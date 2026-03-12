"""Product data extractor — turns raw crawl output into clean Product objects."""

import json
import hashlib
import logging
from typing import Optional
from datetime import date

from bs4 import BeautifulSoup

from llm.client import chat_json
from llm.prompts import EXTRACTION_SYSTEM_PROMPT, EXTRACTION_USER_PROMPT
from query_engine.schemas import Product, ProductSource
from utils.normalizer import (
    normalize_price,
    normalize_capacity,
    normalize_rating,
    normalize_review_count,
    normalize_brand,
)

logger = logging.getLogger(__name__)


def extract_product(
    raw: dict, source_site: str
) -> Optional[Product]:
    """
    Extract a structured Product from raw crawl data.
    Uses JSON-LD / meta / DOM data first, then LLM for gaps.
    """
    try:
        if "data" in raw:
            return _from_parsed_data(
                raw["data"], raw.get("url", ""), source_site
            )
        elif "html" in raw:
            return _from_html(
                raw["html"], raw.get("url", ""), source_site
            )
        else:
            logger.warning("Unknown raw crawl format")
            return None
    except Exception as e:
        logger.error("Product extraction failed: %s", e)
        return None


def _from_parsed_data(
    data: dict, url: str, source_site: str
) -> Optional[Product]:
    """Extract from pre-parsed JSON-LD / meta / DOM dict."""

    name = (data.get("name") or data.get("title") or "").strip()
    if not name:
        return None

    brand = _extract_brand_field(data)
    price = _extract_price_field(data)
    rating = _extract_rating_field(data)
    review_count = _extract_review_count_field(data)
    description = data.get("description", "")
    image = data.get("image", "")
    if isinstance(image, dict):
        image = image.get("url", "")
    if isinstance(image, list):
        image = image[0] if image else ""

    # LLM-assisted feature extraction when basic extraction has gaps
    features_data = _llm_extract_features(
        name,
        description,
        data.get("price_text", str(price) if price else ""),
        data.get("rating_text", str(rating) if rating else ""),
    )

    # Merge LLM results with basic extraction — LLM only fills gaps
    material = features_data.get("material")
    capacity_ml = features_data.get("capacity_ml")
    lid = bool(features_data.get("lid") or False)
    microwave_safe = bool(features_data.get("microwave_safe") or False)
    dishwasher_safe = bool(features_data.get("dishwasher_safe") or False)
    bpa_free = bool(features_data.get("bpa_free") or False)
    features = features_data.get("features", [])

    if not brand and features_data.get("brand"):
        brand = features_data["brand"]
    if not price and features_data.get("price_inr"):
        price = features_data["price_inr"]
    if not rating and features_data.get("rating"):
        rating = features_data["rating"]
    if not review_count and features_data.get("review_count"):
        review_count = features_data["review_count"]

    if not price or price <= 0:
        logger.debug("Skipping product without valid price: %s", name)
        return None

    brand = normalize_brand(brand) if brand else "Unknown"
    product_id = _generate_id(brand, name, capacity_ml)
    product_type = _detect_product_type(name)
    category = _detect_category(product_type)

    return Product(
        product_id=product_id,
        product_name=name,
        brand=brand,
        category=category,
        product_type=product_type,
        material=material,
        capacity_ml=capacity_ml,
        lid=lid,
        microwave_safe=microwave_safe,
        dishwasher_safe=dishwasher_safe,
        bpa_free=bpa_free,
        features=features,
        price_inr=price,
        rating=min(rating, 5.0) if rating is not None else None,
        review_count=review_count,
        sources=[
            ProductSource(site=source_site, price=price, url=url)
        ],
        last_crawled=date.today().isoformat(),
        image_url=image if isinstance(image, str) else None,
    )


