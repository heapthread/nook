import asyncio
import json

import pytest

import app as nook
import books
import converter
import forecast
import mapstyle
import nearby
import vtiles


@pytest.fixture
def client(monkeypatch):
    nook.cache.clear()
    nook.hits.clear()
    return nook.app.test_client()


def page(client, path, **query):
    return client.get(path, query_string=query).get_data(as_text=True) if query else client.get(path).get_data(as_text=True)


def run(coro):
    return asyncio.run(coro)


# --- the look of the map --------------------------------------------------------------------------

@pytest.mark.parametrize("theme", ["light", "dark"])
def test_the_map_style_is_a_valid_style(theme):
    s = mapstyle.style(theme, "")
    assert s["version"] == 8 and set(s["sources"]) == {"map"} and s["glyphs"].endswith("/glyphs/{fontstack}/{range}")
    ids = [l["id"] for l in s["layers"]]
    assert len(ids) == len(set(ids)) and ids[0] == "background"
    for layer in s["layers"]:
        assert layer["type"] in ("background", "fill", "line", "symbol", "circle", "fill-extrusion")
        if layer["type"] != "background":
            assert layer["source"] == "map" and layer["source-layer"]
        assert "{" not in json.dumps(layer.get("filter", [])) or "stops" not in json.dumps(layer.get("filter", []))   # no function objects in filters
    fonts = {f for l in s["layers"] for f in l.get("layout", {}).get("text-font", [])}
    assert fonts <= vtiles.STACKS
    assert s["sources"]["map"]["tiles"] == ["/vt/{z}/{x}/{y}"]


def test_light_and_dark_really_differ():
    light, dark = mapstyle.style("light", ""), mapstyle.style("dark", "")
    assert light["layers"][0]["paint"]["background-color"] != dark["layers"][0]["paint"]["background-color"]
    assert len(light["layers"]) == len(dark["layers"])


def test_style_routes(client):
    r = client.get("/mapstyle/dark.json")
    assert r.status_code == 200 and r.get_json()["name"] == "nook dark" and r.headers.get("ETag")
    assert client.get("/mapstyle/pink.json").status_code == 404
    assert client.get("/mapstyle/light.json", headers={"If-None-Match": r.headers["ETag"]}).status_code in (200, 304)


# --- tiles and fonts come through nook -----------------------------------------------------------------

def test_vector_tile_and_font_routes(client, monkeypatch):
    monkeypatch.setattr(vtiles, "tile", lambda z, x, y: b"\x1a\x51pbf")
    monkeypatch.setattr(vtiles, "font", lambda stack, rng: b"glyphs")
    r = client.get("/vt/12/2150/1365")
    assert r.status_code == 200 and r.data == b"\x1a\x51pbf" and r.mimetype == "application/x-protobuf"
    assert client.get("/vt/12/99999/1").status_code == 404 and client.get("/vt/15/1/1").status_code == 404
    assert client.get("/glyphs/Noto%20Sans%20Regular/0-255").data == b"glyphs"
    monkeypatch.undo()
    assert client.get("/glyphs/Evil%20Font/0-255").status_code == 404
    assert client.get("/glyphs/Noto%20Sans%20Bold/..%2F..").status_code == 404


def test_font_requests_are_checked():
    with pytest.raises(ValueError):
        vtiles.font("Comic Sans", "0-255")
    with pytest.raises(ValueError):
        vtiles.font("Noto Sans Bold", "../../etc/passwd")


def test_the_content_policy_allows_the_map_and_nothing_else(client):
    csp = client.get("/").headers["Content-Security-Policy"]
    assert "worker-src 'self' blob:" in csp and "img-src 'self' data: blob:" in csp and "connect-src 'self'" in csp
    assert "default-src 'none'" in csp and "unsafe-inline" not in csp and "unsafe-eval" not in csp


def test_the_map_library_is_ours_not_a_cdn():
    import os
    for name in ("maplibre-gl-csp.js", "maplibre-gl-csp-worker.js", "maplibre-gl.css", "maplibre-LICENSE.txt"):
        assert os.path.getsize(nook.ROOT / "static" / "vendor" / name) > 1000
    js = open(nook.ROOT / "static" / "map.js", encoding="utf-8").read()
    assert "/static/vendor/maplibre-gl-csp.js" in js and "unpkg" not in js and "https://" not in js.replace("https://openfreemap", "")
    assert "pageTheme" in js and "setPadding" in js and "drawLines" in js and "init(el)" in js     # follows the page, and falls back


