"""Generate a realistic used-car catalogue into SQLite.

The output is deterministic (fixed random seed), so tests and screenshots are reproducible.

    python scripts/seed.py                 # 600 cars into data/cars.db
    python scripts/seed.py 1000000         # a million cars, for load testing
    python scripts/seed.py 5000 --db /tmp/cars.db
"""
import argparse
import random
import sqlite3
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.vocab import CITIES  # noqa: E402

# make, model, body, seats, new ex-showroom price (lakh), fuels, transmissions, Global/Bharat NCAP stars
CATALOG = [
    ("Maruti Suzuki", "Swift", "Hatchback", 5, 7.0, ["Petrol", "CNG"], ["Manual", "Automatic"], 2),
    ("Maruti Suzuki", "Baleno", "Hatchback", 5, 7.5, ["Petrol", "CNG"], ["Manual", "Automatic"], 3),
    ("Maruti Suzuki", "Wagon R", "Hatchback", 5, 5.5, ["Petrol", "CNG"], ["Manual", "Automatic"], 1),
    ("Maruti Suzuki", "Dzire", "Sedan", 5, 7.5, ["Petrol", "CNG"], ["Manual", "Automatic"], 5),
    ("Maruti Suzuki", "Brezza", "SUV", 5, 10.5, ["Petrol", "CNG"], ["Manual", "Automatic"], 4),
    ("Maruti Suzuki", "Ertiga", "MUV", 7, 10.0, ["Petrol", "CNG"], ["Manual", "Automatic"], 3),
    ("Maruti Suzuki", "Grand Vitara", "SUV", 5, 14.0, ["Petrol", "Hybrid"], ["Manual", "Automatic"], 4),
    ("Hyundai", "i20", "Hatchback", 5, 8.0, ["Petrol", "Diesel"], ["Manual", "Automatic"], 3),
    ("Hyundai", "Venue", "SUV", 5, 9.5, ["Petrol", "Diesel"], ["Manual", "Automatic"], 4),
    ("Hyundai", "Creta", "SUV", 5, 14.0, ["Petrol", "Diesel"], ["Manual", "Automatic"], 5),
    ("Hyundai", "Verna", "Sedan", 5, 12.5, ["Petrol", "Diesel"], ["Manual", "Automatic"], 5),
    ("Hyundai", "Alcazar", "SUV", 7, 18.0, ["Petrol", "Diesel"], ["Manual", "Automatic"], 5),
    ("Tata", "Tiago", "Hatchback", 5, 6.0, ["Petrol", "CNG", "Electric"], ["Manual", "Automatic"], 4),
    ("Tata", "Altroz", "Hatchback", 5, 7.5, ["Petrol", "Diesel", "CNG"], ["Manual", "Automatic"], 5),
    ("Tata", "Punch", "SUV", 5, 7.0, ["Petrol", "CNG", "Electric"], ["Manual", "Automatic"], 5),
    ("Tata", "Nexon", "SUV", 5, 10.0, ["Petrol", "Diesel", "Electric"], ["Manual", "Automatic"], 5),
    ("Tata", "Harrier", "SUV", 5, 18.0, ["Diesel"], ["Manual", "Automatic"], 5),
    ("Tata", "Safari", "SUV", 7, 20.0, ["Diesel"], ["Manual", "Automatic"], 5),
    ("Mahindra", "XUV300", "SUV", 5, 10.0, ["Petrol", "Diesel"], ["Manual", "Automatic"], 5),
    ("Mahindra", "Thar", "SUV", 4, 14.0, ["Petrol", "Diesel"], ["Manual", "Automatic"], 4),
    ("Mahindra", "Scorpio-N", "SUV", 7, 17.0, ["Petrol", "Diesel"], ["Manual", "Automatic"], 5),
    ("Mahindra", "XUV700", "SUV", 7, 20.0, ["Petrol", "Diesel"], ["Manual", "Automatic"], 5),
    ("Mahindra", "Bolero", "SUV", 7, 10.0, ["Diesel"], ["Manual"], 1),
    ("Kia", "Sonet", "SUV", 5, 9.5, ["Petrol", "Diesel"], ["Manual", "Automatic"], 3),
    ("Kia", "Seltos", "SUV", 5, 14.0, ["Petrol", "Diesel"], ["Manual", "Automatic"], 3),
    ("Kia", "Carens", "MUV", 7, 13.0, ["Petrol", "Diesel"], ["Manual", "Automatic"], 3),
    ("Honda", "Amaze", "Sedan", 5, 8.0, ["Petrol", "Diesel"], ["Manual", "Automatic"], 4),
    ("Honda", "City", "Sedan", 5, 13.0, ["Petrol", "Diesel", "Hybrid"], ["Manual", "Automatic"], 4),
    ("Honda", "Elevate", "SUV", 5, 13.5, ["Petrol"], ["Manual", "Automatic"], 5),
    ("Toyota", "Innova Crysta", "MUV", 7, 22.0, ["Diesel"], ["Manual", "Automatic"], 5),
    ("Toyota", "Fortuner", "SUV", 7, 38.0, ["Petrol", "Diesel"], ["Manual", "Automatic"], 5),
    ("Toyota", "Glanza", "Hatchback", 5, 7.5, ["Petrol", "CNG"], ["Manual", "Automatic"], 3),
    ("Toyota", "Urban Cruiser Hyryder", "SUV", 5, 14.0, ["Petrol", "Hybrid"], ["Manual", "Automatic"], 4),
    ("Skoda", "Slavia", "Sedan", 5, 13.0, ["Petrol"], ["Manual", "Automatic"], 5),
    ("Skoda", "Kushaq", "SUV", 5, 13.5, ["Petrol"], ["Manual", "Automatic"], 5),
    ("Volkswagen", "Virtus", "Sedan", 5, 13.0, ["Petrol"], ["Manual", "Automatic"], 5),
    ("Volkswagen", "Taigun", "SUV", 5, 13.5, ["Petrol"], ["Manual", "Automatic"], 5),
    ("MG", "Hector", "SUV", 5, 16.0, ["Petrol", "Diesel"], ["Manual", "Automatic"], 4),
    ("MG", "ZS EV", "SUV", 5, 22.0, ["Electric"], ["Automatic"], 5),
    ("Renault", "Kwid", "Hatchback", 5, 4.5, ["Petrol"], ["Manual", "Automatic"], 1),
    ("Renault", "Kiger", "SUV", 5, 7.5, ["Petrol"], ["Manual", "Automatic"], 4),
]
COLORS = ["White", "Silver", "Grey", "Black", "Red", "Blue", "Brown"]
VARIANTS = ["Base", "Mid", "Top", "Top (O)"]
STATE = {"Delhi": "DL", "Gurgaon": "HR", "Noida": "UP", "Mumbai": "MH", "Pune": "MH", "Bangalore": "KA",
         "Hyderabad": "TS", "Chennai": "TN", "Kolkata": "WB", "Ahmedabad": "GJ", "Jaipur": "RJ"}

