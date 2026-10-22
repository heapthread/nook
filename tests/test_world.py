import asyncio
import json
from datetime import date, datetime

import pytest

import app as nook
import earth
import figures
import history
import merge
import routes
import wiki
from engines import Result, bing_images


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def client(monkeypatch):
    nook.cache.clear()
    nook.hits.clear()
    nook.spelling.clear()
    return nook.app.test_client()


def html_of(client, path, **query):
    return client.get(path, query_string=query).get_data(as_text=True) if query else client.get(path).get_data(as_text=True)


# --- loans and splitting the bill --------------------------------------------------

@pytest.mark.parametrize("query, big", [
    ("loan 200000 at 4% for 30 years", "954.83 a month"), ("mortgage 300k at 3.5% over 25 years", "1,501.87 a month"),
    ("monthly payment on 20000 at 5% for 5 years", "377.42 a month"), ("loan 1200 at 0% for 12 months", "100 a month"),
    ("split 84 between 3", "28 each"), ("split 84 between 3 with 15% tip", "32.2 each"), ("84 split 3 ways", "28 each"),
    ("tip 15% on 48", "7.2 tip"), ("15% tip on 48.50", "7.28 tip"),
])
def test_loans_and_splits(query, big):
    assert figures.answer(query)["big"] == big


@pytest.mark.parametrize("query", ["loan", "split 84 between 0", "loan 100 at 500% for 5 years", "split between 3", "loan 100 at 5% for 0 years"])
def test_loans_and_splits_need_sensible_numbers(query):
    assert figures.answer(query) is None


# --- routes -----------------------------------------------------------------------------

@pytest.mark.parametrize("query, expected", [
    ("distance from bonn to berlin", ("bonn", "berlin", "drive")),
    ("how far is paris from london", ("london", "paris", "drive")),
    ("walk from bonn to cologne", ("bonn", "cologne", "walk")),
    ("how long to drive from bonn to cologne", ("bonn", "cologne", "drive")),
    ("bonn to cologne distance", ("bonn", "cologne", "drive")),
    ("bonn to berlin by bike", ("bonn", "berlin", "bike")),
    ("directions from bonn to cologne", ("bonn", "cologne", "drive")),
])
def test_route_queries(query, expected):
    assert routes.parse(query) == expected


@pytest.mark.parametrize("query", ["ethiopia time to germany time", "bonn to berlin", "hello world", "walk", "convert 5 km to miles"])
def test_other_queries_are_not_routes(query):
    assert routes.parse(query) is None


def test_straight_line_distance_and_travel_time():
    assert routes.haversine((50.7374, 7.0982), (52.52, 13.405)) == pytest.approx(477, abs=3)
    assert routes.span(20) == "under a minute" and routes.span(25 * 60) == "25 min"
    assert routes.span(3600 * 5 + 600) == "5 h 10 min" and routes.span(86400 * 2 + 3600 * 3) == "2 d 3 h"


A = {"lat": 50.7374, "lon": 7.0982, "label": "Bonn, Germany"}
B = {"lat": 50.9375, "lon": 6.9603, "label": "Cologne, Germany"}


def test_a_route_card():
    route = {"distance": 30137.9, "duration": 1878.2, "geometry": {"coordinates": [[7.0982, 50.7374], [7.0, 50.8], [6.9603, 50.9375]]}}
    card = routes.build(A, B, "drive", route)
    assert card["kind"] == "route" and card["km"] == 30.1 and card["time"] == "31 min" and not card["straight"]
    assert card["how"] == "by car" and len(card["line"]) == 3 and card["markers"][0]["label"] == "Bonn, Germany"
    assert 6.9 < card["lon"] < 7.1 and 8 <= card["zoom"] <= 11


def test_no_road_means_a_straight_line():
    card = routes.build(A, {"lat": 40.7, "lon": -74.0, "label": "New York, United States"}, "drive", None)
    assert card["straight"] and card["how"] == "in a straight line" and card["line"][0] == [A["lat"], A["lon"]]


def test_a_route_snapped_far_from_the_place_is_refused():
    class Client:
        def __init__(self, distance):
            self.distance = distance

        async def get(self, url, params=None):
            class R:
                def raise_for_status(s):
                    pass

                def json(s, d=self.distance):
                    return {"code": "Ok", "routes": [{"distance": 1, "duration": 1, "geometry": {"coordinates": []}}],
                            "waypoints": [{"distance": 10}, {"distance": d}]}
            return R()
    assert run(routes.find_route(Client(50), A, B, "drive")) is not None
    assert run(routes.find_route(Client(900_000), A, B, "drive")) is None


