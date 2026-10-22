import pytest

import app as nook
import maps


@pytest.fixture
def client(monkeypatch):
    nook.cache.clear()
    nook.hits.clear()
    return nook.app.test_client()


def test_only_real_tiles_are_asked_for():
    assert maps.valid_tile(0, 0, 0) and maps.valid_tile(4, 15, 15)
    assert not maps.valid_tile(4, 16, 0) and not maps.valid_tile(20, 0, 0) and not maps.valid_tile(3, -1, 0)


def test_zoom_from_a_bounding_box():
    assert maps.zoom_from_box(["50.6", "50.8", "7.0", "7.2"]) in (10, 11)     # a city
    assert maps.zoom_from_box(["47", "55", "6", "15"]) in (5, 6)              # a country
    assert maps.zoom_from_box(None) == 12


def test_nominatim_answers_become_places():
    raw = [{"lat": "50.73", "lon": "7.10", "display_name": "Bonn, North Rhine-Westphalia, Germany", "type": "administrative",
            "boundingbox": ["50.6", "50.8", "7.0", "7.2"]}, {"display_name": "no coordinates"}]
    places = maps.parse(raw)
    assert len(places) == 1
    assert places[0]["name"] == "Bonn" and places[0]["where"].startswith("North Rhine") and places[0]["kind"] == "administrative"
    assert "openstreetmap.org" in places[0]["osm"]


def test_tiles_are_remembered(monkeypatch):
    calls = []

    class Reply:
        content = b"\x89PNG tile"

        def raise_for_status(self):
            pass

    monkeypatch.setattr(maps.httpx, "get", lambda url, **kw: calls.append(url) or Reply())
    maps._tiles.clear()
    assert maps.tile(5, 1, 2) == b"\x89PNG tile" and maps.tile(5, 1, 2) == b"\x89PNG tile"
    assert len(calls) == 1 and calls[0].endswith("/5/1/2.png")


def test_the_tile_route(client, monkeypatch):
    monkeypatch.setattr(maps, "tile", lambda z, x, y: b"png")
    r = client.get("/tile/3/2/1.png")
    assert r.status_code == 200 and r.mimetype == "image/png" and "max-age" in r.headers["Cache-Control"]
    assert client.get("/tile/3/9/1.png").status_code == 404


def test_the_maps_page_lists_places_and_centres_the_map(client, monkeypatch):
    places = [{"name": "Oslo", "where": "Norway", "kind": "city", "lat": 59.9, "lon": 10.7, "zoom": 10, "osm": "https://www.openstreetmap.org/x"},
              {"name": "Oslo", "where": "Oslo county", "kind": "county", "lat": 60.0, "lon": 10.8, "zoom": 8, "osm": "https://www.openstreetmap.org/y"}]
    monkeypatch.setattr(maps, "search", lambda q, lang="en": places)
    html = client.get("/maps", query_string={"q": "oslo", "i": "1"}).get_data(as_text=True)
    assert 'class="nmap big"' in html and 'data-lat="60.0"' in html and 'data-zoom="8"' in html
    assert html.count('data-zoom="') >= 3 and "open on openstreetmap.org" in html
    assert '<li class="on">' in html


def test_the_maps_page_without_a_search_or_when_it_fails(client, monkeypatch):
    assert "find a place" in client.get("/maps").get_data(as_text=True)
    import httpx

    def boom(q, lang="en"):
        raise httpx.ConnectError("down")
    monkeypatch.setattr(maps, "search", boom)
    html = client.get("/maps", query_string={"q": "x"}).get_data(as_text=True)
    assert "isn't answering" in html


def test_a_map_link_with_a_position(client):
    html = client.get("/maps", query_string={"lat": "50.7", "lon": "7.1", "z": "11", "name": "Bonn <b>"}).get_data(as_text=True)
    assert 'data-lat="50.7"' in html and "&lt;b&gt;" in html and "<b>" not in html.split("<main")[1].replace("<b>ctrl", "")


def test_the_credit_fades_but_stays_one_click_away(client, monkeypatch):
    html = client.get("/maps").get_data(as_text=True)
    assert "OpenStreetMap contributors" in html and 'class="info"' in html
    js = open(nook.ROOT / "static" / "map.js", encoding="utf-8").read()
    assert "5000" in js and "1500" not in js and "classList.toggle(\"show\")" in js   # OSM: fade after five seconds at the soonest


def test_nothing_on_the_page_reaches_another_site(client):
    html = client.get("/maps").get_data(as_text=True)
    assert "unpkg" not in html and "tile.openstreetmap.org" not in html
    assert "img-src 'self'" in client.get("/maps").headers["Content-Security-Policy"]
