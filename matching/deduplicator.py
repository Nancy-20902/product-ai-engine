"""Product deduplication — merge same products found across different sites."""

import logging
from thefuzz import fuzz
from query_engine.schemas import Product

logger = logging.getLogger(__name__)

# Two products are duplicates if similarity exceeds this threshold
SIMILARITY_THRESHOLD = 85


def deduplicate(products: list[Product]) -> list[Product]:
    """Remove duplicates: merge same products found on different sites."""
    if not products:
        return []

    unique: list[Product] = []

    for product in products:
        merged = False
        for i, existing in enumerate(unique):
            if _is_duplicate(existing, product):
                unique[i] = _merge(existing, product)
                merged = True
                logger.info(
                    "Merged duplicate: %s ~ %s",
                    existing.product_name[:40],
                    product.product_name[:40],
                )
                break
        if not merged:
            unique.append(product)

    logger.info(
        "Deduplication: %d -> %d products",
        len(products),
        len(unique),
    )
    return unique


def _is_duplicate(a: Product, b: Product) -> bool:
    """Check if two products are the same item from different sources."""
    # Different brands = definitely not duplicate
    if a.brand.lower() != b.brand.lower():
        return False

    # Name similarity check
    name_score = fuzz.token_sort_ratio(
        a.product_name.lower(), b.product_name.lower()
    )
    if name_score < SIMILARITY_THRESHOLD:
        return False

    # If capacity is known for both, it must be close
    if a.capacity_ml and b.capacity_ml:
        ratio = a.capacity_ml / b.capacity_ml
        if ratio < 0.8 or ratio > 1.2:
            return False

    return True


def _merge(existing: Product, new: Product) -> Product:
    """Merge a duplicate product — keep best data, combine sources."""
    # Keep the longer / more descriptive name
    if len(new.product_name) > len(existing.product_name):
        existing.product_name = new.product_name

    # Merge sources (avoid duplicate sites)
    existing_sites = {s.site for s in existing.sources}
    for src in new.sources:
        if src.site not in existing_sites:
            existing.sources.append(src)

    # Keep lower price
    existing.price_inr = min(existing.price_inr, new.price_inr)

    # Keep higher rating and review count
    if new.rating > existing.rating:
        existing.rating = new.rating
    if new.review_count > existing.review_count:
        existing.review_count = new.review_count

    # Merge features (union)
    existing_features_lower = {f.lower() for f in existing.features}
    for feat in new.features:
        if feat.lower() not in existing_features_lower:
            existing.features.append(feat)

    # Fill in missing fields from new product
    if not existing.material and new.material:
        existing.material = new.material
    if not existing.capacity_ml and new.capacity_ml:
        existing.capacity_ml = new.capacity_ml
    if not existing.image_url and new.image_url:
        existing.image_url = new.image_url

    # Boolean fields: true if either source says true
    if new.lid:
        existing.lid = True
    if new.microwave_safe:
        existing.microwave_safe = True
    if new.dishwasher_safe:
        existing.dishwasher_safe = True
    if new.bpa_free:
        existing.bpa_free = True

    # Update crawl date to latest
    existing.last_crawled = (
        new.last_crawled or existing.last_crawled
    )

    return existing