"""LLM-powered query understanding engine."""

import re
import logging
from typing import Optional

from llm.client import chat_json
from llm.prompts import QUERY_SYSTEM_PROMPT, QUERY_USER_PROMPT
from llm.guardrails import sanitize_input, is_domain_relevant_quick
from query_engine.schemas import ParsedQuery, QueryIntent

logger = logging.getLogger(__name__)


def parse_query(user_query: str) -> ParsedQuery:
    """Convert any natural language query into a structured ParsedQuery."""

    # Step 1 — sanitize
    clean = sanitize_input(user_query)
    if not clean:
        return _empty_result("Please enter a valid search query.")

    # Step 2 — quick domain check (saves API cost on obvious junk)
    if not is_domain_relevant_quick(clean):
        logger.info(
            "Quick domain check: no keywords found, sending to LLM anyway."
        )

    # Step 3 — LLM parsing
    try:
        prompt = QUERY_USER_PROMPT.format(query=clean)
        data = chat_json(QUERY_SYSTEM_PROMPT, prompt)
        # Sanitize null list fields before Pydantic validation
        if data.get("clarification_needed") is None:
            data["clarification_needed"] = []
        if data.get("features") is None:
            data["features"] = []
        if data.get("compare_brands") is None:
            data.pop("compare_brands", None)
        result = ParsedQuery(**data)
    except Exception as e:
        logger.error("LLM query parsing failed: %s", e)
        return _fallback_parse(clean)

    # Step 4 — post-validation
    result = _post_validate(result, clean)

    logger.info(
        "Parsed query: intent=%s type=%s brand=%s conf=%.2f",
        result.intent,
        result.product_type,
        result.brand,
        result.confidence,
    )
    return result


def _post_validate(p: ParsedQuery, query: str = "") -> ParsedQuery:
    """Apply business rules after LLM parsing."""

    # Hard-correct price ceiling for explicit "under/below/max/upto X" phrases.
    # The LLM sometimes applies a ±20% range for "under X" — override that.
    _UNDER_RE = re.compile(
        r"\b(?:under|below|less\s+than|max|upto|up\s+to|within|budget|not\s+more\s+than)"
        r"\s*(?:rs\.?\s*)?([\d,]+)",
        re.IGNORECASE,
    )
    m = _UNDER_RE.search(query)
    if m:
        cap = float(m.group(1).replace(",", ""))
        p.price_max = cap
        p.price_min = None  # "under X" implies no lower bound from the query

    # Hard-correct price floor for explicit "above/over/min X" phrases.
    _OVER_RE = re.compile(
        r"\b(?:above|over|more\s+than|starting\s+from|min(?:imum)?)\s*"
        r"(?:rs\.?\s*)?([\d,]+)",
        re.IGNORECASE,
    )
    m2 = _OVER_RE.search(query)
    if m2:
        floor = float(m2.group(1).replace(",", ""))
        p.price_min = floor

    # Clamp prices
    if p.price_max is not None and p.price_max > 100000:
        p.price_max = 100000
    if p.price_min is not None and p.price_min < 0:
        p.price_min = 0

    # Clamp capacity
    if p.capacity_ml is not None and p.capacity_ml > 50000:
        p.capacity_ml = 50000

    # Smart defaults — bowl or container: prefer lid
    if (
        p.product_type in ("bowl", "storage container", "container")
        and p.lid_required is None
    ):
        p.lid_required = True
        if "lid preference" not in p.clarification_needed:
            p.clarification_needed.append("lid preference")

    # Smart defaults — lunch box or tiffin: prefer microwave safe
    if p.product_type in ("lunch box", "tiffin box", "tiffin", "bento box"):
        lower_features = [f.lower() for f in p.features]
        if "microwave safe" not in lower_features:
            p.features.append("microwave safe")
            if "microwave preference" not in p.clarification_needed:
                p.clarification_needed.append("microwave preference")

    return p


def _fallback_parse(query: str) -> ParsedQuery:
    """Keyword-based fallback when LLM fails."""
    q = query.lower()

    product_type = None
    type_map = {
        "bowl": "bowl",
        "container": "storage container",
        "lunch box": "lunch box",
        "lunchbox": "lunch box",
        "tiffin": "tiffin box",
        "bottle": "water bottle",
        "flask": "flask",
        "jar": "jar",
        "casserole": "casserole",
        "tumbler": "tumbler",
        "sipper": "sipper",
    }
    for kw, pt in type_map.items():
        if kw in q:
            product_type = pt
            break

    return ParsedQuery(
        intent=QueryIntent.SEARCH,
        product_type=product_type,
        is_domain_relevant=product_type is not None,
        confidence=0.3,
        clarification_needed=[],
    )


def _empty_result(message: str) -> ParsedQuery:
    """Return an empty non-relevant result with a message."""
    return ParsedQuery(
        intent=QueryIntent.SEARCH,
        is_domain_relevant=False,
        confidence=0.0,
        clarification_needed=[message],
    )