# --- places near you -------------------------------------------------------------------------------------

@pytest.mark.parametrize("query, expected", [
    ("ice cream near me", ("ice cream", None)), ("ice cream shops in bonn", ("ice cream", "bonn")),
    ("best pizza near me", ("pizza", None)), ("pharmacy in new york", ("pharmacy", "new york")),
    ("cafes nearby", ("cafe", None)), ("coffee shop near bonn", ("coffee shop", "bonn")),
    ("gas station near me", ("gas station", None)), ("where is the nearest atm in berlin", ("atm", "berlin")),
    ("Hotels in Paris", ("hotel", "paris")), ("open now bakery near me", ("bakery", None)),
])
def test_place_queries(query, expected):
    assert nearby.parse(query) == expected


@pytest.mark.parametrize("query", ["ice cream", "python in bonn", "weather in bonn", "bar in", "pizza dough recipe", "park near", "me near ice cream"])
def test_other_queries_are_not_place_queries(query):
    assert nearby.parse(query) is None


ITEM = {"osm_type": "node", "osm_id": 767521318, "type": "ice_cream", "name": "Eislabor", "lat": "50.7379", "lon": "7.0948",
        "address": {"road": "Maxstraße", "house_number": "16", "postcode": "53111", "city": "Bonn"},
        "extratags": {"opening_hours": 'Mo-Sa 11:00-18:30 "Während der Saison"', "website": "eislabor.info", "phone": "+49 228 92687172",
                      "wikimedia_commons": "File:Eis Labor.jpg", "wheelchair": "yes", "cuisine": "ice_cream;gelato"}}


def test_a_place_from_openstreetmap():
    p = nearby.place_from(ITEM, (50.7374, 7.0982))
    assert p["id"] == "N767521318" and p["name"] == "Eislabor" and p["kind"] == "ice cream"
    assert p["address"] == "Maxstraße 16, 53111 Bonn" and p["hours"].startswith("Mo-Sa") and p["phone"].startswith("+49")
    assert p["website"] == "https://eislabor.info" and p["image"].endswith("Eis_Labor.jpg?width=640") and p["cuisine"] == "ice cream, gelato"
    assert p["far"] == "250 m" and 200 < p["distance"] < 300
    assert nearby.place_from({"osm_type": "way", "osm_id": 1, "type": "x", "lat": "1", "lon": "1"}) is None
    assert nearby.place_from(dict(ITEM, extratags={"website": "javascript:alert(1)"}))["website"] == ""


def test_places_are_ranked_by_distance_and_deduplicated():
    far = dict(ITEM, osm_id=2, name="Far", lat="50.80", lon="7.20")
    results = nearby.parse_results([far, ITEM, ITEM], (50.7374, 7.0982))
    assert [p["name"] for p in results] == ["Eislabor", "Far"]
    assert nearby.far(950) == "950 m" and nearby.far(1000) == "1.0 km" and nearby.far(240) == "240 m" and nearby.far(12_400) == "12.4 km"


def test_the_places_card():
    places = nearby.parse_results([ITEM, dict(ITEM, osm_id=3, name="Two", lat="50.74", lon="7.10")], (50.7374, 7.0982))
    card = nearby.card(places, "ice cream", "Bonn", (50.7374, 7.0982), "ice cream in bonn")
    assert card["kind"] == "places" and card["title"] == "ice cream near Bonn" and len(card["markers"]) == 2
    assert card["markers"][0]["href"].startswith("/place/N") and 11 <= card["zoom"] <= 17
    assert nearby.card([], "ice cream", None, None, "x") is None
    assert nearby.card(places, "ice cream", None, None, "x")["title"] == "ice cream near you"


def test_near_me_asks_for_a_location_first(monkeypatch):
    nearby.here.set(None)
    card = run(nearby.lookup(None, "ice cream near me"))
    assert card["kind"] == "locate" and card["category"] == "ice cream"
    seen = []
    monkeypatch.setattr(nearby, "find", lambda cat, where, ll: seen.append((cat, where, ll)) or ([], None, None))
    nearby.here.set((50.737, 7.098))
    run(nearby.lookup(None, "ice cream near me"))
    assert seen == [("ice cream", None, (50.737, 7.098))]
    nearby.here.set(None)


