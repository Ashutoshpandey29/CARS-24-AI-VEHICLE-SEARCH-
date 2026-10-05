from fastapi import APIRouter, HTTPException, Query

from app.config import get_settings
from app.db import ping
from app.schemas import Car, SearchResponse
from app.search import service
from app.search.query import InvalidCursor

router = APIRouter()


@router.get("/health")
def health():
    ok = ping()
    if not ok:
        raise HTTPException(503, "database unavailable")
    return {"status": "ok", "parser": "llm" if get_settings().llm_enabled else "rules"}


@router.get("/search", response_model=SearchResponse)
def search(
    q: str = Query(..., min_length=2, max_length=300, examples=["Show SUVs under ₹15L"]),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0, le=10_000, description="Simple paging. Prefer `cursor` for deep pages."),
    cursor: str | None = Query(None, max_length=512, description="`next_cursor` from the previous page"),
):
    try:
        return service.search(q, limit, offset, cursor)
    except InvalidCursor as e:
        raise HTTPException(400, str(e))


@router.get("/cars/{car_id}", response_model=Car)
def get_car(car_id: int):
    car = service.get_car(car_id)
    if car is None:
        raise HTTPException(404, "Car not found")
    return car
