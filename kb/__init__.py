"""Pydantic schemas for structured query parsing and product data."""

from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


class QueryIntent(str, Enum):
    RECOMMENDATION = "recommendation"
    COMPARISON = "comparison"
    SEARCH = "search"
    INFORMATIONAL = "informational"


class ParsedQuery(BaseModel):
    """LLM extracts this structured object from any natural language query."""

    intent: QueryIntent = Field(description="What the user wants to do")
    product_type: Optional[str] = Field(None, description="e.g., bowl, lunch box, container")
    material: Optional[str] = Field(None, description="e.g., glass, plastic, steel, borosilicate")
    brand: Optional[str] = Field(None, description="Detected brand name, normalized")
    price_min: Optional[float] = Field(None, description="Minimum price in INR")
    price_max: Optional[float] = Field(None, description="Maximum price in INR")
    capacity_ml: Optional[int] = Field(None, description="Capacity in milliliters")
    features: list[str] = Field(default_factory=list, description="e.g., microwave safe, airtight, BPA free")
    lid_required: Optional[bool] = Field(None, description="Whether lid is required")
    sort_preference: Optional[str] = Field(None, description="e.g., cheapest, highest rated, best value")
    is_domain_relevant: bool = Field(True, description="False if query is outside kitchen storage domain")
    confidence: float = Field(0.0, ge=0.0, le=1.0, description="LLM's confidence in parsing")
    clarification_needed: list[str] = Field(default_factory=list, description="Attributes the user should clarify")


class ProductSource(BaseModel):
    site: str
    price: float
    url: str


class Product(BaseModel):
    product_id: str
    product_name: str
    brand: str
    category: str
    product_type: str
    material: Optional[str] = None
    capacity_ml: Optional[int] = None
    lid: bool = False
    microwave_safe: bool = False
    dishwasher_safe: bool = False
    bpa_free: bool = False
    features: list[str] = Field(default_factory=list)
    price_inr: float
    rating: float = Field(ge=0.0, le=5.0)
    review_count: int = 0
    sources: list[ProductSource] = Field(default_factory=list)
    last_crawled: str = ""
    image_url: Optional[str] = None


class RecommendationResult(BaseModel):
    product: Product
    score: float
    label: str = ""  # "Best Value", "Highest Rated", "Budget Pick"
    reasons: list[str] = Field(default_factory=list)