SCHEMA = """
DROP TABLE IF EXISTS cars;
CREATE TABLE cars (
  id INTEGER PRIMARY KEY, make TEXT NOT NULL, model TEXT NOT NULL, variant TEXT NOT NULL,
  body_type TEXT NOT NULL, fuel_type TEXT NOT NULL, transmission TEXT NOT NULL,
  year INTEGER NOT NULL, km_driven INTEGER NOT NULL, price INTEGER NOT NULL, seats INTEGER NOT NULL,
  safety_rating INTEGER NOT NULL, owners INTEGER NOT NULL, city TEXT NOT NULL, color TEXT NOT NULL,
  registration TEXT NOT NULL
);
"""

# One index per common way people narrow a search, each ending in price so
# "<filter> under X lakh" is a single index range scan.
INDEXES = """
CREATE INDEX idx_body_price ON cars(body_type, price);
CREATE INDEX idx_fuel_trans_price ON cars(fuel_type, transmission, price);
CREATE INDEX idx_make_price ON cars(make, price);
CREATE INDEX idx_city_price ON cars(city, price);
CREATE INDEX idx_price ON cars(price);
CREATE INDEX idx_year_km ON cars(year DESC, km_driven);
CREATE INDEX idx_km ON cars(km_driven);
CREATE INDEX idx_safety_price ON cars(safety_rating DESC, price);
"""

BATCH = 50_000


def make_car(rng: random.Random, i: int) -> tuple:
    make, model, body, seats, new_lakh, fuels, trans, ncap = rng.choice(CATALOG)
    fuel, tr = rng.choice(fuels), rng.choice(trans)
    year = rng.randint(2014, date.today().year)
    age = date.today().year - year
    km = max(1500, int(rng.gauss(11000, 3000) * max(age, 0.3)))
    if fuel == "Electric":
        km = int(km * 0.6)
    variant = rng.choice(VARIANTS)
    premium = 1 + 0.08 * VARIANTS.index(variant) + (0.08 if tr == "Automatic" else 0) + (0.07 if fuel in ("Diesel", "Hybrid") else 0)
    # ~12%/yr depreciation, extra hit for high mileage, small market noise
    value = new_lakh * premium * (0.88 ** age) * (1 - min(km / 1_000_000, 0.15)) * rng.uniform(0.93, 1.07)
    price = int(round(value * 1e5, -3))
    city = rng.choice(CITIES)
    reg = f"{STATE[city]}{rng.randint(1, 20):02d}{chr(65 + rng.randint(0, 25))}{chr(65 + rng.randint(0, 25))}{rng.randint(1000, 9999)}"
    owners = 1 if age < 3 else rng.choice([1, 1, 2, 2, 3])
    return (i, make, model, variant, body, fuel, tr, year, km, price, seats, ncap, owners, city, rng.choice(COLORS), reg)


def seed(count: int = 600, db: str = "data/cars.db") -> None:
    started = time.perf_counter()
    Path(db).parent.mkdir(parents=True, exist_ok=True)
    rng = random.Random(24)
    con = sqlite3.connect(db)
    con.execute("PRAGMA journal_mode = OFF")
    con.execute("PRAGMA synchronous = OFF")
    con.executescript(SCHEMA)
    for start in range(1, count + 1, BATCH):
        rows = [make_car(rng, i) for i in range(start, min(start + BATCH, count + 1))]
        con.executemany("INSERT INTO cars VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    con.executescript(INDEXES)  # building indexes after the inserts is much faster than before
    con.execute("ANALYZE")  # gives the query planner row counts to choose indexes with
    con.commit()
    con.close()
    print(f"Seeded {count:,} cars into {db} in {time.perf_counter() - started:.1f}s")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("count", nargs="?", type=int, default=600)
    ap.add_argument("--db", default="data/cars.db")
    args = ap.parse_args()
    seed(args.count, args.db)
