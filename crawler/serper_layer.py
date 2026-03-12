"""Serper.dev API layer — replaces Google Shopping scraping."""

import requests
import logging
from config import SERPER_API_KEY

logger = logging.getLogger(__name__)


def search_google_shopping(query: str, max_results: int = 5) -> list[dict]:
    """
    Call Serper.dev shopping API and return normalized raw dicts
    compatible with extract_product().
    """
    if not SERPER_API_KEY:
        logger.warning("SERPER_API_KEY not set, skipping Google Shopping")
        return []

    try:
        response = requests.post(
            "https://google.serper.dev/shopping",
            headers={
                "X-API-KEY": SERPER_API_KEY,
                "Content-Type": "application/json",
            },
            json={"q": query, "gl": "in", "hl": "en", "num": max_results},
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()

    except requests.RequestException as e:
        logger.error("Serper API call failed: %s", e)
        return []

    results = []
    for item in data.get("shopping", [])[:max_results]:
        raw = {
            "data": {
                "title": item.get("title", ""),
                "name": item.get("title", ""),
                "price_text": item.get("price", ""),
                "rating_text": str(item.get("rating", "")) if item.get("rating") else "",
                "description": item.get("snippet", ""),
                "image": item.get("imageUrl", ""),
            },
            "url": item.get("link", ""),
            "seller_site": item.get("source", "Google Shopping"),
        }
        results.append(raw)

    logger.info("Serper returned %d shopping results", len(results))
    return results
