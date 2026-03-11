"""Layer 2: BeautifulSoup — traditional HTML parsing fallback."""

import json
import logging
from typing import Optional

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

_USER_AGENTS = [
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
]

_agent_index = 0


def _get_ua() -> str:
    global _agent_index
    ua = _USER_AGENTS[_agent_index % len(_USER_AGENTS)]
    _agent_index += 1
    return ua


def extract_with_bs4(
    url: str, timeout: int = 15
) -> Optional[dict]:
    """
    Fetch page with requests and parse with BeautifulSoup.
    Tries JSON-LD first, then meta tags, then DOM selectors.
    """
    try:
        headers = {
            "User-Agent": _get_ua(),
            "Accept-Language": "en-IN,en;q=0.9",
        }
        resp = requests.get(url, headers=headers, timeout=timeout)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")

        # --- Sub-layer A: JSON-LD ---
        jsonld = _extract_jsonld(soup)
        if jsonld:
            logger.info("BS4: JSON-LD found for %s", url)
            return {"data": jsonld, "source": "bs4_jsonld", "url": url}

        # --- Sub-layer B: Meta tags ---
        meta = _extract_meta(soup)
        if meta.get("title"):
            logger.info("BS4: Meta tags found for %s", url)
            return {"data": meta, "source": "bs4_meta", "url": url}

        # --- Sub-layer C: Generic DOM ---
        dom = _extract_dom(soup)
        if dom.get("title"):
            logger.info("BS4: DOM extraction for %s", url)
            return {"data": dom, "source": "bs4_dom", "url": url}

        logger.debug(
            "BS4: Could not extract product data from %s", url
        )
        return None

    except Exception as e:
        logger.debug("BS4 failed for %s: %s", url, e)
        return None


def _extract_jsonld(soup: BeautifulSoup) -> Optional[dict]:
    """Extract product data from <script type=application/ld+json>."""
    scripts = soup.find_all("script", {"type": "application/ld+json"})
    for script in scripts:
        try:
            data = json.loads(script.string)
            if isinstance(data, list):
                for item in data:
                    if (
                        isinstance(item, dict)
                        and item.get("@type") == "Product"
                    ):
                        return item
            elif isinstance(data, dict):
                if data.get("@type") == "Product":
                    return data
                graph = data.get("@graph", [])
                for item in graph:
                    if (
                        isinstance(item, dict)
                        and item.get("@type") == "Product"
                    ):
                        return item
        except (json.JSONDecodeError, TypeError):
            continue
    return None


def _extract_meta(soup: BeautifulSoup) -> dict:
    """Extract from Open Graph and product meta tags."""
    result = {}
    tag_map = {
        "og:title": "title",
        "og:description": "description",
        "og:image": "image",
        "product:price:amount": "price",
        "product:price:currency": "currency",
        "product:brand": "brand",
    }
    for prop, key in tag_map.items():
        tag = soup.find("meta", {"property": prop})
        if tag and tag.get("content"):
            result[key] = tag["content"]

    desc_tag = soup.find("meta", {"name": "description"})
    if desc_tag and desc_tag.get("content") and "description" not in result:
        result["description"] = desc_tag["content"]

    return result


def _extract_dom(soup: BeautifulSoup) -> dict:
    """Generic DOM-based extraction as last resort."""
    result = {}

    # Title
    for selector in [
        "#productTitle",
        "h1.product-title",
        ".product-name",
        "h1",
    ]:
        el = soup.select_one(selector)
        if el and el.get_text(strip=True):
            result["title"] = el.get_text(strip=True)
            break

    # Price
    for selector in [
        ".a-price-whole",
        ".price",
        "#priceblock_ourprice",
        ".product-price",
        "[data-price]",
        ".selling-price",
    ]:
        el = soup.select_one(selector)
        if el:
            text = el.get_text(strip=True) or el.get("data-price", "")
            if text:
                result["price_text"] = text
                break

    # Rating
    for selector in [
        ".a-icon-alt",
        ".rating",
        "[data-rating]",
        ".star-rating",
    ]:
        el = soup.select_one(selector)
        if el:
            text = el.get_text(strip=True) or el.get("data-rating", "")
            if text:
                result["rating_text"] = text
                break

    # Description / features
    for selector in [
        "#feature-bullets",
        ".product-description",
        ".product-features",
        "#productDescription",
    ]:
        el = soup.select_one(selector)
        if el:
            result["description"] = el.get_text(" ", strip=True)
            break

    return result


