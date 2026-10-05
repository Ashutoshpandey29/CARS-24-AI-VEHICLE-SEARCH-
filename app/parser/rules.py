"""Regex parser. Used when no API key is set or the LLM call fails.

Handles the common phrasings (body type, fuel, gearbox, budget in lakh/crore,
km, year, seats, safety, make, city, sort words). Anything it does not
recognise is ignored, which is why the LLM parser gives better results on
free-form queries.
"""
import re
from typing import Optional

from app.schemas import Filters
from app.vocab import CITIES, MAKES

_UNIT = {"l": 1e5, "lac": 1e5, "lakh": 1e5, "lakhs": 1e5, "cr": 1e7, "crore": 1e7, "k": 1e3}
_NUM = r"(\d+(?:\.\d+)?)\s*(lakhs?|lac|l|crore|cr|k)?\b"
_LT = r"(?:under|below|less than|upto|up to|within|max|<)"
_GT = r"(?:above|over|more than|min|from|>)"
_WORDS = {
    "body_types": {"SUV": r"\bsuvs?\b", "Sedan": r"\bsedans?\b", "Hatchback": r"\bhatch(?:back)?s?\b", "MUV": r"\b(?:muv|mpv)s?\b"},
    "fuel_types": {"Petrol": r"\bpetrol\b", "Diesel": r"\bdiesel\b", "CNG": r"\bcng\b", "Electric": r"\b(?:electric|ev)s?\b", "Hybrid": r"\bhybrid\b"},
}
_SORTS = [(r"cheapest|budget|lowest price", "price_asc"), (r"newest|latest", "year_desc"),
          (r"low mileage|least driven|low km", "km_asc"), (r"safest", "safety_desc")]


def _money(num: str, unit: Optional[str]) -> int:
    n = float(num)
    if unit:
        return int(n * _UNIT[unit])
    return int(n * 1e5) if n < 1000 else int(n)  # a bare "15" next to "under" means 15 lakh


def rule_parse(q: str) -> Filters:
    t = q.lower().replace("₹", " ").replace("rs.", " ").replace(",", "")
    f = Filters()

    # km goes first and is removed from the text, so "80k km" is not read as a price
    if m := re.search(rf"(?:{_LT}\s*)?(\d+(?:\.\d+)?)\s*(k)?\s*(?:km|kms|kilometers?)\b", t):
        f.max_km = int(float(m.group(1)) * (1000 if m.group(2) else 1))
        t = t.replace(m.group(0), " ")
    if m := re.search(rf"between\s*{_NUM}\s*(?:and|-|to)\s*{_NUM}", t):
        f.min_price, f.max_price = _money(m[1], m[2] or m[4]), _money(m[3], m[4])
    else:
        if m := re.search(rf"{_LT}\s*{_NUM}", t):
            f.max_price = _money(m[1], m[2])
        if m := re.search(rf"{_GT}\s*{_NUM}", t):
            if not re.fullmatch(r"20\d\d", m[1]):
                f.min_price = _money(m[1], m[2])
    if m := re.search(r"(?:after|since|newer than|from|>)\s*(20\d\d)|(20\d\d)\s*(?:or|and)\s*(?:newer|later|above)", t):
        f.min_year = int(m[1] or m[2])

    for field, words in _WORDS.items():
        setattr(f, field, [k for k, rx in words.items() if re.search(rx, t)])
    if re.search(r"\b(?:automatic|auto|amt|cvt|dct)\b", t):
        f.transmission = "Automatic"
    elif re.search(r"\bmanual\b", t):
        f.transmission = "Manual"

    if m := re.search(r"\b([4-8])\s*-?\s*seater\b", t):
        f.min_seats = int(m[1])
    if re.search(r"\bfamily\b", t):
        f.min_seats = max(f.min_seats or 0, 5)
        f.body_types = f.body_types or ["SUV", "MUV", "Sedan"]
    if re.search(r"5\s*-?\s*star", t):
        f.min_safety = 5
    elif re.search(r"\bsafe(?:ty|st)?\b|\bncap\b", t):
        f.min_safety = 4

    f.makes = [mk for mk in MAKES if re.search(rf"\b{mk.lower().split()[0]}\b", t)]
    f.city = next((c for c in CITIES if re.search(rf"\b{c.lower()}\b", t)), None)
    f.sort = next((s for rx, s in _SORTS if re.search(rx, t)), None)
    return f
