"""Measure search latency on a large catalogue.

Seeds a temporary database (1M cars by default), then runs the example
queries through the real API with the cache on and off.

    python scripts/benchmark.py --count 1000000
"""
import argparse
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

QUERIES = [
    "Show SUVs under ₹15L",
    "Diesel automatic cars below 80k km",
    "Family cars with high safety ratings",
    "Hyundai between 5 and 9 lakh after 2019 in Pune, cheapest",
    "7 seater diesel under 20L",
    "petrol hatchback under 5 lakh in delhi",
    "automatic sedan newest",
]


def pct(values, p):
    values = sorted(values)
    return values[min(len(values) - 1, int(len(values) * p))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=1_000_000)
    ap.add_argument("--rounds", type=int, default=20)
    args = ap.parse_args()

    db = os.path.join(tempfile.mkdtemp(), "bench.db")
    os.environ["DB_PATH"] = db
    os.environ.pop("ANTHROPIC_API_KEY", None)

    from fastapi.testclient import TestClient

    from app.cache import get_cache
    from app.main import app
    from scripts.seed import seed

    seed(args.count, db)
    client = TestClient(app)

    print(f"\n{'query':<60} {'total':>9} {'cold ms':>8} {'warm ms':>8}")
    cold_all, warm_all = [], []
    for q in QUERIES:
        cold = []
        for _ in range(args.rounds):
            get_cache().clear()
            t = time.perf_counter()
            r = client.get("/search", params={"q": q}).json()
            cold.append((time.perf_counter() - t) * 1000)
        warm = []
        for _ in range(args.rounds):
            t = time.perf_counter()
            client.get("/search", params={"q": q})
            warm.append((time.perf_counter() - t) * 1000)
        cold_all += cold
        warm_all += warm
        print(f"{q:<60} {str(r['total']) + ('' if r['total_exact'] else '+'):>9} {statistics.median(cold):>8.1f} {statistics.median(warm):>8.2f}")

    # deep paging: offset vs cursor at roughly the 5,000th result
    q = "Show SUVs under ₹15L"
    get_cache().clear()
    t = time.perf_counter()
    client.get("/search", params={"q": q, "limit": 100, "offset": 5000})
    offset_ms = (time.perf_counter() - t) * 1000
    cursor = None
    for _ in range(50):
        r = client.get("/search", params={"q": q, "limit": 100, **({"cursor": cursor} if cursor else {})}).json()
        cursor = r["next_cursor"]
    get_cache().clear()
    t = time.perf_counter()
    client.get("/search", params={"q": q, "limit": 100, "cursor": cursor})
    cursor_ms = (time.perf_counter() - t) * 1000

    print(f"\n{args.count:,} cars, {args.rounds} rounds per query")
    print(f"uncached: p50 {pct(cold_all, .5):.1f} ms, p95 {pct(cold_all, .95):.1f} ms")
    print(f"cached:   p50 {pct(warm_all, .5):.2f} ms, p95 {pct(warm_all, .95):.2f} ms")
    print(f"page at result ~5,000: offset {offset_ms:.1f} ms, cursor {cursor_ms:.1f} ms")
    os.remove(db)


if __name__ == "__main__":
    main()
