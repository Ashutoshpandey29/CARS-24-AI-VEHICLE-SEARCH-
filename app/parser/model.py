"""Our own trained parser: a CRF sequence tagger.

The query is split into tokens and the model labels each one with the slot it
fills (BIO tags), e.g.

    not   diesel      under  12          lakh        1.2       lakh      km
    O     B-FUEL_NOT  O      B-PRICE_MAX I-PRICE_MAX B-KM_MAX  I-KM_MAX  O

The labelled spans are then turned into Filters by small normalisers
(number words, lakh/crore/k units, aliases such as "bengaluru").

Because the model labels a token from its context (the words around it), it
picks up things a fixed regex cannot: "1.2 lakh" followed by "km" is a
distance, not a price; "diesel" after "not" is an exclusion.

Train with `python scripts/train_model.py`. Runs on CPU in about a millisecond
per query, needs no network and costs nothing per query.
"""
import logging
import re
import threading
from datetime import date
from pathlib import Path
from typing import Optional

from app.config import get_settings
from app.schemas import Filters

log = logging.getLogger(__name__)

DEFAULT_MODEL_PATH = Path(__file__).resolve().parents[2] / "models" / "query_tagger.crfsuite"

_TOKEN = re.compile(r"\d+(?:\.\d+)?|[a-z]+|₹")

NUM_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
    "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
    "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20, "twentyfive": 25, "thirty": 30,
    "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90, "hundred": 100,
}
UNITS = {"l": 1e5, "lac": 1e5, "lacs": 1e5, "lakh": 1e5, "lakhs": 1e5, "cr": 1e7, "crore": 1e7, "crores": 1e7,
         "k": 1e3, "thousand": 1e3}

BODY = {"suv": "SUV", "suvs": "SUV", "sedan": "Sedan", "sedans": "Sedan", "hatchback": "Hatchback",
        "hatchbacks": "Hatchback", "hatch": "Hatchback", "muv": "MUV", "muvs": "MUV", "mpv": "MUV", "mpvs": "MUV"}
FUEL = {"petrol": "Petrol", "gasoline": "Petrol", "diesel": "Diesel", "cng": "CNG", "electric": "Electric",
        "ev": "Electric", "evs": "Electric", "hybrid": "Hybrid"}
ALL_FUELS = ["Petrol", "Diesel", "CNG", "Electric", "Hybrid"]
MAKE = {"maruti": "Maruti Suzuki", "suzuki": "Maruti Suzuki", "hyundai": "Hyundai", "tata": "Tata",
        "mahindra": "Mahindra", "kia": "Kia", "honda": "Honda", "toyota": "Toyota", "skoda": "Skoda",
        "volkswagen": "Volkswagen", "vw": "Volkswagen", "mg": "MG", "renault": "Renault"}
CITY = {"delhi": "Delhi", "gurgaon": "Gurgaon", "gurugram": "Gurgaon", "noida": "Noida", "mumbai": "Mumbai",
        "bombay": "Mumbai", "pune": "Pune", "bangalore": "Bangalore", "bengaluru": "Bangalore",
        "hyderabad": "Hyderabad", "chennai": "Chennai", "madras": "Chennai", "kolkata": "Kolkata",
        "calcutta": "Kolkata", "ahmedabad": "Ahmedabad", "jaipur": "Jaipur"}
NEGATIONS = {"not", "no", "non", "except", "without", "avoid", "but", "excluding", "nothing"}
SORTS = {"SORT_PRICE": "price_asc", "SORT_PRICE_DESC": "price_desc", "SORT_NEW": "year_desc",
         "SORT_KM": "km_asc", "SORT_SAFE": "safety_desc"}


def tokenize(text: str) -> list[str]:
    text = text.lower()
    text = re.sub(r"(?<=\d),(?=\d)", "", text)  # 8,00,000 -> 800000
    return _TOKEN.findall(text)


def _shape(tok: str) -> str:
    if re.fullmatch(r"20\d\d", tok):
        return "YEAR"
    if re.fullmatch(r"\d+\.\d+", tok):
        return "DEC"
    if tok.isdigit():
        return "NUM" if len(tok) < 4 else "BIGNUM"
    if tok in NUM_WORDS:
        return "NUMWORD"
    return "WORD"


def _lex(tok: str) -> str:
    for name, table in (("body", BODY), ("fuel", FUEL), ("make", MAKE), ("city", CITY), ("unit", UNITS)):
        if tok in table:
            return name
    return "none"


def token_features(tokens: list[str], i: int) -> dict:
    tok = tokens[i]
    f = {"bias": 1.0, "w": tok, "shape": _shape(tok), "lex": _lex(tok), "suf3": tok[-3:]}
    for d in (-3, -2, -1, 1, 2, 3):
        j = i + d
        if 0 <= j < len(tokens):
            f[f"w{d:+d}"] = tokens[j]
            f[f"shape{d:+d}"] = _shape(tokens[j])
            f[f"lex{d:+d}"] = _lex(tokens[j])
        else:
            f[f"w{d:+d}"] = "<pad>"
    f["neg_before"] = any(t in NEGATIONS for t in tokens[max(0, i - 3):i])
    f["first"] = i == 0
    f["last"] = i == len(tokens) - 1
    return f