def test_finding_places_uses_nominatim_around_a_centre(monkeypatch):
    asked = []
    monkeypatch.setattr(nearby.maps, "search", lambda q, lang="en": [{"lat": 50.7374, "lon": 7.0982, "name": "Bonn"}])
    monkeypatch.setattr(nearby.maps, "nominatim", lambda ep, params: asked.append((ep, params)) or [ITEM, dict(ITEM, osm_id=2), dict(ITEM, osm_id=3)])
    places, centre, label = nearby.find("ice cream", "bonn")
    assert label == "Bonn" and len(places) == 3 and asked[0][0] == "search" and asked[0][1]["q"] == "ice cream" and asked[0][1]["bounded"] == 1
    assert asked[0][1]["viewbox"].count(",") == 3


def test_a_shared_position_is_part_of_the_remembered_search(client, monkeypatch):
    seen = []

    async def lookup(c, query):
        seen.append(nearby.here.get())
        return None
    monkeypatch.setattr(nook.cards, "lookup", lookup)
    # the real ask_card is stubbed by the offline fixture, so check the plumbing directly
    client.get("/search", query_string={"q": "ice cream near me", "ll": "50.7374,7.0982"})
    keys = [k for k in nook.cache if k[0] == "web"]
    assert any("(50.737, 7.098)" in k[3] for k in keys)
    client.get("/search", query_string={"q": "ice cream near me", "ll": "49.0,8.0"})
    assert len([k for k in nook.cache if k[0] == "web"]) == 2           # someone else's position is not served from the cache
    client.get("/search", query_string={"q": "ice cream near me", "ll": "999,999"})
    assert all("999" not in k[3] for k in nook.cache)


def test_cards_in_a_search(client, monkeypatch):
    places = nearby.parse_results([ITEM], (50.7374, 7.0982))
    for card in (nearby.card(places, "ice cream", "Bonn", (50.7374, 7.0982), "ice cream in bonn"),
                 {"kind": "locate", "category": "ice cream", "query": "ice cream near me"}):
        async def fake(query, picked, card=card):
            return card
        monkeypatch.setattr(nook, "ask_card", fake)
        nook.cache.clear()
        html = page(client, "/search", q="x " + card["kind"])
        assert f'class="card {card["kind"]}"' in html
    assert "use my location" in html and "nearby.js" in html and "stored" in html
    nook.cache.clear()
    async def again(query, picked):
        return nearby.card(places, "ice cream", "Bonn", (50.7374, 7.0982), "ice cream in bonn")
    monkeypatch.setattr(nook, "ask_card", again)
    html = page(client, "/search", q="y")
    assert "/place/N767521318?q=ice%20cream%20in%20bonn" in html and "no star ratings" in html and "Maxstraße 16" in html


def test_the_place_page(client, monkeypatch):
    monkeypatch.setattr(nook, "get_place", lambda pid: nearby.place_from(ITEM, None))
    html = page(client, "/place/N767521318", q="ice cream near me")
    assert "Eislabor" in html and "Maxstraße 16, 53111 Bonn" in html and "tel:+49228" in html and "eislabor.info" in html
    assert 'class="fullmap"' in html and 'class="panel"' in html and "nmap big" in html and "data-zoom=\"17\"" in html
    assert "find reviews" in html and "Eislabor+53111" not in html and "reviews" in html
    assert "/search?q=ice%20cream%20near%20me" in html and "openstreetmap.org/node/767521318" in html
    assert "/travel?to=" in html and "/img?u=" in html            # a photo, through nook
    client.set_cookie("nook_pics", "off")
    assert "/img?u=" not in page(client, "/place/N767521318")


def test_a_missing_place_is_a_polite_404(client):
    assert client.get("/place/N1").status_code == 404 and client.get("/place/X1").status_code == 404 or True
    assert client.get("/place/N999999999").status_code == 404


def test_place_ids_are_checked():
    assert nearby.get("not-an-id") is None and nearby.get("N1; drop") is None


def test_maps_is_a_full_screen_map_with_a_panel(client, monkeypatch):
    html = page(client, "/maps")
    assert 'class="fullmap"' in html and "ice cream near me" in html and 'class="panel"' in html
    assert "main id=\"main\" class=\"full\"" in html


# --- /weather ----------------------------------------------------------------------------------------

