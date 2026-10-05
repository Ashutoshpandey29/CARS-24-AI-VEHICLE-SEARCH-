"""Generate labelled training queries for the CRF tagger.

Each query is built from slot phrases ("under 15 lakh", "not diesel",
"for a family of 7" ...) in random order, with filler words around them.
Every token gets a BIO label, so the model learns which words fill which slot
from the words around them.

In production the same format would be filled from real search logs, labelled
by the LLM parser and spot-checked (distillation). See README, "Trained model".
"""
import random

from app.parser.model import tokenize

R = random.Random()

BODIES = ["suv", "suvs", "sedan", "sedans", "hatchback", "hatchbacks", "hatch", "muv", "mpv", "compact suv"]
FUELS = ["petrol", "diesel", "cng", "electric", "ev", "hybrid"]
MAKES = ["maruti", "maruti suzuki", "suzuki", "hyundai", "tata", "mahindra", "kia", "honda", "toyota", "skoda",
         "volkswagen", "vw", "mg", "renault"]
CITIES = ["delhi", "gurgaon", "gurugram", "noida", "mumbai", "bombay", "pune", "bangalore", "bengaluru",
          "hyderabad", "chennai", "kolkata", "ahmedabad", "jaipur"]
NUM_WORDS = ["two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve",
             "fifteen", "twenty", "twentyfive", "thirty"]
CARS = ["car", "cars", "vehicle", "vehicles", "options", "something", "one", "a car", "used car", "second hand car"]


def seg(text, label=None):
    """A phrase; every token gets `label` (BIO) or O."""
    toks = tokenize(text)
    if label is None:
        return [(t, "O") for t in toks]
    return [(t, ("B-" if i == 0 else "I-") + label) for i, t in enumerate(toks)]


def pick(*options):
    return R.choice(options)


def price():
    n = R.choice([1.5, 2, 2.5, 3, 3.5, 4, 4.5, 5, 5.5, 6, 7, 7.5, 8, 9, 10, 11, 12, 13, 14, 15, 16, 18, 20, 22, 25, 30, 35, 40])
    style = R.random()
    if style < 0.08:
        return f"{int(n * 100000)}"
    if style < 0.14:
        return f"{int(n * 100000):,}"
    if style < 0.24 and n == int(n) and int(n) <= 30:
        words = {2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten",
                 11: "eleven", 12: "twelve", 15: "fifteen", 20: "twenty", 25: "twentyfive", 30: "thirty"}
        if int(n) in words:
            return f"{words[int(n)]} {pick('lakh', 'lakhs', 'lac')}"
    if style < 0.28 and n >= 10:
        return f"{n / 100:g} {pick('cr', 'crore')}"
    num = f"{n:g}"
    return pick(f"{num} lakh", f"{num} lakhs", f"{num}l", f"{num} l", f"{num} lac", f"₹{num}l", f"₹{num} lakh",
                f"rs {num} lakh", f"{num}")


def km():
    n = R.choice([10, 15, 20, 25, 30, 40, 50, 60, 70, 75, 80, 90, 100, 120, 150])
    return pick(f"{n}k", f"{n} k", f"{n * 1000}", f"{n * 1000:,}", f"{n} thousand",
                f"{n / 100:g} lakh" if n >= 100 else f"{n}k", f"{n / 100:g} lac" if n >= 100 else f"{n},000")


def slot_body():
    b = R.choice(BODIES)
    if b == "compact suv":
        return seg("compact") + seg("suv", "BODY")
    return seg(b, "BODY")


def slot_fuel():
    f = R.choice(FUELS)
    return pick(lambda: seg(f, "FUEL"), lambda: seg(pick("running on", "that runs on", "with a")) + seg(f, "FUEL") +
                seg(pick("", "engine")), lambda: seg(f, "FUEL") + seg(pick("engine", "variant", "only", "")))()


def slot_fuel_not():
    f = R.choice(FUELS)
    return pick(lambda: seg(pick("not", "no", "non", "except", "without", "avoid", "anything but", "but not",
                                 "nothing", "excluding")) + seg(f, "FUEL_NOT"),
                lambda: seg(f, "FUEL_NOT") + seg(pick("not wanted", "not needed")))()