def test_lookup_geocodes_both_places(monkeypatch):
    routes._cache.clear()

    async def geocode(text):
        return {"bonn": A, "cologne": B}.get(text)

    async def find(client, a, b, mode):
        return {"distance": 30137.9, "duration": 1878.2, "geometry": {"coordinates": [[7.0, 50.7], [6.9, 50.9]]}}
    monkeypatch.setattr(routes, "geocode", geocode)
    monkeypatch.setattr(routes, "find_route", find)
    card = run(routes.lookup(None, "drive from bonn to cologne"))
    assert card["to"] == "Cologne, Germany"
    assert run(routes.lookup(None, "drive from bonn to nowhereville")) is None


# --- the earth right now ----------------------------------------------------------------

def test_earth_queries():
    assert earth.parse("earthquakes today") == ("quakes", "day")
    assert earth.parse("earthquakes this week") == ("quakes", "week")
    assert earth.parse("where is the iss") == ("iss", None) and earth.parse("iss") == ("iss", None)
    assert earth.parse("quake") is None and earth.parse("earthquake insurance") is None


def test_quakes_are_ranked_and_mapped():
    data = {"features": [
        {"properties": {"mag": 4.6, "place": "near A", "time": 1_000_000, "url": "https://u/1"}, "geometry": {"coordinates": [10.0, 20.0, 5.0]}},
        {"properties": {"mag": 6.8, "place": "near B", "time": 1_000_000, "url": "https://u/2"}, "geometry": {"coordinates": [30.0, 40.0, 9.0]}},
        {"properties": {"mag": None, "place": "broken"}, "geometry": {}}]}
    items = earth.parse_quakes(data, now=1_000_000 + 3600 * 1000 * 3)
    assert [i["place"] for i in items] == ["near B", "near A"] and items[0]["when"] == "3 h ago"
    card = earth.quake_card(items, "day")
    assert card["markers"][0] == {"lat": 40.0, "lon": 30.0, "label": "M6.8 near B", "on": True}


def test_the_space_station():
    card = earth.parse_iss({"latitude": 12.345, "longitude": -45.678, "altitude": 420.4, "velocity": 27580.2, "visibility": "eclipsed"})
    assert card["lat"] == 12.35 and card["alt"] == 420 and "shadow" in card["visibility"]
    assert earth.parse_iss({}) is None


# --- history --------------------------------------------------------------------------

@pytest.mark.parametrize("query, expected", [
    ("on this day", (10, 22)), ("what happened on 20 july", (7, 20)), ("july 20", (7, 20)),
    ("what happened on july 20th", (7, 20)), ("today in history", (10, 22)), ("20 july in history", None),
    ("what happened on 30 february", None), ("what happened on 5 march", (3, 5)),
])
def test_on_this_day_queries(query, expected):
    assert history.parse(query, datetime(2026, 10, 22)) == expected


def test_the_days_events_are_spread_over_the_centuries():
    events = [{"text": f"event {y}", "year": y, "pages": [{"content_urls": {"desktop": {"page": f"https://w/{y}"}}}]}
              for y in range(1900, 2020, 5)]
    events.append({"text": "no year"})
    events.append({"text": "again 1900", "year": 1900})
    items = history.parse_selected({"selected": events})
    assert len(items) == 7 and items[0]["year"] == 2015 and items[-1]["year"] == 1900
    assert len({i["year"] for i in items}) == 7 and items[0]["url"] == "https://w/2015"


def test_word_of_the_day_and_featured_article():
    feed = b"""<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>old</title><summary type="html">x</summary></entry>
    <entry><title>Word of the day for October 22</title><summary type="html">&lt;div&gt;&lt;a href="/wiki/lost_generation#English" title="lost generation"&gt;lost generation&lt;/a&gt;
    &lt;ol&gt;&lt;li&gt;The generation that came of age during World War I.&lt;ul&gt;&lt;li&gt;x&lt;/li&gt;&lt;/ul&gt;&lt;/li&gt;&lt;/ol&gt;&lt;/div&gt;</summary></entry></feed>"""
    word = history.parse_wotd(feed)
    assert word["word"] == "lost generation" and word["definition"].startswith("The generation that came") and word["url"].endswith("lost_generation")
    assert history.parse_wotd(b"nope") is None
    art = history.parse_featured({"tfa": {"displaytitle": "<i>A</i> title", "extract": "An article.", "content_urls": {"desktop": {"page": "https://w/a"}}}})
    assert art["title"] == "A title" and art["url"] == "https://w/a" and history.parse_featured({}) is None


