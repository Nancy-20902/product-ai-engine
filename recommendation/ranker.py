"""Multi-criteria scoring + LLM-powered recommendation explanation."""

import logging
from llm.client import chat_json
from llm.prompts import (
    RECOMMENDATION_SYSTEM_PROMPT,
    RECOMMENDATION_USER_PROMPT,
)
from query_engine.schemas import (
    ParsedQuery,
    Product,
    RecommendationResult,
)
from config import (
    WEIGHT_PRICE,
    WEIGHT_RATING,
    WEIGHT_FEATURE_MATCH,
    WEIGHT_REVIEW_COUNT,
    WEIGHT_BRAND_REPUTATION,
    KNOWN_BRANDS,
)

logger = logging.getLogger(__name__)


def rank_products(
    products: list[Product],
    query: ParsedQuery,
    original_query: str = "",
) -> list[RecommendationResult]:
    """Score, rank, and explain product recommendations."""
    if not products:
        return []

    # Step 1: Algorithmic scoring (deterministic, no LLM)
    scored = _score_all(products, query)

    # Step 2: LLM-generated explanations
    scored = _add_llm_explanations(
        scored, original_query or query.product_type or "storage container"
    )

    return scored


def _score_all(
    products: list[Product], query: ParsedQuery
) -> list[RecommendationResult]:
    """Score every product using the weighted formula."""
    if not products:
        return []

    # Compute normalization bounds
    prices = [p.price_inr for p in products]
    reviews = [p.review_count for p in products if p.review_count is not None]
    min_price = min(prices)
    max_price = max(prices)
    max_reviews = max(reviews) if reviews else 1

    results = []

    for product in products:
        score = 0.0
        reasons = []

        # --- Price Score (lower is better) ---
        if max_price > min_price:
            price_score = 1.0 - (
                (product.price_inr - min_price)
                / (max_price - min_price)
            )
        else:
            price_score = 1.0

        # Bonus if within budget
        if query.price_max and product.price_inr <= query.price_max:
            price_score = min(1.0, price_score + 0.1)
            reasons.append(f"Within budget (Rs{product.price_inr:.0f})")

        score += WEIGHT_PRICE * price_score

        # --- Rating Score (higher is better) ---
        if product.rating is not None:
            rating_score = product.rating / 5.0
            if product.rating >= 4.5:
                reasons.append(f"Excellent rating ({product.rating})")
            score += WEIGHT_RATING * rating_score
        else:
            # Unknown rating — redistribute weight to other factors
            score += WEIGHT_RATING * 0.5

        # --- Feature Match Score ---
        feature_score = _compute_feature_match(product, query)
        if feature_score > 0.8:
            reasons.append("Strong feature match")
        score += WEIGHT_FEATURE_MATCH * feature_score

        # --- Review Count Score (social proof) ---
        if product.review_count is not None:
            review_score = min(
                1.0, product.review_count / max(max_reviews, 1)
            )
            if product.review_count > 1000:
                reasons.append(
                    f"Popular ({product.review_count} reviews)"
                )
            score += WEIGHT_REVIEW_COUNT * review_score
        else:
            # Unknown review count — redistribute weight
            score += WEIGHT_REVIEW_COUNT * 0.5

        # --- Brand Reputation Score ---
        brand_score = KNOWN_BRANDS.get(
            product.brand.lower(), 0.50
        )
        score += WEIGHT_BRAND_REPUTATION * brand_score

        # Normalize to 0-100
        final_score = round(score * 100, 1)

        results.append(
            RecommendationResult(
                product=product,
                score=final_score,
                reasons=reasons,
            )
        )

    # Sort by score descending
    results.sort(key=lambda r: r.score, reverse=True)

    # Assign labels
    _assign_labels(results)

    return results