def sent_features(tokens: list[str]) -> list[dict]:
    return [token_features(tokens, i) for i in range(len(tokens))]


def spans(tokens: list[str], tags: list[str]) -> list[tuple[str, list[str]]]:
    out: list[tuple[str, list[str]]] = []
    for tok, tag in zip(tokens, tags):
        if tag == "O":
            continue
        kind, label = tag.split("-", 1)
        if kind == "B" or not out or out[-1][0] != label:
            out.append((label, [tok]))
        else:
            out[-1][1].append(tok)
    return out


def _number(tokens: list[str]) -> tuple[Optional[float], Optional[str]]:
    num, unit = None, None
    for t in tokens:
        if num is None and re.fullmatch(r"\d+(?:\.\d+)?", t):
            num = float(t)
        elif num is None and t in NUM_WORDS:
            num = float(NUM_WORDS[t])
        elif t in UNITS and unit is None:
            unit = t
    return num, unit


def _money(num: float, unit: Optional[str]) -> int:
    if unit:
        return int(num * UNITS[unit])
    return int(num * 1e5) if num < 1000 else int(num)  # "under 15" in a budget means 15 lakh


def to_filters(tokens: list[str], tags: list[str]) -> Filters:
    f = Filters()
    found = spans(tokens, tags)
    price_units = [_number(toks)[1] for label, toks in found if label in ("PRICE_MIN", "PRICE_MAX")]
    shared_unit = next((u for u in price_units if u), None)  # "between 5 and 9 lakh": 5 is lakh too
    excluded: list[str] = []

    for label, toks in found:
        text = " ".join(toks)
        num, unit = _number(toks)
        if label == "BODY":
            f.body_types += [BODY[t] for t in toks if t in BODY and BODY[t] not in f.body_types]
        elif label == "FUEL":
            f.fuel_types += [FUEL[t] for t in toks if t in FUEL and FUEL[t] not in f.fuel_types]
        elif label == "FUEL_NOT":
            excluded += [FUEL[t] for t in toks if t in FUEL]
        elif label == "TRANS":
            f.transmission = "Manual" if re.search(r"manual|stick|clutch pedal", text) else "Automatic"
        elif label == "MAKE":
            f.makes += [MAKE[t] for t in toks if t in MAKE and MAKE[t] not in f.makes]
        elif label == "CITY":
            f.city = next((CITY[t] for t in toks if t in CITY), f.city)
        elif label in ("PRICE_MAX", "PRICE_MIN") and num is not None:
            value = _money(num, unit or shared_unit)
            setattr(f, "max_price" if label == "PRICE_MAX" else "min_price", value)
        elif label == "KM_MAX" and num is not None:
            f.max_km = int(num * UNITS[unit]) if unit else int(num if num >= 1000 else num * 1000)
        elif label == "YEAR_MIN" and num is not None and 2000 <= num <= 2100:
            f.min_year = int(num)
        elif label == "AGE_MAX" and num is not None and num < 30:
            f.min_year = date.today().year - int(num)
        elif label == "SEATS" and num is not None and 2 <= num <= 9:
            f.min_seats = int(num)
        elif label == "SAFETY":
            f.min_safety = int(num) if num is not None and 0 <= num <= 5 else 4
        elif label == "FAMILY":
            f.min_seats = max(f.min_seats or 0, 5)
            if not f.body_types:
                f.body_types = ["SUV", "MUV", "Sedan"]
        elif label in SORTS:
            f.sort = SORTS[label]

    if excluded and not f.fuel_types:
        f.fuel_types = [x for x in ALL_FUELS if x not in excluded]
    return f


class ModelParser:
    def __init__(self, path: Path):
        import pycrfsuite

        self._tagger = pycrfsuite.Tagger()
        self._tagger.open(str(path))
        self._lock = threading.Lock()  # the C tagger is not thread-safe

    def tag(self, text: str) -> tuple[list[str], list[str]]:
        tokens = tokenize(text)
        if not tokens:
            return tokens, []
        with self._lock:
            tags = self._tagger.tag(sent_features(tokens))
        return tokens, tags

    def parse(self, text: str) -> Filters:
        return to_filters(*self.tag(text))


_parser: Optional[ModelParser] = None
_loaded = False


def get_model() -> Optional[ModelParser]:
    global _parser, _loaded
    if not _loaded:
        _loaded = True
        configured = get_settings().model_path
        p = Path(configured) if configured else DEFAULT_MODEL_PATH
        if p.exists():
            try:
                _parser = ModelParser(p)
            except Exception as e:  # missing library or corrupt file: fall back to rules
                log.warning("could not load trained model %s: %s", p, e)
        else:
            log.info("no trained model at %s, run `python scripts/train_model.py`", p)
    return _parser


def model_parse(text: str) -> Optional[Filters]:
    model = get_model()
    return model.parse(text) if model else None