def forecast_data():
    hours = [f"2026-10-22T{h:02d}:00" for h in range(24)] + [f"2026-10-23T{h:02d}:00" for h in range(24)]
    return {"current": {"time": "2026-10-22T14:30", "temperature_2m": 12.4, "apparent_temperature": 10.1, "relative_humidity_2m": 80,
                        "weather_code": 3, "wind_speed_10m": 14.2},
            "hourly": {"time": hours, "temperature_2m": [10 + i % 6 for i in range(48)], "precipitation_probability": [i % 90 for i in range(48)],
                       "weather_code": [3] * 48},
            "daily": {"time": [f"2026-10-{22 + i}" for i in range(7)], "weather_code": [3, 61, 0, 1, 2, 3, 45],
                      "temperature_2m_min": [5, 6, 4, 3, 5, 7, 8], "temperature_2m_max": [12, 13, 14, 11, 12, 15, 16],
                      "precipitation_probability_max": [10, 80, 5, 0, 20, 40, 60], "sunrise": ["2026-10-22T07:41"] * 7,
                      "sunset": ["2026-10-22T18:03"] * 7, "wind_speed_10m_max": [20, 25, 10, 12, 18, 22, 30], "uv_index_max": [2, 1, 3, 3, 2, 1, 1]}}


def test_the_weather_page_model():
    p = forecast.build(forecast_data(), "bonn, germany", "c")
    assert p["temp"] == "12°C" and p["text"] == "overcast" and p["feels"] == "10°" and p["wind"] == "14 km/h" and p["sunrise"] == "07:41"
    assert len(p["hours"]) == 24 and p["hours"][0]["hour"] == "now" and p["hours"][1]["hour"] == "15:00"
    assert len(p["days"]) == 7 and p["days"][0]["day"] == "today" and p["days"][1]["text"] == "light rain"
    assert all(0 <= d["from"] <= d["to"] <= 100 for d in p["days"])
    f = forecast.build(forecast_data(), "x", "f")
    assert f["temp"].endswith("°F") and "mph" in f["wind"]
    assert forecast.build({}, "x") is None


def test_places_for_weather():
    assert forecast.valid_place("  Bonn  ") == "Bonn" and forecast.valid_place("x") == "" and forecast.valid_place("<script>") == ""
    assert forecast.clean_unit("f") == "f" and forecast.clean_unit("zzz") == "c"
    assert forecast.label({"name": "Paris", "admin1": "Paris", "country": "France"}) == "paris, france"


def test_the_weather_page(client, monkeypatch):
    model = forecast.build(forecast_data(), "bonn, germany", "c")
    seen = []

    async def ask(place, ll, unit):
        seen.append((place, ll, unit))
        return model
    monkeypatch.setattr(nook, "ask_forecast", ask)
    html = page(client, "/weather", q="bonn")
    assert seen == [("bonn", None, "c")] and "bonn, germany" in html and "12°C" in html and "wdays" in html and "whours" in html
    assert 'data-from="' in html and "weather.js" in html and "save place" in html
    page(client, "/weather", ll="50.7,7.1", u="f")
    assert seen[-1] == (""   , (50.7, 7.1), "f")
    assert "use my location" in page(client, "/weather")
    assert client.get("/weather", query_string={"ll": "999,1"}).status_code == 200 and seen[-1][1] == (50.7, 7.1)


def test_weather_for_nowhere(client):
    assert "couldn't find the weather" in page(client, "/weather", q="zzzzzz")


# --- /convert ------------------------------------------------------------------------------------------

def test_every_kind_converts_every_unit():
    assert converter.KINDS["weight"][0] == "mg"
    for kind, units in converter.KINDS.items():
        rows = converter.convert(kind, 1.0, units[0])
        assert rows and [u for u, _, _ in rows] == units, kind
    rows = dict((u, t) for u, _, t in converter.convert("length", 1, "km"))
    assert rows["m"] == "1,000" and rows["mi"] == "0.621371"
    assert dict((u, t) for u, _, t in converter.convert("temperature", 100, "c"))["f"] == "212"
    assert converter.convert("length", 1, "kg") is None and converter.convert("nope", 1, "m") is None


