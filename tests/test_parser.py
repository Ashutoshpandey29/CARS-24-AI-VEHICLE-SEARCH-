from app.parser import rule_parse


def test_suv_under_15l():
    f = rule_parse("Show SUVs under ₹15L")
    assert f.body_types == ["SUV"] and f.max_price == 1_500_000


def test_diesel_automatic_km():
    f = rule_parse("Diesel automatic cars below 80k km")
    assert f.fuel_types == ["Diesel"] and f.transmission == "Automatic"
    assert f.max_km == 80_000 and f.max_price is None


def test_family_safety():
    f = rule_parse("Family cars with high safety ratings")
    assert f.min_seats == 5 and f.min_safety == 4 and "SUV" in f.body_types


def test_range_year_city_make():
    f = rule_parse("hyundai between 5 and 9 lakh after 2019 in pune, cheapest")
    assert (f.min_price, f.max_price, f.min_year) == (500_000, 900_000, 2019)
    assert f.makes == ["Hyundai"] and f.city == "Pune" and f.sort == "price_asc"


def test_seven_seater():
    f = rule_parse("7 seater diesel under 20L")
    assert f.min_seats == 7 and f.fuel_types == ["Diesel"] and f.max_price == 2_000_000