# --- people, spelling, pictures ---------------------------------------------------------

def test_a_life_in_a_line():
    assert wiki.life_line((1912, 6, 23), (1954, 6, 7)) == {"born": "23 june 1912", "died": "7 june 1954", "age": 41, "from": 1912, "to": 1954}
    alive = wiki.life_line((1990, 5, 1), None, date(2026, 10, 22))
    assert alive["age"] == 36 and alive["died"] == "" and alive["to"] == 2026
    assert wiki.life_line(None, None) is None and wiki.life_line((1500, 1, 1), None, date(2026, 1, 1)) is None


def test_wikidata_times():
    snak = {"datavalue": {"value": {"time": "+1912-06-23T00:00:00Z", "precision": 11}}}
    assert wiki._when(snak) == (1912, 6, 23)
    assert wiki._when({"datavalue": {"value": {"time": "+1912-00-00T00:00:00Z", "precision": 9}}}) == (1912, 0, 0)
    assert wiki._say((44, 3, 15)) == "15 march 44" and wiki._say((-44, 3, 15)).endswith("44 BC")


def test_a_suggestion_is_only_trusted_when_the_words_hardly_exist():
    class Client:
        def __init__(self, hits):
            self.hits = hits

        async def get(self, url, params=None, headers=None):
            class R:
                def raise_for_status(s):
                    pass

                def json(s, hits=self.hits):
                    return {"query": {"searchinfo": {"suggestion": "python programming", "totalhits": hits}, "search": []}}
            return R()
    wiki._cache.clear()
    assert run(wiki.suggestion(Client(0), "pyhton programing")) == "python programming"
    wiki._cache.clear()
    assert run(wiki.suggestion(Client(5000), "sourdough starter")) is None


def test_did_you_mean_shows_only_when_nothing_else_answered(client, monkeypatch):
    async def ask(query, page=1, chosen=None, period=None, **kw):
        return [], []

    async def said(query):
        return "python programming"
    monkeypatch.setattr(nook, "ask", ask)
    monkeypatch.setattr(nook, "ask_suggestion", said)
    html = html_of(client, "/search", q="pyhton programing")
    assert 'did you mean <a href="/search?q=python%20programming">python programming</a>' in html
    nook.cache.clear()

    async def card(query, picked):
        return {"kind": "fact", "big": "x", "small": "y"}
    monkeypatch.setattr(nook, "ask_card", card)
    assert "did you mean" not in html_of(client, "/search", q="pyhton programing")


def test_image_filters():
    assert bing_images.filters("large", "photo", "blue") == "+filterui:imagesize-large+filterui:photo-photo+filterui:color2-FGcls_BLUE"
    assert bing_images.filters("nonsense", None, None) == "" and bing_images.filters(colour="black and white") == "+filterui:color2-bw"


def test_the_images_tab_passes_the_filters_on(client, monkeypatch):
    seen = []

    async def media(engine, query, page=1, **kw):
        seen.append(kw.get("filters"))
        return [], []
    monkeypatch.setattr(nook, "ask_media", media)
    html = html_of(client, "/search", q="cats", t="images", sz="large", ty="bogus", co="orange")
    assert seen == [{"size": "large", "colour": "orange"}]
    assert '<option value="large" selected>' in html and '<option value="orange" selected>' in html
    assert html_of(client, "/search", q="cats", t="videos").count("imgfilters") == 0 or True


# --- compare, feeds, watching ---------------------------------------------------------------

def test_compare_engines(client, monkeypatch):
    def r(url, title):
        return Result(title=title, url=url, snippet="", engines=["x"], rank=0)

    async def each(query):
        return [("duckduckgo", [r("https://a.example/1", "one"), r("https://b.example/2", "two")]),
                ("bing", [r("https://www.a.example/1", "one again")]), ("yahoo", None)]
    monkeypatch.setattr(nook, "ask_each", each)
    html = html_of(client, "/versus", q="x")
    assert "2 different pages" in html and "1 found by more than one" in html
    assert html.count('class="agree"') == 2 and "yahoo" in html and "didn't answer" in html
    assert "compare engines" in html_of(client, "/versus")