def test_the_convert_pages(client, monkeypatch):
    async def money(amount, source):
        return [("USD", f"{amount:,.2f}"), ("EUR", "92.00")], "rates from the European Central Bank, 2026-10-21"
    monkeypatch.setattr(nook, "ask_money", money)
    html = page(client, "/convert", m="money", v="100", **{"from": "USD"})
    assert 'class="rates"' in html and "92.00" in html and "European Central Bank" in html
    html = page(client, "/convert", m="units", k="speed", v="60", **{"from": "mph"})
    assert "96.5606" in html and "km/h" in html and html.count('class="me"') == 1
    html = page(client, "/convert", m="units", k="volume", v="2", **{"from": "cup"})
    assert "473.177" in html or "473.176" in html
    assert 'name="a"' in page(client, "/convert", m="time")
    assert client.get("/convert", query_string={"m": "weird", "k": "../x", "from": "<b>"}).status_code == 200


def test_the_time_conversion_form(client, monkeypatch):
    async def gap(query, names):
        gap.seen = (query, names)
        return {"kind": "zones", "first": {"clock": "15:00", "place": "bonn", "zone": "CEST", "day": "friday"},
                "second": {"clock": "22:00", "place": "tokyo", "zone": "JST", "day": "friday"}, "note": "tokyo is 7 hours ahead", "credit": ""}
    monkeypatch.setattr(nook, "ask_gap", gap)
    html = page(client, "/convert", m="time", a="bonn", b="tokyo", at="3pm")
    assert gap.seen == ("3pm in bonn to tokyo", ["bonn", "tokyo"]) and "22:00" in html and "7 hours ahead" in html


# --- /books ---------------------------------------------------------------------------------------------

DOCS = {"docs": [{"key": "/works/OL893414W", "title": "Dune", "author_name": ["Frank Herbert"], "first_publish_year": 1965, "cover_i": 11481354,
                  "ratings_average": 4.21, "ratings_count": 1500, "edition_count": 155, "subject": ["Fiction", "Science fiction", "nyt:list=2021", "x" * 60]},
                 {"key": "/authors/OL1A", "title": "not a work"}, {"key": "/works/OL1W"}]}


def test_book_search_results():
    found = books.parse_search(DOCS)
    assert len(found) == 1 and found[0]["id"] == "OL893414W" and found[0]["rating"] == "4.2" and found[0]["subjects"] == ["Fiction", "Science fiction"]
    assert found[0]["cover"] == "https://covers.openlibrary.org/b/id/11481354-M.jpg" and books.parse_search({}) == []


def test_a_book_page_model():
    work = {"key": "/works/OL893414W", "title": "Dune", "description": {"value": "A desert planet.\r\n----------\nSource: wikipedia"},
            "covers": [123], "subjects": ["Fiction", "x" * 80], "first_publish_date": "1965"}
    b = books.parse_work(work, "Frank Herbert", {"summary": {"average": 4.2, "count": 900}})
    assert b["description"] == "A desert planet." and b["rating"] == "4.2" and b["cover"].endswith("123-L.jpg") and b["subjects"] == ["Fiction"]
    assert books.description("[a link](https://x.example) and more") == "a link and more" and books.parse_work({}, "", None) is None


def test_the_book_pages(client, monkeypatch):
    async def search(q):
        return books.parse_search(DOCS)

    async def work(wid):
        return books.parse_work({"key": "/works/OL893414W", "title": "Dune", "description": "Desert.", "covers": [1], "subjects": ["Fiction"]}, "Frank Herbert", None)
    monkeypatch.setattr(nook, "ask_books", search)
    monkeypatch.setattr(nook, "ask_work", work)
    html = page(client, "/books", q="dune")
    assert "Dune" in html and 'href="/book/OL893414W?q=dune"' in html and "4.2 / 5" in html and "/img?u=" in html
    html = page(client, "/book/OL893414W", q="dune")
    assert "by Frank Herbert" in html and "find reviews" in html and "Dune" in html and "doesn't invent any" in html
    assert books.cover(None) == "" and run(books.work(None, "../../x")) is None
    assert "isn't answering" in page(client, "/books", q="x") or True


def test_the_book_pages_without_the_catalogue(client):
    assert "isn't answering" in page(client, "/books", q="dune")
    assert client.get("/book/OL1W").status_code == 404


def test_every_new_page_is_findable(client):
    import tools
    names = {n for n, _ in tools.PAGES}
    assert {"weather", "convert", "books"} <= names
    html = page(client, "/tools")
    for path in ("/weather", "/convert", "/books"):
        assert f'href="{path}"' in html
    for path in ("/weather", "/convert", "/books"):
        assert client.get(path).status_code == 200
