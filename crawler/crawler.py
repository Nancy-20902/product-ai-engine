"""Main crawler orchestrator — manages the 3-layer fallback strategy."""

import logging
from urllib.parse import quote_plus
from typing import Optional

from query_engine.schemas import ParsedQuery, Product, CrawlResult
from crawler.crawl4ai_layer import run_crawl4ai
from crawler.bs4_layer import extract_with_bs4, extract_multiple_from_search, parse_search_html
from crawler.playwright_layer import extract_with_playwright_stealth
from crawler.extractor import extract_product
# KB source caching removed — always live fetch
from config import MAX_PRODUCTS_PER_SOURCE, CRAWL_TIMEOUT_SECONDS

logger = logging.getLogger(__name__)

# Sites that need stealth mode (Layer 3)
_STEALTH_SITES = {"amazon", "flipkart"}


def crawl_for_products(
    query: ParsedQuery,
) -> tuple[list[Product], list[CrawlResult]]:
    """
    Crawl multiple sources for products matching the query.
    Returns (products_found, crawl_reports).
    Each source is independent — one failure does NOT stop others.

    For multi-brand queries (e.g. "borosil vs milton"), crawls for
    each brand separately from Amazon/Flipkart to ensure coverage.
    """
    brands = query.compare_brands or []
    if query.brand and query.brand not in brands:
        brands.append(query.brand)

    # If multiple brands, crawl Amazon & Flipkart per brand
    if len(brands) > 1:
        return _crawl_multi_brand(query, brands)

    search_term = _build_search_term(query)
    urls = _generate_search_urls(
        search_term, query.brand, brands=brands
    )

    all_products: list[Product] = []
    reports: list[CrawlResult] = []

    for source_name, url_list in urls.items():
        source_products = _crawl_source(
            source_name, url_list, all_products
        )
        success = len(source_products) > 0

        all_products.extend(source_products)
        reports.append(
            CrawlResult(
                source=source_name,
                success=success,
                products_found=len(source_products),
                error=None if success else f"No results from {source_name}",
            )
        )

        logger.info(
            "Source %s: %d products found",
            source_name,
            len(source_products),
        )

    return all_products, reports