def slot_trans():
    if R.random() < 0.25:
        return seg(pick("no gears", "gearless", "without clutch", "no clutch", "self drive gearbox"), "TRANS")
    t = pick("automatic", "auto", "amt", "cvt", "dct", "manual", "automatic transmission", "manual transmission",
             "automatic gearbox", "manual gearbox")
    return pick(lambda: seg(t, "TRANS"), lambda: seg("with") + seg(t, "TRANS"))()


def slot_make():
    if R.random() < 0.2:
        a, b = R.sample(MAKES, 2)
        return seg(a, "MAKE") + seg(pick("or", "and", ",")) + seg(b, "MAKE")
    return seg(R.choice(MAKES), "MAKE")


def slot_city():
    return seg(pick("in", "near", "around", "located in", "available in", "from")) + seg(R.choice(CITIES), "CITY")


def slot_price_max():
    lead = pick("under", "below", "less than", "upto", "up to", "within", "max", "budget", "budget of", "budget is",
                "my budget is", "not more than", "no more than", "at most", "cheaper than", "maximum", "around",
                "budget around", "till")
    if R.random() < 0.1:
        return seg(price(), "PRICE_MAX") + seg(pick("budget", "max", "or less", "and below"))
    return seg(lead) + seg(price(), "PRICE_MAX")


def slot_price_min():
    return seg(pick("above", "over", "more than", "starting", "starting from", "at least", "min", "minimum",
                    "costlier than")) + seg(price(), "PRICE_MIN")


def slot_price_range():
    lo = R.choice([2, 3, 4, 5, 6, 7, 8, 10, 12, 15])
    hi = lo + R.choice([2, 3, 4, 5, 8, 10])
    unit = pick("lakh", "lakhs", "l", "lac")
    form = R.random()
    if form < 0.5:
        return seg(pick("between", "from", "in the range")) + seg(str(lo), "PRICE_MIN") + seg(pick("and", "to", "-")) + seg(f"{hi} {unit}", "PRICE_MAX")
    if form < 0.8:
        return seg(str(lo), "PRICE_MIN") + seg(pick("to", "-")) + seg(f"{hi} {unit}", "PRICE_MAX") + seg(pick("", "budget", "range"))
    return seg(pick("between", "from")) + seg(f"{lo} {unit}", "PRICE_MIN") + seg(pick("and", "to")) + seg(f"{hi} {unit}", "PRICE_MAX")


def slot_km():
    unit = pick("km", "kms", "kilometers", "km driven", "kilometres")
    form = R.random()
    if form < 0.6:
        return seg(pick("below", "under", "less than", "max", "within", "not more than", "driven less than",
                        "driven under", "upto", "odometer under")) + seg(km(), "KM_MAX") + seg(unit)
    if form < 0.8:
        return seg(km(), "KM_MAX") + seg(unit) + seg(pick("or less", "max", "and below"))
    return seg("driven") + seg(pick("below", "under", "less than")) + seg(km(), "KM_MAX")


def slot_year():
    y = str(R.randint(2012, 2025))
    form = R.random()
    if form < 0.55:
        return seg(pick("after", "since", "newer than", "from", "made after", "registered after", "model year",
                        "not before")) + seg(y, "YEAR_MIN")
    return seg(y, "YEAR_MIN") + seg(pick("or newer", "onwards", "and above", "or later", "model or newer", "plus"))


def slot_age():
    n = pick(str(R.randint(1, 8)), R.choice(["two", "three", "four", "five", "six"]))
    return pick(
        lambda: seg(pick("not older than", "less than", "under", "at most", "max", "no more than", "not more than")) + seg(n, "AGE_MAX") + seg(pick("years old", "years", "yrs old", "year old")),
        lambda: seg(n, "AGE_MAX") + seg(pick("years old or newer", "years or less", "years old max")),
    )()