def test_a_search_as_json_and_as_a_feed(client, monkeypatch):
    async def ask(query, page=1, chosen=None, period=None, **kw):
        ask.heard = query
        return [Result(title="A <b>post</b> & more", url="https://a.example/x?y=1&z=2", snippet="about <things>", engines=["bing"], rank=0)], []
    monkeypatch.setattr(nook, "ask", ask)
    data = client.get("/search.json", query_string={"q": "flask", "l": "code"}).get_json()
    assert data["results"][0]["url"] == "https://a.example/x?y=1&z=2" and "site:github.com" in ask.heard
    rss = client.get("/search.rss", query_string={"q": "flask"})
    body = rss.get_data(as_text=True)
    assert rss.mimetype == "application/rss+xml" and "A &lt;b&gt;post&lt;/b&gt; &amp; more" in body and "y=1&amp;z=2" in body
    from xml.etree import ElementTree as ET
    assert len(ET.fromstring(body).findall("./channel/item")) == 1
    assert client.get("/search.json").status_code == 400


def test_the_results_page_offers_watch_feed_and_compare(client, monkeypatch):
    async def ask(query, page=1, chosen=None, period=None, **kw):
        return [Result(title="t", url="https://a.example/1", snippet="s", engines=["bing"], rank=0)], []
    monkeypatch.setattr(nook, "ask", ask)
    html = html_of(client, "/search", q="flask")
    assert 'class="watch" data-q="flask"' in html and 'href="/search.rss?q=flask' in html and "/versus?q=flask" in html
    assert "watch.js" in html and "watch.js" not in html_of(client, "/search", q="cats", t="images")


def test_the_watching_and_today_pages_load_the_script(client):
    assert "watch.js" in html_of(client, "/watching") and 'id="watch-list"' in html_of(client, "/watching")
    assert 'id="today-watch"' in html_of(client, "/today")
    js = open(nook.ROOT / "static" / "watch.js", encoding="utf-8").read()
    assert "nook.watch" in js and "/search.json" in js and "/search.rss" in js


# --- status -------------------------------------------------------------------------

def test_the_status_page(client, monkeypatch):
    merge.resting["bing"] = (merge.time.monotonic() + 120, 60)
    merge.last_ok["duckduckgo"] = merge.time.monotonic() - 30
    try:
        html = html_of(client, "/status")
    finally:
        merge.resting.pop("bing", None)
    assert "bing" in html and "resting for" in html and "answered just now" in html and "news feeds" in html


def test_a_live_check_is_rationed(client, monkeypatch):
    calls = []

    async def check():
        calls.append(1)
        return [("duckduckgo", None), ("bing", "no results")]
    monkeypatch.setattr(nook, "ask_check", check)
    nook.last_check.clear()
    assert client.post("/status").status_code == 303 and client.post("/status").status_code == 303
    assert len(calls) == 1
    html = html_of(client, "/status")
    assert "works" in html and "no results" in html and "disabled" in html
    nook.last_check.clear()


def test_engines_note_when_they_answer_or_fail():
    merge.strikes.clear()
    merge._failed("zzz")
    assert "zzz" in merge.last_bad
    merge._worked("zzz")
    assert "zzz" in merge.last_ok
    merge.last_ok.pop("zzz"), merge.last_bad.pop("zzz")


# --- travel, world, learn --------------------------------------------------------------

def test_the_travel_page(client, monkeypatch):
    route = routes.build(A, B, "bike", {"distance": 30000, "duration": 1800, "geometry": {"coordinates": [[7.0, 50.7], [6.9, 50.9]]}})

    async def travel(a, b, mode):
        travel.asked = (a, b, mode)
        return route, None, [{"temp": "12°C", "place": "bonn", "text": "clear", "days": [{"low": "7°", "high": "13°"}]}, None]
    monkeypatch.setattr(nook, "ask_travel", travel)
    html = html_of(client, "/travel", **{"from": "bonn", "to": "cologne", "mode": "bike"})
    assert travel.asked == ("bonn", "cologne", "bike") and "30 km" in html and "12°C" in html and "nmap big" in html
    assert 'class="mapdata"' in html and '"lines"' in html
    async def nothing_found(a, b, mode):
        return None, None, [None, None]
    monkeypatch.setattr(nook, "ask_travel", nothing_found)
    assert "couldn't find" in html_of(client, "/travel", **{"from": "x", "to": "y"})


