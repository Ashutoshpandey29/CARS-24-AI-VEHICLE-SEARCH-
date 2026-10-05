from typing import List, Optional

from pydantic import BaseModel, Field

from app.vocab import CITIES, MAKES, BodyType, FuelType, SortKey, Transmission


class Filters(BaseModel):
    """Structured form of a search query. Both parsers produce this."""

    body_types: List[BodyType] = Field(default_factory=list)
    fuel_types: List[FuelType] = Field(default_factory=list)
    transmission: Optional[Transmission] = None
    makes: List[str] = Field(default_factory=list, description=f"Subset of: {', '.join(MAKES)}")
    min_price: Optional[int] = Field(None, description="INR, absolute rupees")
    max_price: Optional[int] = Field(None, description="INR, absolute rupees")
    max_km: Optional[int] = None
    min_year: Optional[int] = None
    min_seats: Optional[int] = None
    min_safety: Optional[int] = Field(None, description="NCAP stars 0-5")
    city: Optional[str] = Field(None, description=f"One of: {', '.join(CITIES)}")
    sort: Optional[SortKey] = None


class Car(BaseModel):
    id: int
    make: str
    model: str
    variant: str
    body_type: str
    fuel_type: str
    transmission: str
    year: int
    km_driven: int
    price: int
    seats: int
    safety_rating: int
    owners: int
    city: str
    color: str
    registration: str


class SearchResponse(BaseModel):
    query: str
    parser: str = Field(description="'llm', 'model' or 'rules': which parser produced the filters")
    filters: dict = Field(description="How the query was understood")
    relaxed: List[str] = Field(description="Soft filters dropped because the strict search found nothing")
    total: int
    total_exact: bool = Field(description="False when there are more than COUNT_CAP matches; `total` is then a lower bound")
    limit: int
    offset: int
    next_cursor: Optional[str] = Field(None, description="Pass back as `cursor` to get the next page")
    took_ms: float
    results: List[Car]
