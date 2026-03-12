"""Pydantic models — the data contracts for the entire system."""

from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


class QueryIntent(str, Enum):
    RECOMMENDATION = "recommendation"
    COMPARISON = "comparison"
    SEARCH = "search"
    INFORMATIONAL = "informational"


class ParsedQuery(BaseModel):
    """Structured representation of a user's natural language query."""

    intent: QueryIntent = QueryIntent.SEARCH
    product_type: Optional[str] = None
    material: Optional[str] = None
    material_exclude: Optional[str] = None
    brand: Optional[str] = None
    compare_brands: Optional[list[str]] = None
    price_min: Optional[float] = None
    price_max: Optional[float] = None
    capacity_ml: Optional[int] = None
    features: list[str] = Field(default_factory=list)
    lid_required: Optional[bool] = None
    sort_preference: Optional[str] = None
    is_domain_relevant: bool = True
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    clarification_needed: list[str] = Field(default_factory=list)


class ProductSource(BaseModel):
    """A single source (website) where this product was found."""

    site: str
    price: float
    url: str


class Product(BaseModel):
    """A fully normalized product stored in the knowledge base."""

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
    rating: Optional[float] = Field(default=None, ge=0.0, le=5.0)
    review_count: Optional[int] = None
    sources: list[ProductSource] = Field(default_factory=list)
    last_crawled: str = ""
    image_url: Optional[str] = None


class RecommendationResult(BaseModel):
    """A scored and labeled product recommendation."""

    product: Product
    score: float
    label: str = ""
    reasons: list[str] = Field(default_factory=list)
    caveat: Optional[str] = None


class CrawlResult(BaseModel):
    """Result from crawling a single source."""

    source: str
    success: bool
    products_found: int = 0
    error: Optional[str] = None