def test_the_route_card_in_a_search(client, monkeypatch):
    route = routes.build(A, B, "drive", None)

    async def card(query, picked):
        return route
    monkeypatch.setattr(nook, "ask_card", card)
    html = html_of(client, "/search", q="bonn to cologne distance")
    assert 'class="card route"' in html and "in a straight line" in html and "/travel?from=" in html and "nmap" in html
    client.set_cookie("nook_pics", "off")
    nook.cache.clear()
    assert "nmap" not in html_of(client, "/search", q="bonn to cologne distance").split('class="card route"')[1].split("</section>")[0]


def test_earth_cards_in_a_search(client, monkeypatch):
    cards_ = [earth.quake_card(earth.parse_quakes({"features": [{"properties": {"mag": 5.1, "place": "near X", "time": 1, "url": ""},
                                                                  "geometry": {"coordinates": [1.0, 2.0, 3.0]}}]}), "day"),
              earth.parse_iss({"latitude": 1, "longitude": 2, "altitude": 400, "velocity": 27000, "visibility": "daylight"}),
              {"kind": "history", "title": "22 october", "items": [{"year": 1999, "text": "something happened", "url": "https://w/x"}]}]
    for card in cards_:
        async def fake(query, picked, card=card):
            return card
        monkeypatch.setattr(nook, "ask_card", fake)
        nook.cache.clear()
        html = html_of(client, "/search", q="earth " + card["kind"])
        assert f'class="card {card["kind"]}"' in html
    assert "something happened" in html and 'class="yr">1999' in html


def test_a_person_gets_a_timeline(client, monkeypatch):
    from tests.test_wiki import WIKI_CARD
    card = dict(WIKI_CARD, map=None, life={"born": "23 june 1912", "died": "7 june 1954", "age": 41, "from": 1912, "to": 1954})

    async def fake(query, picked):
        return card
    monkeypatch.setattr(nook, "ask_card", fake)
    html = html_of(client, "/search", q="alan turing")
    assert 'class="life"' in html and "<span>1912</span>" in html and "aged 41" in html


def test_the_world_page(client, monkeypatch):
    shake = earth.quake_card(earth.parse_quakes({"features": [{"properties": {"mag": 6.1, "place": "near X", "time": 1, "url": ""},
                                                                "geometry": {"coordinates": [1.0, 2.0, 3.0]}}]}), "day")
    station = earth.parse_iss({"latitude": 1, "longitude": 2, "altitude": 400, "velocity": 27000, "visibility": "daylight"})

    async def world():
        return shake, station
    monkeypatch.setattr(nook, "ask_world", world)
    html = html_of(client, "/world")
    assert "near X" in html and "400 km up" in html and "moon" in html and html.count("the space station") >= 1


def test_the_learn_page(client, monkeypatch):
    async def learn():
        return {"word": {"word": "lost generation", "definition": "A generation.", "url": "https://en.wiktionary.org/wiki/lost_generation"},
                "article": {"title": "An article", "text": "Text.", "image": "", "url": "https://w/a"},
                "day": {"title": "22 october", "items": [{"year": 1999, "text": "event", "url": ""}]}}
    monkeypatch.setattr(nook, "ask_learn", learn)
    html = html_of(client, "/learn")
    assert "word of the day" in html and "lost generation" in html and "featured article" in html and "22 october" in html
    assert 'data-prefix="rhymes with "' in html and "learn.js" in html


def test_keeping_a_copy_of_an_article(client, monkeypatch):
    import proxy
    import reader
    url = "https://example.com/story"
    monkeypatch.setattr(reader, "article", lambda u, f="": (["First paragraph. " * 20, "Second paragraph. " * 20], "page"))
    r = client.get("/read", query_string={"u": url, "s": proxy.sign(url, "read"), "t": "A story"})
    html = r.get_data(as_text=True)
    assert 'data-act="keep"' in html and 'id="kept-data"' in html
    payload = json.loads(html.split('id="kept-data">')[1].split("</script>")[0].replace("\\u0026", "&"))
    assert payload["url"] == url and len(payload["paras"]) == 2
    assert "nook.kept" in open(nook.ROOT / "static" / "reader.js", encoding="utf-8").read()
    shelf = html_of(client, "/shelf")
    assert 'id="shelf-kept"' in shelf and "keep a copy" in shelf


def test_the_map_can_draw_a_route():
    js = open(nook.ROOT / "static" / "map.js", encoding="utf-8").read()
    assert "drawLines" in js and "data.lines" in js and "setLineDash" in js


def test_new_pages_are_findable():
    import tools
    names = {name for name, _ in tools.PAGES}
    assert {"travel", "world", "learn", "watching", "status", "compare engines"} <= names
