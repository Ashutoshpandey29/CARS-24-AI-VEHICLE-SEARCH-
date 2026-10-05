def test_health(client):
    assert client.get("/health").json() == {"status": "ok", "parser": "model", "fallbacks": ["rules"]}


def test_results_respect_filters(client):
    r = client.get("/search", params={"q": "Diesel automatic cars below 80k km"}).json()
    assert r["parser"] == "model" and r["total"] > 0
    assert all(c["fuel_type"] == "Diesel" and c["transmission"] == "Automatic" and c["km_driven"] <= 80_000
               for c in r["results"])


def test_relaxes_when_nothing_matches(client):
    # the only Renault hatchback (Kwid) has a 1 star rating, so min_safety has to go
    r = client.get("/search", params={"q": "5 star renault hatchback"}).json()
    assert r["relaxed"] == ["min_safety"] and r["total"] > 0
    assert {c["model"] for c in r["results"]} == {"Kwid"}


def test_cursor_pages_match_offset_pages(client):
    q = "SUVs under 15 lakh cheapest"
    full = client.get("/search", params={"q": q, "limit": 60}).json()["results"]
    seen, cursor = [], None
    for _ in range(3):
        params = {"q": q, "limit": 20, **({"cursor": cursor} if cursor else {})}
        page = client.get("/search", params=params).json()
        seen += page["results"]
        cursor = page["next_cursor"]
    assert [c["id"] for c in seen] == [c["id"] for c in full]
    prices = [c["price"] for c in seen]
    assert prices == sorted(prices)


def test_last_page_has_no_cursor(client):
    r = client.get("/search", params={"q": "5 star renault hatchback", "limit": 100}).json()
    assert r["total"] <= 100 and r["next_cursor"] is None


def test_bad_cursor(client):
    r = client.get("/search", params={"q": "suv", "cursor": "not-a-cursor"})
    assert r.status_code == 400


def test_cursor_from_other_sort_rejected(client):
    cursor = client.get("/search", params={"q": "suv cheapest", "limit": 1}).json()["next_cursor"]
    r = client.get("/search", params={"q": "suv newest", "cursor": cursor})
    assert r.status_code == 400


def test_validation(client):
    assert client.get("/search", params={"q": "x"}).status_code == 422
    assert client.get("/search", params={"q": "suv", "limit": 500}).status_code == 422


def test_car_lookup(client):
    assert client.get("/cars/1").status_code == 200
    assert client.get("/cars/999999").status_code == 404


def test_home_page(client):
    r = client.get("/")
    assert r.status_code == 200 and "<html" in r.text.lower()