# ─── Multi-product extraction from search results ───

def extract_multiple_from_search(
    url: str, timeout: int = 15, max_products: int = 10
) -> list[dict]:
    """
    Extract multiple products from a search results page.
    Supports Amazon and Google web search.
    Returns list of raw product dicts for the extractor.
    """
    try:
        headers = {
            "User-Agent": _get_ua(),
            "Accept-Language": "en-IN,en;q=0.9",
        }
        resp = requests.get(url, headers=headers, timeout=timeout)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        return _parse_search_html(soup, url, max_products)

    except Exception as e:
        logger.debug("BS4 multi-product skipped for %s: %s", url, e)
        return []


def parse_search_html(
    html: str, url: str, max_products: int = 10
) -> list[dict]:
    """
    Parse pre-fetched HTML (e.g. from Crawl4AI) for multiple products.
    Public wrapper for _parse_search_html.
    """
    soup = BeautifulSoup(html, "html.parser")
    return _parse_search_html(soup, url, max_products)


def _parse_search_html(
    soup: BeautifulSoup, url: str, max_products: int
) -> list[dict]:
    """Route to the appropriate search parser based on URL."""
    if "amazon" in url:
        return _extract_amazon_search(soup, url, max_products)
    elif "google.com/search" in url:
        return _extract_google_search(soup, url, max_products)
    elif "flipkart.com/search" in url:
        return _extract_flipkart_search(soup, url, max_products)
    else:
        return []


def _extract_amazon_search(
    soup: BeautifulSoup, url: str, max_products: int
) -> list[dict]:
    """Parse Amazon search results into individual product dicts."""
    import re
    cards = soup.select('[data-component-type="s-search-result"]')
    products = []

    for card in cards:
        if len(products) >= max_products:
            break

        asin = card.get("data-asin", "")
        if not asin:
            continue

        # Title: second h2 or .a-text-normal (first h2 is often just brand)
        title = None
        brand_name = None
        h2_tags = card.find_all("h2")
        if len(h2_tags) >= 2:
            brand_name = h2_tags[0].get_text(strip=True)
            title = h2_tags[1].get_text(strip=True)
        if not title:
            title_el = card.select_one(".a-text-normal")
            if title_el:
                title = title_el.get_text(strip=True)
        if not title:
            title_el = card.select_one("h2")
            if title_el:
                title = title_el.get_text(strip=True)
        if not title:
            continue

        # Price
        price_el = card.select_one(".a-price-whole")
        price_text = price_el.get_text(strip=True) if price_el else None

        # Rating
        rating_el = card.select_one(".a-icon-alt")
        rating_text = rating_el.get_text(strip=True) if rating_el else None

        # Link — prefer direct /dp/ links over sponsored /sspa/ links
        link = None
        for a_tag in card.find_all("a", href=True):
            href = a_tag["href"]
            if "/dp/" in href or "/gp/" in href:
                link = href if href.startswith("http") else "https://www.amazon.in" + href
                break
        if not link:
            a_tag = card.select_one("a.a-link-normal[href]")
            if a_tag:
                href = a_tag["href"]
                link = href if href.startswith("http") else "https://www.amazon.in" + href

        # Image
        img_el = card.select_one("img.s-image")
        image = img_el["src"] if img_el and img_el.get("src") else ""

        # Review count
        review_text = None
        review_el = card.select_one("span.a-size-base.s-underline-text")
        if review_el:
            review_text = review_el.get_text(strip=True)

        if not price_text:
            continue  # Skip products without prices

        data = {
            "name": title,
            "title": title,
            "brand": brand_name or "",
            "price_text": price_text,
            "rating_text": rating_text or "",
            "image": image,
            "description": title,  # search results don't have full descriptions
            "review_count_text": review_text,
        }

        products.append({
            "data": data,
            "source": "bs4_amazon_search",
            "url": link or url,
        })

    logger.info(
        "Amazon search: extracted %d products from %d cards",
        len(products), len(cards)
    )
    return products


