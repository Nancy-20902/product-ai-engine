"""Value normalization — prices, capacities, ratings, brands."""

import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def normalize_price(text: str) -> Optional[float]:
    """
    Normalize any price string to a float in INR.
    Handles: Rs489, Rs. 489, 489 INR, 4,999, MRP Rs599 Rs489, etc.
    """
    if not text:
        return None

    text = str(text).strip()

    # Remove currency symbols and words
    text = re.sub(r"[₹$€£]", "", text)
    text = re.sub(r"(?i)(rs\.?|inr|mrp|price|rupees)", "", text)

    # Find all numbers (could be MRP followed by sale price)
    numbers = re.findall(r"[\d,]+\.?\d*", text)
    if not numbers:
        return None

    prices = []
    for n in numbers:
        n = n.replace(",", "")
        try:
            prices.append(float(n))
        except ValueError:
            continue

    if not prices:
        return None

    # If multiple prices found (MRP and sale), return the lowest (sale price)
    # Filter out unreasonably small values (could be quantity like "2" or "3")
    valid_prices = [p for p in prices if p >= 10]
    if valid_prices:
        return min(valid_prices)

    return prices[-1]


def normalize_capacity(text: str) -> Optional[int]:
    """
    Normalize capacity to milliliters.
    Handles: 1L, 1.6 litres, 500 ML, 1600ml, etc.
    """
    if not text:
        return None

    text = str(text).strip().lower()

    # Try litres first
    match = re.search(r"([\d.]+)\s*(?:l(?:itre)?(?:s)?|ltr)", text)
    if match:
        litres = float(match.group(1))
        return int(litres * 1000)

    # Try millilitres
    match = re.search(r"([\d.]+)\s*(?:ml|millilitre|milliliter)", text)
    if match:
        return int(float(match.group(1)))

    # Try bare number if context suggests capacity
    match = re.search(r"(\d+)", text)
    if match:
        val = int(match.group(1))
        # Heuristic: if the number is 1-30 it's probably litres
        if 1 <= val <= 30:
            return val * 1000
        # If 50-10000 it's probably ml
        if 50 <= val <= 10000:
            return val

    return None


def normalize_rating(text: str) -> Optional[float]:
    """
    Normalize rating to a float 0-5.
    Handles: 4.5 out of 5 stars, 4.5/5, 4.5, etc.
    """
    if not text:
        return None

    text = str(text).strip()

    # "4.5 out of 5" or "4.5/5"
    match = re.search(r"([\d.]+)\s*(?:out\s*of\s*5|/\s*5)", text)
    if match:
        val = float(match.group(1))
        return min(val, 5.0)

    # Bare number
    match = re.search(r"([\d.]+)", text)
    if match:
        val = float(match.group(1))
        if 0 <= val <= 5:
            return val

    return None


def normalize_review_count(text: str) -> Optional[int]:
    """
    Normalize review count to integer.
    Handles: 3,420 ratings, (3420), 3.4K reviews, etc.
    """
    if not text:
        return None

    text = str(text).strip()

    # Handle K suffix (3.4K -> 3400)
    match = re.search(r"([\d.]+)\s*[kK]", text)
    if match:
        return int(float(match.group(1)) * 1000)

    # Extract number with commas
    match = re.search(r"([\d,]+)", text)
    if match:
        num_str = match.group(1).replace(",", "")
        try:
            return int(num_str)
        except ValueError:
            return None

    return None


def normalize_brand(brand: str) -> str:
    """Normalize brand name — fix case, remove symbols."""
    if not brand:
        return "Unknown"

    brand = brand.strip()
    # Remove trademark symbols
    brand = re.sub(r"[®™©]", "", brand)
    brand = brand.strip()

    # Title case
    brand = brand.title()

    # Known corrections
    corrections = {
        "Boroseal": "Borosil",
        "Tuperware": "Tupperware",
        "Tupperwear": "Tupperware",
        "Miton": "Milton",
        "Signora": "Signoraware",
        "Lock And Lock": "Lock & Lock",
        "Locknlock": "Lock & Lock",
    }
    if brand in corrections:
        brand = corrections[brand]

    return brand