def _compute_feature_match(
    product: Product, query: ParsedQuery
) -> float:
    """Score how well product features match query requirements."""
    if (
        not query.features
        and query.lid_required is None
        and query.material is None
    ):
        return 0.7  # Neutral score when no features specified

    matches = 0
    total_checks = 0

    # Material match
    if query.material:
        total_checks += 1
        if (
            product.material
            and query.material.lower() in product.material.lower()
        ):
            matches += 1

    # Material exclude
    if query.material_exclude:
        total_checks += 1
        if not product.material or (
            query.material_exclude.lower()
            not in product.material.lower()
        ):
            matches += 1

    # Lid match
    if query.lid_required is not None:
        total_checks += 1
        if product.lid == query.lid_required:
            matches += 1

    # Capacity match (within 20 percent tolerance)
    if query.capacity_ml:
        total_checks += 1
        if product.capacity_ml:
            ratio = product.capacity_ml / query.capacity_ml
            if 0.8 <= ratio <= 1.2:
                matches += 1

    # Feature matching
    product_features_lower = {f.lower() for f in product.features}
    product_features_lower.update(_get_boolean_features(product))

    for feature in query.features:
        total_checks += 1
        feature_lower = feature.lower()
        if any(
            feature_lower in pf or pf in feature_lower
            for pf in product_features_lower
        ):
            matches += 1

    return matches / max(total_checks, 1)


def _get_boolean_features(product: Product) -> set[str]:
    """Convert boolean product attributes to feature strings for matching."""
    features = set()
    if product.microwave_safe:
        features.add("microwave safe")
    if product.dishwasher_safe:
        features.add("dishwasher safe")
    if product.bpa_free:
        features.add("bpa free")
    if product.lid:
        features.add("lid")
    return features


def _assign_labels(recommendations: list[RecommendationResult]) -> None:
    """Assign descriptive labels to top recommendations."""
    if not recommendations:
        return

    # Best overall = highest score
    recommendations[0].label = "Best Overall"

    # Find category winners
    cheapest = min(
        recommendations, key=lambda r: r.product.price_inr
    )
    highest_rated = max(
        recommendations, key=lambda r: r.product.rating if r.product.rating is not None else -1
    )
    most_reviewed = max(
        recommendations, key=lambda r: r.product.review_count if r.product.review_count is not None else -1
    )

    # Assign labels (don't overwrite Best Overall)
    if cheapest is not recommendations[0] and not cheapest.label:
        cheapest.label = "Budget Pick"
    if (
        highest_rated is not recommendations[0]
        and not highest_rated.label
    ):
        highest_rated.label = "Highest Rated"
    if (
        most_reviewed is not recommendations[0]
        and most_reviewed is not highest_rated
        and not most_reviewed.label
    ):
        most_reviewed.label = "Most Popular"



def _add_llm_explanations(
    recommendations: list[RecommendationResult],
    original_query: str,
) -> list[RecommendationResult]:
    """Use LLM to generate human-readable recommendation reasons."""
    if not recommendations:
        return recommendations

    # Prepare product text for the LLM
    top_products = recommendations[:5]
    products_lines = []
    for i, rec in enumerate(top_products, 1):
        p = rec.product
        features_str = ", ".join(p.features[:5]) if p.features else "none listed"
        lid_str = "Yes" if p.lid else "N/A"
        micro_str = "Yes" if p.microwave_safe else "N/A"
        products_lines.append(
            f"{i}. {p.product_name} | Brand: {p.brand} | "
            f"Price: Rs{p.price_inr:.0f} | Rating: {p.rating}/5 | " if p.rating is not None else
            f"Price: Rs{p.price_inr:.0f} | Rating: N/A | "
            f"Material: {p.material or 'N/A'} | "
            f"Capacity: {p.capacity_ml or 'N/A'}ml | "
            f"Lid: {lid_str} | Microwave: {micro_str} | "
            f"Features: {features_str} | Score: {rec.score}/100 | "
            f"ID: {p.product_id}"
        )
    products_text = "\n".join(products_lines)

    try:
        prompt = RECOMMENDATION_USER_PROMPT.format(
            query=original_query,
            products_text=products_text,
        )
        data = chat_json(
            RECOMMENDATION_SYSTEM_PROMPT, prompt, max_tokens=1500
        )

        llm_recs = data.get("recommendations", [])

        # Map LLM output back to our recommendation objects
        id_map = {rec.product.product_id: rec for rec in top_products}
        for llm_rec in llm_recs:
            pid = llm_rec.get("product_id", "")
            if pid in id_map:
                rec = id_map[pid]
                if llm_rec.get("label"):
                    rec.label = llm_rec["label"]
                if llm_rec.get("reasons"):
                    rec.reasons = llm_rec["reasons"]
                if llm_rec.get("caveat"):
                    rec.caveat = llm_rec["caveat"]

    except Exception as e:
        logger.error("LLM recommendation explanation failed: %s", e)
        # Algorithmic labels and reasons still work — no crash

    return recommendations