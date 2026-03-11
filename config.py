"""Project configuration — all settings in one place."""

import os
from dotenv import load_dotenv

load_dotenv()

# --- OpenAI ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = "gpt-4o-mini"
OPENAI_TEMPERATURE = 0

# --- Crawler ---
MAX_PRODUCTS_PER_SOURCE = 5
CRAWL_TIMEOUT_SECONDS = 35
CRAWL_SOURCES = ["google_shopping", "brand_site", "amazon", "flipkart"]

# --- KB ---
CACHE_HOURS = 24

# --- Scoring Weights (sum to 1.0) ---
WEIGHT_PRICE = 0.25
WEIGHT_RATING = 0.30
WEIGHT_FEATURE_MATCH = 0.25
WEIGHT_REVIEW_COUNT = 0.10
WEIGHT_BRAND_REPUTATION = 0.10

# --- Known Brands and Reputation ---
KNOWN_BRANDS = {
    "borosil": 0.90,
    "milton": 0.80,
    "tupperware": 0.85,
    "cello": 0.70,
    "signoraware": 0.75,
    "treo": 0.65,
    "femora": 0.60,
    "wonderchef": 0.70,
    "lock & lock": 0.80,
    "jaypee": 0.55,
    "nayasa": 0.50,
    "princeware": 0.50,
    "joy home": 0.45,
    "glass lock": 0.70,
}

# --- Domain guardrail keywords ---
DOMAIN_KEYWORDS = [
    "bowl", "container", "lunch", "tiffin", "box", "storage",
    "kitchen", "food", "meal", "prep", "jar", "bottle", "lid",
    "glass", "plastic", "steel", "microwave", "airtight",
    "casserole", "dabba", "canister", "rack", "organizer",
    "water bottle", "flask", "thermos", "tumbler", "sipper",
    "plate", "spoon", "fork", "chopstick", "utensil",
    "masala box", "spice rack", "oil dispenser", "salt pepper",
    "bread box", "cake box", "cookie jar", "cereal container",
    "fridge", "freezer", "pantry", "keep food", "store food",
    "wine glass", "champagne", "flute", "mug", "cup", "drinkware",
    "dinner set", "serving tray", "platter", "coaster", "tableware",
    "pan", "pot", "kadhai", "tawa", "pressure cooker", "cookware",
    "knife", "ladle", "spatula", "cutlery", "baking",
    "crystal", "ceramic", "porcelain", "stoneware", "bone china",
    "borosil", "milton", "tupperware", "cello", "signoraware",
    "treo", "femora", "wonderchef", "lock & lock", "jaypee",
    "nayasa", "princeware",
]