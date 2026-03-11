"""Input sanitization, prompt injection defense, and domain validation."""

import re
import logging
from config import DOMAIN_KEYWORDS

logger = logging.getLogger(__name__)

# Prompt injection patterns
_INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?(previous|above|prior)\s+(instructions|prompts|rules)",
    r"you\s+are\s+now\s+a",
    r"forget\s+(everything|all)",
    r"system\s*prompt",
    r"act\s+as\s+(a|an)",
    r"pretend\s+you",
    r"do\s+not\s+follow",
    r"override",
    r"jailbreak",
    r"disregard",
    r"new\s+instructions",
    r"reveal\s+(your|the)\s+(prompt|instructions)",
]


def sanitize_input(query: str) -> str:
    """Clean user input and strip injection attempts."""
    if not query or not isinstance(query, str):
        return ""

    # Hard length limit
    query = query[:500]

    # Strip injection patterns
    for pattern in _INJECTION_PATTERNS:
        if re.search(pattern, query, re.IGNORECASE):
            logger.warning("Prompt injection attempt detected and stripped.")
            query = re.sub(pattern, "", query, flags=re.IGNORECASE)

    # Remove dangerous characters but keep currency symbols and basic punctuation
    query = re.sub(r"[^\w\s₹$€£.,!?&\-/()'\"]", "", query)

    # Collapse whitespace
    query = re.sub(r"\s+", " ", query).strip()

    return query


def is_domain_relevant_quick(query: str) -> bool:
    """Quick keyword check before LLM call to save API cost on obvious spam."""
    query_lower = query.lower()
    return any(kw in query_lower for kw in DOMAIN_KEYWORDS)


def validate_parsed_domain(parsed: dict) -> bool:
    """Validate LLM's domain relevance flag with our own check."""
    if not parsed.get("is_domain_relevant", False):
        return False

    # If LLM said relevant but there is no product_type and no brand, double-check
    if not parsed.get("product_type") and not parsed.get("brand"):
        features = parsed.get("features", [])
        if not features:
            return False

    return True