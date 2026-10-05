import json
import os
import time

from app.cache import get_cache
from app.config import get_settings
from app.db import get_connection
from app.parser import parse
from app.schemas import Filters
from app.search import query as q

# dropped one by one, in this order, when the strict search finds nothing.
# Budget, fuel, body type, make and city are hard constraints and are never relaxed.
SOFT_FILTERS = ["min_safety", "max_km", "min_year"]

# If the filters match at least this share of the catalogue, read rows in sort
# order from an index and stop early instead of sorting every match.
DENSE_SHARE = 0.01


def _catalog_version() -> int:
    # reseeding the DB changes its mtime, which invalidates every cached count and page
    try:
        return os.stat(get_settings().db_path).st_mtime_ns
    except OSError:
        return 0


def _cached(key: str, ttl: int, compute):
    cache = get_cache()
    if (hit := cache.get(key)) is not None:
        return json.loads(hit)
    value = compute()
    cache.set(key, json.dumps(value), ttl)
    return value


def search(text: str, limit: int, offset: int = 0, cursor: str | None = None) -> dict:
    started = time.perf_counter()
    filters, source = parse(text)
    con = get_connection()
    ttl = get_settings().result_cache_ttl
    version = _catalog_version()

    def key(kind: str, f: Filters, *extra) -> str:
        return f"{kind}:v1:{version}:{f.model_dump_json()}:" + ":".join(map(str, extra))

    cap = get_settings().count_cap

    def count(f: Filters) -> tuple[int, bool]:
        return tuple(_cached(key("count", f), ttl, lambda: q.count(con, f, cap)))

    total, exact = count(filters)
    relaxed = []
    for name in SOFT_FILTERS:
        if total:
            break
        if getattr(filters, name) is not None:
            setattr(filters, name, None)
            relaxed.append(name)
            total, exact = count(filters)

    size = _cached(f"size:v1:{version}", ttl, lambda: q.table_size(con))
    dense = not exact or total >= size * DENSE_SHARE
    # fetch one extra row to know whether there is a next page
    rows = _cached(key("page", filters, limit, offset, cursor), ttl,
                   lambda: q.fetch(con, filters, limit + 1, offset, cursor, walk_sort_index=dense)) if total else []
    has_more = len(rows) > limit
    rows = rows[:limit]

    return {
        "query": text,
        "parser": source,
        "filters": filters.model_dump(exclude_defaults=True),
        "relaxed": relaxed,
        "total": total,
        "total_exact": exact,
        "limit": limit,
        "offset": 0 if cursor else offset,
        "next_cursor": q.encode_cursor(filters.sort or "default", rows[-1]) if has_more else None,
        "took_ms": round((time.perf_counter() - started) * 1000, 2),
        "results": rows,
    }


def get_car(car_id: int) -> dict | None:
    row = get_connection().execute("SELECT * FROM cars WHERE id = ?", (car_id,)).fetchone()
    return dict(row) if row else None