def _extract_google_search(
    soup: BeautifulSoup, url: str, max_products: int
) -> list[dict]:
    """
    Parse Google Shopping search results.
    Works with JS-rendered HTML (from Crawl4AI).
    Cards use div.UC8ZCe with product name, price, merchant in text.
    """
    import re
    price_re = re.compile(r'₹([\d,]+)')
    products = []
    seen_names = set()

    # Google Shopping product cards (JS-rendered)
    cards = soup.select("div.UC8ZCe")
    for card in cards:
        if len(products) >= max_products:
            break

        text = card.get_text(' ', strip=True)
        if not text or len(text) < 10:
            continue

        # Skip non-product cards (filters, "About this result", etc.)
        if 'About this result' in text or 'Report a violation' in text:
            continue
        if text.startswith('Under ') or text.startswith('Over '):
            continue

        prices = price_re.findall(text)
        if not prices:
            continue

        # Extract product name: text before the first ₹ symbol
        price_idx = text.index('₹')
        name = text[:price_idx].strip()
        # Clean up "Also nearby" / "Nearby, X km" prefixes
        if name.startswith('Also nearby'):
            name = name[len('Also nearby'):].strip()
        nearby_match = re.match(r'^Nearby,?\s*\d+\s*km\s*', name)
        if nearby_match:
            name = name[nearby_match.end():].strip()
        if not name or len(name) < 5:
            continue

        # Skip duplicates
        if name in seen_names:
            continue
        seen_names.add(name)

        # Extract merchant
        merchant = None
        for span in card.find_all('span'):
            t = span.get_text(strip=True)
            if '.com' in t or '.in' in t:
                merchant = t
                break

        # Extract rating
        rating = None
        for span in card.find_all('span'):
            t = span.get_text(strip=True)
            if re.match(r'^\d\.\d$', t):
                rating = t
                break

        # Image
        img = card.find('img')
        img_src = ''
        if img:
            src = img.get('src', '')
            if src.startswith('http'):
                img_src = src

        products.append({
            "data": {
                "name": name,
                "title": name,
                "price_text": prices[0],
                "rating_text": rating or "",
                "image": img_src,
                "description": name,
                "merchant": merchant or "",
            },
            "source": "bs4_google_shopping",
            "url": url,
        })

    logger.info("Google search: extracted %d items", len(products))
    return products


def _extract_flipkart_search(
    soup: BeautifulSoup, url: str, max_products: int
) -> list[dict]:
    """
    Parse Flipkart search results.
    Uses div[data-id] cards which contain product text, prices, ratings.
    """
    import re
    price_re = re.compile(r'₹([\d,]+)')
    products = []

    # Flipkart product cards identified by data-id attribute
    cards = soup.find_all('div', attrs={'data-id': True})
    for card in cards:
        if len(products) >= max_products:
            break

        data_id = card.get('data-id', '')
        if not data_id:
            continue

        all_text = card.get_text(' ', strip=True)
        prices = price_re.findall(all_text)
        if not prices:
            continue

        # Title: find first link with substantial text (not price)
        title = None
        link = url
        for a_tag in card.find_all('a', href=True):
            href = a_tag.get('href', '')
            a_text = a_tag.get_text(strip=True)
            if a_text and len(a_text) > 10 and '₹' not in a_text:
                title = a_text
                if '/p/' in href:
                    link = 'https://www.flipkart.com' + href if not href.startswith('http') else href
                break

        if not title:
            # Fallback: text before the first price
            price_idx = all_text.find('₹')
            if price_idx > 5:
                title = all_text[:price_idx].strip()

        if not title or len(title) < 5:
            continue

        # Rating
        rating = None
        for span in card.find_all(['span', 'div']):
            t = span.get_text(strip=True)
            if re.match(r'^\d(\.\d)?$', t):
                rating = t
                break

        # Image
        img = card.find('img')
        img_src = img.get('src', '') if img else ''

        products.append({
            "data": {
                "name": title,
                "title": title,
                "price_text": prices[0],  # First price is selling price
                "rating_text": rating or "",
                "image": img_src,
                "description": title,
            },
            "source": "bs4_flipkart_search",
            "url": link,
        })

    # Fallback: try older CSS-class based selectors
    if not products:
        old_cards = soup.select("div._1AtVbE, div._1sdMkc, div.tUxRFH")
        for card in old_cards[:max_products]:
            title_el = card.select_one("a.IRpwTa, div._4rR01T, a.wjcEIp")
            price_el = card.select_one("div._30jeq3, div._1_WHN1")
            if not title_el or not price_el:
                continue
            products.append({
                "data": {
                    "name": title_el.get_text(strip=True),
                    "title": title_el.get_text(strip=True),
                    "price_text": price_el.get_text(strip=True),
                },
                "source": "bs4_flipkart_search",
                "url": url,
            })

    logger.info("Flipkart search: extracted %d products", len(products))
    return products