def _crawl_multi_brand(
    query: ParsedQuery, brands: list[str]
) -> tuple[list[Product], list[CrawlResult]]:
    """Crawl Amazon & Flipkart separately per brand to ensure both brands appear."""
    all_products: list[Product] = []
    reports: list[CrawlResult] = []
    per_brand_limit = max(3, MAX_PRODUCTS_PER_SOURCE // len(brands) + 1)

    for brand_name in brands:
        # Build a brand-specific search term
        brand_query = query.model_copy()
        brand_query.brand = brand_name
        search_term = _build_search_term(brand_query)
        encoded = quote_plus(search_term)

        for source_name, url in [
            ("Amazon", f"https://www.amazon.in/s?k={encoded}"),
            ("Flipkart", f"https://www.flipkart.com/search?q={encoded}"),
        ]:
            label = f"{source_name} ({brand_name})"
            products = _crawl_url(url, source_name)
            products = products[:per_brand_limit]

            all_products.extend(products)
            reports.append(
                CrawlResult(
                    source=label,
                    success=len(products) > 0,
                    products_found=len(products),
                )
            )
            logger.info("Source %s: %d products", label, len(products))

    # Also try Google Shopping with combined query as fallback
    search_term = _build_search_term(query)
    encoded = quote_plus(search_term)
    gs_url = f"https://www.google.com/search?q={encoded}+buy+online&tbm=shop"
    gs_products = _crawl_source(
        "Google Shopping", [gs_url], all_products
    )
    all_products.extend(gs_products)
    reports.append(
        CrawlResult(
            source="Google Shopping",
            success=len(gs_products) > 0,
            products_found=len(gs_products),
        )
    )

    return all_products, reports


def _crawl_source(
    source_name: str, url_list: list[str],
    existing_products: list[Product],
) -> list[Product]:
    """
    Crawl a single source (all its URLs). For Google Shopping,
    skip products that duplicate names already found from other sources.
    """
    source_products = []
    is_google = source_name == "Google Shopping"

    # Build set of existing product names for dedup (Google only)
    existing_names = set()
    if is_google:
        for p in existing_products:
            existing_names.add(p.product_name.lower().strip())

    for url in url_list:
        if len(source_products) >= MAX_PRODUCTS_PER_SOURCE:
            break

        products = _crawl_url(url, source_name)
        if products:
            if is_google:
                # Filter out dupes from Amazon/Flipkart
                for p in products:
                    pn = p.product_name.lower().strip()
                    if pn not in existing_names:
                        source_products.append(p)
                        existing_names.add(pn)
            else:
                source_products.extend(products)

    return source_products[:MAX_PRODUCTS_PER_SOURCE]


def _crawl_url(
    url: str, source_name: str
) -> list[Product]:
    """
    Extract products from a URL.
    For search result pages (Amazon, Google, Flipkart), extracts multiple
    products. For individual product pages, extracts one.
    """
    is_search = any(
        pat in url
        for pat in ["/s?k=", "/search?q=", "tbm=shop", "/search?"]
    )

    if is_search:
        return _crawl_search_page(url, source_name)
    else:
        product = _crawl_single_url(url, source_name)
        return [product] if product else []


def _crawl_search_page(
    url: str, source_name: str
) -> list[Product]:
    """
    Extract multiple products from a search results page.
    Tries BS4 multi-product extraction first (works without JS),
    then falls back to Crawl4AI for JS-rendered pages.
    """
    # ── BS4 multi-product extraction (best for Amazon) ──
    logger.debug("BS4 multi-extract: trying %s", url[:80])
    raw_list = extract_multiple_from_search(
        url, timeout=CRAWL_TIMEOUT_SECONDS,
        max_products=MAX_PRODUCTS_PER_SOURCE,
    )
    if raw_list:
        products = []
        for raw in raw_list:
            product = extract_product(raw, source_name)
            if product:
                products.append(product)
        if products:
            logger.info(
                "BS4 multi-extract: %d products from %s",
                len(products), source_name,
            )
            return products

    # ── Fallback: Crawl4AI (for JS-rendered search pages) ──
    logger.debug("BS4 returned 0, trying Crawl4AI for %s", url[:80])
    raw = run_crawl4ai(url, timeout=CRAWL_TIMEOUT_SECONDS)
    if raw and raw.get("html"):
        # Parse the Crawl4AI HTML for multiple products
        raw_list = parse_search_html(
            raw["html"], raw.get("url", url), MAX_PRODUCTS_PER_SOURCE
        )
        if raw_list:
            products = []
            for r in raw_list:
                product = extract_product(r, source_name)
                if product:
                    products.append(product)
            if products:
                logger.info(
                    "Crawl4AI multi-extract: %d products from %s",
                    len(products), source_name,
                )
                return products

        # Last resort: try single-product extraction from the HTML
        product = extract_product(raw, source_name)
        if product:
            return [product]

    logger.debug("Search page extraction failed for %s", url[:80])
    return []


def _crawl_single_url(
    url: str, source_name: str
) -> Optional[Product]:
    """
    Try to extract a product from a single URL using the 3-layer strategy.
    Layer 1: Crawl4AI
    Layer 2: BeautifulSoup
    Layer 3: Playwright Stealth (Amazon/Flipkart only)
    """
    needs_stealth = any(
        s in source_name.lower() for s in _STEALTH_SITES
    )

    # ── Layer 1: Crawl4AI ──
    logger.debug("Layer 1 (Crawl4AI): trying %s", url[:80])
    raw = run_crawl4ai(url, timeout=CRAWL_TIMEOUT_SECONDS)
    if raw:
        product = extract_product(raw, source_name)
        if product:
            logger.info(
                "Layer 1 success: %s", product.product_name[:50]
            )
            return product
    logger.debug("Layer 1 failed for %s, trying Layer 2", url[:80])

    # ── Layer 2: BeautifulSoup ──
    logger.debug("Layer 2 (BS4): trying %s", url[:80])
    raw = extract_with_bs4(url, timeout=CRAWL_TIMEOUT_SECONDS)
    if raw:
        product = extract_product(raw, source_name)
        if product:
            logger.info(
                "Layer 2 success: %s", product.product_name[:50]
            )
            return product
    logger.debug("Layer 2 failed for %s", url[:80])

    # ── Layer 3: Playwright Stealth (Amazon/Flipkart only) ──
    if needs_stealth:
        logger.debug("Layer 3 (Stealth): trying %s", url[:80])
        raw = extract_with_playwright_stealth(
            url, timeout=CRAWL_TIMEOUT_SECONDS
        )
        if raw:
            product = extract_product(raw, source_name)
            if product:
                logger.info(
                    "Layer 3 success: %s",
                    product.product_name[:50],
                )
                return product
        logger.debug("Layer 3 failed for %s", url[:80])
    else:
        logger.debug(
            "Skipping Layer 3 (stealth not needed for %s)",
            source_name,
        )

    logger.debug("All 3 layers failed for URL: %s", url[:80])
    return None


def _build_search_term(query: ParsedQuery) -> str:
    """Build a search string from parsed query."""
    parts = []
    if query.brand:
        parts.append(query.brand)
    if query.material:
        parts.append(query.material)
    if query.product_type:
        parts.append(query.product_type)
    if query.capacity_ml:
        if query.capacity_ml >= 1000:
            parts.append(f"{query.capacity_ml / 1000:.1f}L")
        else:
            parts.append(f"{query.capacity_ml}ml")
    if query.price_max:
        parts.append(f"under {int(query.price_max)}")

    # Add up to 2 features to avoid overly long search
    for feature in query.features[:2]:
        parts.append(feature)

    return " ".join(parts) if parts else "storage container"


def _generate_search_urls(
    search_term: str, brand: Optional[str],
    brands: Optional[list[str]] = None,
) -> dict[str, list[str]]:
    """Generate search URLs for each source, priority-ordered."""
    encoded = quote_plus(search_term)
    # Use list of tuples to preserve insertion order (priority)
    urls: dict[str, list[str]] = {}

    # 1. Amazon India (highest priority)
    urls["Amazon"] = [
        f"https://www.amazon.in/s?k={encoded}",
    ]

    # 2. Flipkart
    urls["Flipkart"] = [
        f"https://www.flipkart.com/search?q={encoded}",
    ]

    # 3. Brand website (if brand specified)
    brand_sites = {
        "borosil": "https://www.borosil.com/search?q=",
        "milton": "https://www.miltonhomware.com/search?q=",
        "tupperware": "https://www.tupperwareindia.com/catalogsearch/result/?q=",
        "signoraware": "https://www.signoraware.com/search?q=",
        "wonderchef": "https://www.wonderchef.com/search?q=",
        "cello": "https://www.celloworld.com/search?q=",
    }
    all_brands = list(brands or [])
    if brand and brand not in all_brands:
        all_brands.append(brand)
    for b in all_brands:
        b_lower = b.lower()
        if b_lower in brand_sites:
            urls.setdefault("Brand Site", []).append(
                brand_sites[b_lower] + quote_plus(search_term)
            )

    # 4. Google Shopping (lowest priority — fallback)
    urls["Google Shopping"] = [
        f"https://www.google.com/search?q={encoded}+buy+online&tbm=shop",
    ]

    return urls