def _from_html(
    html: str, url: str, source_site: str
) -> Optional[Product]:
    """Extract from raw HTML by first parsing with BS4."""
    soup = BeautifulSoup(html, "html.parser")

    # Try JSON-LD in the HTML
    jsonld = _find_jsonld(soup)
    if jsonld:
        return _from_parsed_data(jsonld, url, source_site)

    # Fall back to meta + DOM
    data = {}
    title_el = soup.select_one("h1") or soup.select_one("title")
    if title_el:
        data["title"] = title_el.get_text(strip=True)

    desc_el = soup.find("meta", {"name": "description"})
    if desc_el:
        data["description"] = desc_el.get("content", "")

    # Price from DOM
    for sel in [
        ".a-price-whole",
        ".price",
        ".selling-price",
        "#priceblock_ourprice",
    ]:
        el = soup.select_one(sel)
        if el:
            data["price_text"] = el.get_text(strip=True)
            break

    # Rating from DOM
    for sel in [
        ".a-icon-alt",
        ".rating",
        "[data-rating]",
        ".star-rating",
    ]:
        el = soup.select_one(sel)
        if el:
            data["rating_text"] = (
                el.get_text(strip=True) or el.get("data-rating", "")
            )
            break

    # Image from DOM
    for sel in [
        "#landingImage",
        ".product-image img",
        "img.product-img",
        "img[data-old-hires]",
    ]:
        el = soup.select_one(sel)
        if el:
            data["image"] = (
                el.get("data-old-hires")
                or el.get("src")
                or ""
            )
            break

    if data.get("title"):
        return _from_parsed_data(data, url, source_site)

    return None


def _find_jsonld(soup: BeautifulSoup) -> Optional[dict]:
    """Find Product JSON-LD in the page."""
    for script in soup.find_all(
        "script", {"type": "application/ld+json"}
    ):
        try:
            obj = json.loads(script.string)
            if isinstance(obj, dict) and obj.get("@type") == "Product":
                return obj
            if isinstance(obj, list):
                for item in obj:
                    if (
                        isinstance(item, dict)
                        and item.get("@type") == "Product"
                    ):
                        return item
            if isinstance(obj, dict):
                for item in obj.get("@graph", []):
                    if (
                        isinstance(item, dict)
                        and item.get("@type") == "Product"
                    ):
                        return item
        except (json.JSONDecodeError, TypeError):
            continue
    return None


def _extract_brand_field(data: dict) -> Optional[str]:
    """Extract brand from various data formats."""
    brand = data.get("brand")
    if isinstance(brand, dict):
        b = brand.get("name", "").strip()
        if b:
            return b
    if isinstance(brand, str) and brand.strip():
        return brand.strip()

    # Fallback: try to detect brand from product name or title
    name = (data.get("name") or data.get("title") or "").strip()
    if name:
        detected = _detect_brand_from_name(name)
        if detected:
            return detected

    # Also try merchant field (Google Shopping)
    merchant = data.get("merchant", "")
    if merchant:
        detected = _detect_brand_from_name(merchant)
        if detected:
            return detected

    return None


# Known brand names for detection from product names
_KNOWN_BRAND_NAMES = [
    "Borosil", "Milton", "Tupperware", "Cello", "Signoraware",
    "Treo", "Femora", "Wonderchef", "Lock & Lock", "Jaypee",
    "Nayasa", "Princeware", "Glass Lock", "Cutting Edge",
    "Kuber Industries", "JEOBEST", "Flair", "Pigeon",
    "Vaya", "Oliveware", "Home Puff", "HomePuff",
    "Cresimo", "Zanmini", "Glasslock", "Pyrex", "Corelle",
    "La Opala", "Laopala", "IKEA",
]


def _detect_brand_from_name(text: str) -> Optional[str]:
    """Detect brand from product name — first word(s) are almost always the brand."""
    import re
    words = text.split()
    if not words:
        return None

    # Strategy: the brand is the first word (or first two words) of the product name.
    # Check if first 1-2 words match a known brand (word-boundary, not substring).
    text_lower = text.lower()
    # Try multi-word brands first (e.g. "Cutting Edge", "Lock & Lock", "La Opala")
    for brand in _KNOWN_BRAND_NAMES:
        if " " in brand:
            pattern = r'\b' + re.escape(brand.lower()) + r'\b'
            if re.search(pattern, text_lower):
                return brand
    # Then single-word brands — must match as a whole word
    for brand in _KNOWN_BRAND_NAMES:
        if " " not in brand:
            pattern = r'\b' + re.escape(brand.lower()) + r'\b'
            if re.search(pattern, text_lower):
                return brand

    # Fallback: first word is likely the brand (very common in e-commerce titles)
    first = words[0]
    # Skip generic/descriptive first words
    _SKIP = {"the", "a", "an", "new", "set", "pack", "of", "premium",
             "best", "top", "buy", "original", "genuine"}
    if first.lower() not in _SKIP and len(first) >= 2:
        return first if first[0].isupper() or first.isupper() else None
    return None


