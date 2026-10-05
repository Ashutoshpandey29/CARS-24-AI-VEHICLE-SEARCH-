from app.parser.model import get_model
from app.parser.rules import rule_parse
from training import evaluate


def parse(q):
    return get_model().parse(q)


def test_model_is_shipped():
    assert get_model() is not None


def test_km_in_lakh_is_distance_not_price():
    f = parse("Maruti or Toyota automatic, max 1.2 lakh km")
    assert f.max_km == 120_000 and f.max_price is None
    assert f.makes == ["Maruti Suzuki", "Toyota"] and f.transmission == "Automatic"


def test_negated_fuel_is_excluded():
    f = parse("an SUV, not diesel")
    assert "Diesel" not in f.fuel_types and "Petrol" in f.fuel_types


def test_number_words_and_family_size():
    f = parse("something for a family of 7 that runs on diesel, budget twelve lakh")
    assert f.min_seats == 7 and f.max_price == 1_200_000 and f.fuel_types == ["Diesel"]


def test_city_alias():
    assert parse("suv in bengaluru").city == "Bangalore"


def test_quality_does_not_regress():
    # guards against a retrain that makes the model worse than the one in the README
    assert evaluate.score(parse)["exact"] >= 0.9
    assert evaluate.score(parse)["exact"] > evaluate.score(rule_parse)["exact"]
