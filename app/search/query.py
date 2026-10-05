"""Filters -> parameterised SQL.

Values only ever go in as bound parameters. Column names and sort orders come
from fixed tables in this file, so nothing produced by the parser (or the LLM)
ends up in the SQL text.
"""
import base64
import json
import sqlite3

from app.schemas import Filters

# every order ends with id so the ordering is total, which keyset pagination needs
ORDERS: dict[str, list[tuple[str, str]]] = {
    "default": [("year", "DESC"), ("km_driven", "ASC"), ("id", "ASC")],
    "price_asc": [("price", "ASC"), ("id", "ASC")],
    "price_desc": [("price", "DESC"), ("id", "ASC")],
    "km_asc": [("km_driven", "ASC"), ("id", "ASC")],
    "year_desc": [("year", "DESC"), ("km_driven", "ASC"), ("id", "ASC")],
    "safety_desc": [("safety_rating", "DESC"), ("price", "ASC"), ("id", "ASC")],
}


# Index that already stores rows in each sort order. When a query matches a large
# share of the catalogue, walking this index and stopping after `limit` hits is far
# cheaper than letting SQLite collect every match and sort it.
SORT_INDEX = {
    "default": "idx_year_km",
    "year_desc": "idx_year_km",
    "price_asc": "idx_price",
    "price_desc": "idx_price",
    "km_asc": "idx_km",
    "safety_desc": "idx_safety_price",
}


class InvalidCursor(ValueError):
    pass


def where_clause(f: Filters) -> tuple[list[str], list]:
    where, args = [], []

    def in_(col, vals):
        if vals:
            where.append(f"{col} IN ({','.join('?' * len(vals))})")
            args.extend(vals)

    def cmp(col, op, val):
        if val is not None:
            where.append(f"{col} {op} ?")
            args.append(val)

    in_("body_type", f.body_types)
    in_("fuel_type", f.fuel_types)
    in_("make", f.makes)
    cmp("transmission", "=", f.transmission)
    cmp("city", "=", f.city)
    cmp("price", ">=", f.min_price)
    cmp("price", "<=", f.max_price)
    cmp("km_driven", "<=", f.max_km)
    cmp("year", ">=", f.min_year)
    cmp("seats", ">=", f.min_seats)
    cmp("safety_rating", ">=", f.min_safety)
    return where, args


def _sql_where(parts: list[str]) -> str:
    return " WHERE " + " AND ".join(parts) if parts else ""


def count(con: sqlite3.Connection, f: Filters, cap: int = 0) -> tuple[int, bool]:
    """Return (count, exact). With a cap, stop counting after `cap` matches."""
    where, args = where_clause(f)
    if not cap:
        return con.execute(f"SELECT COUNT(*) FROM cars{_sql_where(where)}", args).fetchone()[0], True
    sql = f"SELECT COUNT(*) FROM (SELECT 1 FROM cars{_sql_where(where)} LIMIT ?)"
    n = con.execute(sql, [*args, cap + 1]).fetchone()[0]
    return min(n, cap), n <= cap


def table_size(con: sqlite3.Connection) -> int:
    return con.execute("SELECT COUNT(*) FROM cars").fetchone()[0]


def encode_cursor(sort: str, row: dict) -> str:
    values = [row[col] for col, _ in ORDERS[sort]]
    raw = json.dumps({"s": sort, "v": values}, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(sort: str, cursor: str) -> list:
    try:
        data = json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
        values = data["v"]
    except Exception as e:
        raise InvalidCursor("cursor is malformed") from e
    if data.get("s") != sort or len(values) != len(ORDERS[sort]):
        raise InvalidCursor("cursor does not belong to this query")
    return values


def _after(sort: str, values: list) -> tuple[str, list]:
    """Rows strictly after `values` in the given order (keyset condition).

    The first term bounds the leading sort column so SQLite can seek straight to
    the right place in the index instead of scanning from the start.
    """
    order = ORDERS[sort]
    lead_col, lead_dir = order[0]
    ors, args = [], [values[0]]
    for i, (col, direction) in enumerate(order):
        parts = [f"{c} = ?" for c, _ in order[:i]] + [f"{col} {'<' if direction == 'DESC' else '>'} ?"]
        ors.append("(" + " AND ".join(parts) + ")")
        args.extend(values[: i + 1])
    bound = f"{lead_col} {'<=' if lead_dir == 'DESC' else '>='} ?"
    return f"{bound} AND (" + " OR ".join(ors) + ")", args


def fetch(con: sqlite3.Connection, f: Filters, limit: int, offset: int = 0,
          cursor: str | None = None, walk_sort_index: bool = False) -> list[dict]:
    """Return up to `limit` rows. Uses keyset pagination when a cursor is given, OFFSET otherwise.

    walk_sort_index: read rows in sort order from the sort's index. Only worth it
    when the filters match many rows; for selective filters let SQLite pick.
    """
    sort = f.sort or "default"
    where, args = where_clause(f)
    if cursor:
        cond, cond_args = _after(sort, decode_cursor(sort, cursor))
        where, args = [*where, cond], [*args, *cond_args]
        offset = 0
    hint = f" INDEXED BY {SORT_INDEX[sort]}" if walk_sort_index else ""
    order_by = ", ".join(f"{col} {d}" for col, d in ORDERS[sort])
    sql = f"SELECT * FROM cars{hint}{_sql_where(where)} ORDER BY {order_by} LIMIT ? OFFSET ?"
    return [dict(r) for r in con.execute(sql, [*args, limit, offset])]