def _extract_price_field(data: dict) -> Optional[float]:
    """Extract price from JSON-LD offers or direct fields."""
    # JSON-LD offers format
    offers = data.get("offers", {})
    if isinstance(offers, dict):
        p = offers.get("price") or offers.get("lowPrice")
        if p is not None:
            return normalize_price(str(p))
    if isinstance(offers, list) and offers:
        p = offers[0].get("price")
        if p is not None:
            return normalize_price(str(p))

    # Direct price fields
    for key in ["price", "price_text"]:
        if data.get(key):
            return normalize_price(str(data[key]))
    return None


def _extract_rating_field(data: dict) -> Optional[float]:
    """Extract rating from aggregateRating or direct fields."""
    ar = data.get("aggregateRating", {})
    if isinstance(ar, dict):
        r = ar.get("ratingValue")
        if r is not None:
            return normalize_rating(str(r))
    for key in ["rating", "rating_text"]:
        if data.get(key):
            return normalize_rating(str(data[key]))
    return None


def _extract_review_count_field(data: dict) -> Optional[int]:
    """Extract review count from aggregateRating."""
    ar = data.get("aggregateRating", {})
    if isinstance(ar, dict):
        rc = ar.get("reviewCount") or ar.get("ratingCount")
        if rc is not None:
            return normalize_review_count(str(rc))
    return None


def _llm_extract_features(
    name: str,
    description: str,
    price_text: str,
    rating_text: str,
) -> dict:
    """
    Use LLM to extract detailed features from product description.
    Only called when basic extraction leaves gaps.
    """
    if not description and not name:
        return {}

    try:
        prompt = EXTRACTION_USER_PROMPT.format(
            name=name or "Unknown",
            description=description or "No description available.",
            price_text=price_text or "N/A",
            rating_text=rating_text or "N/A",
        )
        return chat_json(EXTRACTION_SYSTEM_PROMPT, prompt)
    except Exception as e:
        logger.error("LLM feature extraction failed: %s", e)
        return {}


def _generate_id(
    brand: str, name: str, capacity_ml: Optional[int]
) -> str:
    """Generate a deterministic product ID from brand + name + capacity."""
    raw = f"{brand.lower()}_{name.lower()}_{capacity_ml or 0}"
    return "prod_" + hashlib.md5(raw.encode()).hexdigest()[:12]


def _detect_product_type(name: str) -> str:
    """Detect product type from the product name."""
    n = name.lower()
    type_map = [
        ("lunch box", "lunch box"),
        ("lunchbox", "lunch box"),
        ("tiffin", "tiffin box"),
        ("bento", "bento box"),
        ("meal prep", "meal prep container"),
        ("water bottle", "water bottle"),
        ("flask", "flask"),
        ("thermos", "flask"),
        ("tumbler", "tumbler"),
        ("sipper", "sipper"),
        ("casserole", "casserole"),
        ("hot pot", "casserole"),
        ("hot case", "casserole"),
        ("jar", "jar"),
        ("canister", "canister"),
        ("masala", "jar"),
        ("spice", "jar"),
        ("oil dispenser", "oil dispenser"),
        ("bread box", "bread box"),
        ("cake box", "cake box"),
        ("bottle", "water bottle"),
        ("bowl", "bowl"),
        ("container", "storage container"),
    ]
    for keyword, ptype in type_map:
        if keyword in n:
            return ptype
    return "storage container"


def _detect_category(product_type: str) -> str:
    """Map product type to a broader category."""
    cat_map = {
        "bowl": "storage container",
        "storage container": "storage container",
        "lunch box": "lunch box",
        "tiffin box": "lunch box",
        "bento box": "lunch box",
        "meal prep container": "meal prep container",
        "water bottle": "bottle",
        "flask": "bottle",
        "tumbler": "bottle",
        "sipper": "bottle",
        "casserole": "casserole",
        "jar": "jar",
        "canister": "jar",
        "oil dispenser": "kitchen accessory",
        "bread box": "storage container",
        "cake box": "storage container",
    }
    return cat_map.get(product_type, "storage container")