def slot_seats():
    n = pick(*[str(x) for x in (4, 5, 6, 7, 8)], "seven", "six", "five", "eight")
    form = R.random()
    if form < 0.4:
        return seg(n, "SEATS") + seg(pick("seater", "seaters", "seats", "seat"))
    if form < 0.55:
        return seg(pick("seats", "seating for", "room for", "space for")) + seg(n, "SEATS") + seg(pick("", "people"))
    if form < 0.8:
        return seg(pick("for a", "for my", "for")) + seg("family", "FAMILY") + seg("of") + seg(n, "SEATS")
    return seg("for") + seg(n, "SEATS") + seg(pick("people", "persons", "passengers", "adults", "members"))


def slot_safety():
    form = R.random()
    if form < 0.35:
        return seg(f"{R.randint(3, 5)} star", "SAFETY") + seg(pick("", "rated", "rating", "safety", "ncap"))
    if form < 0.5:
        return seg(pick("at least", "minimum", "min")) + seg(f"{R.randint(3, 5)} star", "SAFETY") + seg(pick("safety", "rating"))
    if form < 0.8:
        return seg(pick("with")) + seg(pick("high safety", "good safety", "great safety"), "SAFETY") + seg(pick("rating", "ratings", ""))
    return seg(pick("safe"), "SAFETY")


def slot_family():
    return pick(lambda: seg("family", "FAMILY") + seg(pick("car", "cars", "vehicle", "")),
                lambda: seg(pick("for my", "for the", "for")) + seg("family", "FAMILY"))()


def slot_sort():
    label, words = R.choice([
        ("SORT_PRICE", ["cheapest", "lowest price", "least expensive", "budget friendly", "sort by price", "low to high"]),
        ("SORT_PRICE_DESC", ["most expensive", "costliest", "high to low", "premium first"]),
        ("SORT_NEW", ["newest", "latest", "most recent", "newest first", "latest model"]),
        ("SORT_KM", ["least driven", "lowest km", "low mileage", "least kms"]),
        ("SORT_SAFE", ["safest", "most safe", "safest first"]),
    ])
    return seg(R.choice(words), label)


PRE = ["", "", "", "show", "show me", "find", "find me", "i want", "i need", "looking for", "need", "any", "get me",
       "list", "search", "want to buy", "suggest", "recommend", "please show", "can you find", "hi i am looking for",
       "do you have", "is there a"]
FILLER = ["", "", "", "", "please", "urgently", "for daily commute", "for office use", "in good condition",
          "white colour", "for my son", "single owner preferred", "good condition", "asap"]
JOIN = ["", "", "", "with", "and", ",", "that is", "which is", "having"]

PRE_NOUN = [slot_fuel, slot_trans, slot_make, slot_family, slot_sort, slot_safety]
POST_NOUN = [slot_price_max, slot_price_min, slot_price_range, slot_km, slot_year, slot_age, slot_city, slot_seats,
             slot_fuel_not, slot_trans, slot_safety, slot_fuel]


def example() -> list[tuple[str, str]]:
    out = seg(R.choice(PRE))
    for fn in R.sample(PRE_NOUN, R.choice([0, 0, 1, 1, 2, 3])):
        out += fn()
    out += slot_body() if R.random() < 0.55 else seg(R.choice(CARS))
    post = R.sample(POST_NOUN, R.choice([0, 1, 1, 2, 2, 3, 4]))
    labels_used = set()
    for fn in post:
        if fn in (slot_price_max, slot_price_min, slot_price_range) and labels_used & {"price"}:
            continue
        if fn in (slot_year, slot_age) and labels_used & {"year"}:
            continue
        if fn in (slot_price_max, slot_price_min, slot_price_range):
            labels_used.add("price")
        if fn in (slot_year, slot_age):
            labels_used.add("year")
        out += seg(R.choice(JOIN)) + fn()
    out += seg(R.choice(FILLER))
    if not out:
        return example()
    return out


def generate(n: int, seed: int = 7) -> list[list[tuple[str, str]]]:
    R.seed(seed)
    return [example() for _ in range(n)]
