"""Knowledge base CRUD operations with caching."""

import json
import os
import logging
from datetime import datetime, timedelta
from typing import Optional

from query_engine.schemas import ParsedQuery, Product

logger = logging.getLogger(__name__)

KB_DIR = os.path.join(os.path.dirname(__file__))
PRODUCTS_FILE = os.path.join(KB_DIR, "products.json")
SOURCES_FILE = os.path.join(KB_DIR, "sources.json")
CACHE_HOURS = 24


def load_products() -> list[Product]:
    """Load all products from the knowledge base."""
    if not os.path.exists(PRODUCTS_FILE):
        logger.warning("products.json not found. Returning empty list.")
        return []

    try:
        with open(PRODUCTS_FILE, "r", encoding="utf-8") as f:
            content = f.read().strip()
        if not content:
            return []
        data = json.loads(content)
    except (json.JSONDecodeError, IOError) as e:
        logger.error("Failed to load products.json: %s", e)
        return []

    products = []
    for item in data:
        try:
            products.append(Product(**item))
        except Exception as e:
            logger.warning("Skipping invalid product entry: %s", e)
    return products


def save_products(products: list[Product]) -> None:
    """Save products to the knowledge base."""
    os.makedirs(KB_DIR, exist_ok=True)
    data = [p.model_dump() for p in products]
    with open(PRODUCTS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    logger.info("Saved %d products to KB.", len(products))


def search_products(query: ParsedQuery) -> list[Product]:
    """Search KB for products matching the parsed query."""
    all_products = load_products()
    if not all_products:
        return []

    results = []
    for product in all_products:
        if _matches_query(product, query):
            results.append(product)

    # Sort by rating descending
    results.sort(key=lambda p: p.rating, reverse=True)
    logger.info("KB search found %d matching products.", len(results))
    return results


def _matches_query(product: Product, query: ParsedQuery) -> bool:
    """Check if a product matches the parsed query filters."""

    # Product type filter (bidirectional substring match)
    if query.product_type:
        pt = query.product_type.lower()
        ptype = product.product_type.lower()
        cat = product.category.lower()
        if not (pt in ptype or ptype in pt or pt in cat or cat in pt):
            return False

    # Material filter
    if query.material:
        if (
            not product.material
            or query.material.lower() not in product.material.lower()
        ):
            return False

    # Material exclude filter
    if query.material_exclude:
        if (
            product.material
            and query.material_exclude.lower() in product.material.lower()
        ):
            return False

    # Brand filter (supports multi-brand via compare_brands)
    if query.compare_brands and len(query.compare_brands) > 1:
        if product.brand.lower() not in [
            b.lower() for b in query.compare_brands
        ]:
            return False
    elif query.brand:
        if query.brand.lower() != product.brand.lower():
            return False

    # Price range filter
    if query.price_max is not None and product.price_inr > query.price_max:
        return False
    if query.price_min is not None and product.price_inr < query.price_min:
        return False

    # Capacity filter (20 percent tolerance)
    if query.capacity_ml and product.capacity_ml:
        ratio = product.capacity_ml / query.capacity_ml
        if ratio < 0.8 or ratio > 1.2:
            return False

    # Lid filter (hard filter only when explicitly required)
    if query.lid_required is True and not product.lid:
        return False

    return True


def needs_crawling(query: ParsedQuery, results: list[Product]) -> bool:
    """Determine if live crawling is needed."""
    # Too few results
    if len(results) < 5:
        return True

    # Check if any results are stale
    now = datetime.now()
    for product in results:
        if product.last_crawled:
            try:
                last = datetime.strptime(product.last_crawled, "%Y-%m-%d")
                if now - last > timedelta(hours=CACHE_HOURS):
                    return True
            except ValueError:
                continue

    return False


def add_products(new_products: list[Product]) -> None:
    """
    Merge new products into KB.
    - New product: add it.
    - Existing product, all fields same: skip.
    - Existing product, new data fills gaps: update only the gaps.
    """
    existing = load_products()
    existing_map = {p.product_id: p for p in existing}

    added = 0
    updated = 0
    for product in new_products:
        if product.product_id in existing_map:
            old = existing_map[product.product_id]
            changed = False

            # Fill empty fields from new data
            if (not old.material or old.material == "N/A") and product.material:
                old.material = product.material
                changed = True
            if not old.capacity_ml and product.capacity_ml:
                old.capacity_ml = product.capacity_ml
                changed = True
            if (not old.brand or old.brand == "Unknown") and product.brand and product.brand != "Unknown":
                old.brand = product.brand
                changed = True
            if not old.image_url and product.image_url:
                old.image_url = product.image_url
                changed = True
            if not old.features and product.features:
                old.features = product.features
                changed = True

            # Update price if lower
            if product.price_inr < old.price_inr:
                old.price_inr = product.price_inr
                changed = True
            # Update rating if higher
            if product.rating > old.rating:
                old.rating = product.rating
                changed = True
            # Update booleans only if new is True (confirmed)
            for attr in ("lid", "microwave_safe", "dishwasher_safe", "bpa_free"):
                if getattr(product, attr) and not getattr(old, attr):
                    setattr(old, attr, True)
                    changed = True

            # Add new sources
            old_urls = {s.url for s in old.sources}
            for src in product.sources:
                if src.url not in old_urls:
                    old.sources.append(src)
                    changed = True

            if changed:
                old.last_crawled = product.last_crawled or old.last_crawled
                updated += 1
        else:
            existing.append(product)
            existing_map[product.product_id] = product
            added += 1

    if added > 0 or updated > 0:
        save_products(list(existing_map.values()))
        logger.info("KB update: %d added, %d updated.", added, updated)


def load_sources() -> dict:
    """Load crawl history."""
    if not os.path.exists(SOURCES_FILE):
        return {}
    try:
        with open(SOURCES_FILE, "r", encoding="utf-8") as f:
            content = f.read().strip()
        if not content:
            return {}
        return json.loads(content)
    except (json.JSONDecodeError, IOError):
        return {}


def save_source(url: str) -> None:
    """Record that a URL was crawled now."""
    sources = load_sources()
    sources[url] = datetime.now().isoformat()
    with open(SOURCES_FILE, "w", encoding="utf-8") as f:
        json.dump(sources, f, indent=2)


def was_recently_crawled(url: str) -> bool:
    """Check if a URL was crawled within the cache window."""
    sources = load_sources()
    if url not in sources:
        return False
    try:
        last = datetime.fromisoformat(sources[url])
        return datetime.now() - last < timedelta(hours=CACHE_HOURS)
    except (ValueError, TypeError):
        return False