import re
from datetime import datetime, timezone
from pathlib import Path

import pytest

import app as nook
import cards
import proxy

FIX = Path(__file__).parent / "fixtures"


def read(name):
    return (FIX / name).read_text(encoding="utf-8")


@pytest.fixture
def client():
    nook.cache.clear()
    nook.hits.clear()
    cards._cache.clear()
    return nook.app.test_client()


# --- what the query is asking for -------------------------------------------

@pytest.mark.parametrize("q, word", [
    ("define meretricious", "meretricious"), ("meretricious meaning", "meretricious"),
    ("what does serendipity mean", "serendipity"), ("definition of ephemeral", "ephemeral"),
    ("Meaning of well-being?", "well-being"), ("what is the meaning of love", "love"),
])
def test_define_patterns(q, word):
    assert cards.define_word(q) == word


@pytest.mark.parametrize("q", ["python decorators", "define", "how to define a function", "the meaning of life is 42"])
def test_not_definitions(q):
    assert cards.define_word(q) is None


@pytest.mark.parametrize("q, topic", [("alan turing", "alan turing"), ("who is alan turing?", "alan turing"),
                                      ("what was the roman empire", "roman empire")])
def test_topics(q, topic):
    assert cards.topic_of(q) == topic


@pytest.mark.parametrize("q", ["a", "how do i fix a leaking tap in the bathroom", "site:example.com cats"])
def test_not_topics(q):
    assert cards.topic_of(q) is None


# --- dictionary pages -------------------------------------------------------

def test_american_heritage_page():
    a = cards.parse_ahd(read("ahd_meretricious.html"))
    assert a["audio"].startswith("https://www.ahdictionary.com/") and a["audio"].endswith(".wav")
    entry = a["entries"][0]
    assert entry["pos"] == "adjective"
    first, second = entry["senses"]
    assert [s["text"] for s in first["subs"]] == ["Attracting attention in a vulgar manner",
                                                   "Plausible but false or insincere; specious"]
    assert first["subs"][0]["example"] == "“meretricious ornamentation.”"
    assert second["text"].startswith("Of or relating to prostitutes")
    assert a["origin"].startswith("Latin meretr") and a["origin"].endswith("earn money.")
    assert "see" not in a["origin"].split(",")[-1]  # the cross-reference is cut


def test_quotations_keep_their_author_and_get_curly_quotes():
    html = ('<div id="results"><table><tr><td><div class="rtseg"><b>x</b></div><div class="pseg"><i>adj.</i>'
            '<div class="ds-list"><b>1. </b><span> </span>Lasting briefly:<span> </span>'
            '<font><i>"Too ephemeral to keep"</i></font><span> </span><font><i>(Someone Famous).</i></font></div></div>'
            '</td></tr></table></div>')
    sense = cards.parse_ahd(html)["entries"][0]["senses"][0]
    assert sense["text"] == "Lasting briefly"
    assert sense["example"] == "“Too ephemeral to keep” (Someone Famous)."


def test_cambridge_page():
    c = cards.parse_cambridge(read("cambridge_meretricious.html"))
    assert c["ipa"] and "." not in c["ipa"]
    assert c["audio"].startswith("https://dictionary.cambridge.org/media/") and c["audio"].endswith(".mp3")
    sense = c["entries"][0]["senses"][0]
    assert sense["text"].startswith("seeming attractive") and sense["example"]


def test_a_whole_card_is_built_from_whatever_answered():
    a, c = cards.parse_ahd(read("ahd_meretricious.html")), cards.parse_cambridge(read("cambridge_meretricious.html"))
    similar = cards.parse_datamuse(read("datamuse_syn.json"), "meretricious")
    card = cards.build_definition("meretricious", a, c, similar)
    assert card["phonetic"].startswith("/") and card["audio"].endswith(".mp3")
    assert card["source"]["name"] == "American Heritage Dictionary" and card["origin"]
    assert "gaudy" in card["similar"] and "meretricious" not in card["similar"]
    only = cards.build_definition("meretricious", None, c, [])  # only Cambridge answered
    assert only["source"]["name"] == "Cambridge Dictionary" and not only["origin"]
    fallback = cards.parse_datamuse_defs('[{"word":"x","defs":["adj\\tseeming nice"]}]')  # only the synonym service
    assert cards.build_definition("x", None, None, [], fallback)["entries"][0]["pos"] == "adjective"
    assert cards.build_definition("x") is None  # nobody answered: no card


# --- summaries and money ------------------------------------------------------

def test_knowledge_card():
    card = cards.parse_knowledge(read("ddg_instant.json"), "alan turing")
    assert card["title"] == "Alan Turing" and card["image"].startswith("https://duckduckgo.com/i/")
    assert card["text"].endswith(".") and len(card["text"]) <= 520
    assert card["source"]["name"] == "Wikipedia"
    assert cards.parse_knowledge(read("ddg_instant.json"), "banana bread") is None  # not what was asked about
    assert cards.parse_knowledge("not json", "x") is None


def test_currency_card():
    card = cards.parse_currency(read("frankfurter.json"), 100.0, "USD", "EUR")
    assert card["line"] == "100 USD = 89.02 EUR" and "European Central Bank" in card["note"]
    assert cards._currency("100 usd in eur") == (100.0, "USD", "EUR")
    assert cards._currency("usd to eur") == (1.0, "USD", "EUR")
    assert cards._currency("5 km in mi") is None and cards._currency("usd to usd") is None


# --- cards worked out on the spot --------------------------------------------

def test_dice_coin_and_random():
    for _ in range(50):
        card = cards.local("roll d20")
        assert card["kind"] == "dice" and 1 <= int(card["big"]) <= 20
    two = cards.local("roll 2d6")
    assert "2d6" in two["small"] and 2 <= int(two["big"]) <= 12
    assert cards.local("flip a coin")["big"] in ("heads", "tails")
    assert 5 <= int(cards.local("random number between 5 and 9")["big"]) <= 9
    assert cards.local("roll 0d6") is None and cards.local("roll d1") is None


def test_time_somewhere():
    now = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)
    card = cards.local("time in tokyo", now)
    assert card["kind"] == "time" and card["clock"] == "21:00" and card["place"] == "tokyo"
    assert "UTC+9" in card["zone"]
    assert cards.local("what time is it in new york", now)["place"] == "new york"
    assert cards.local("london time", now)["clock"] in ("12:00", "13:00")
    assert cards.local("time in atlantis", now) is None


def test_timer():
    assert cards.local("timer 5 min") == {"kind": "timer", "seconds": 300}
    assert cards.local("set a timer for 90 seconds")["seconds"] == 90
    assert cards.local("2 hour timer")["seconds"] == 7200
    assert cards.local("timer 0 min") is None and cards.local("timer 999 hours") is None


# --- in the page ---------------------------------------------------------------

def with_card(monkeypatch, card):
    async def fake(query, picked):
        return card
    monkeypatch.setattr(nook, "ask_card", fake)


def test_definition_card_in_the_page(client, monkeypatch):
    a, c = cards.parse_ahd(read("ahd_meretricious.html")), cards.parse_cambridge(read("cambridge_meretricious.html"))
    with_card(monkeypatch, cards.build_definition("meretricious", a, c, ["gaudy", "garish"]))
    html = client.get("/search?q=define+meretricious").get_data(as_text=True)
    assert 'class="card define"' in html and "<h2>meretricious</h2>" in html
    assert "Attracting attention in a vulgar manner" in html and "origin" in html
    assert 'href="/search?q=define+gaudy"' in html
    assert 'data-audio="/audio?u=' in html and "card.js" in html


def test_no_card_when_none_is_wanted(client):
    assert 'class="card' not in client.get("/search?q=cats").get_data(as_text=True)


def test_knowledge_card_picture_goes_through_nook(client, monkeypatch):
    with_card(monkeypatch, cards.parse_knowledge(read("ddg_instant.json"), "alan turing"))
    html = client.get("/search?q=alan+turing").get_data(as_text=True)
    assert 'class="card knowledge"' in html and 'class="pic" src="/img?u=' in html


def test_cards_are_worked_out_fresh_not_remembered(client):
    rolls = {client.get("/search?q=roll+d20").get_data(as_text=True).split('class="big">')[1].split("<")[0]
             for _ in range(25)}
    assert len(rolls) > 1  # not the same roll every time


def test_timer_page(client):
    html = client.get("/search?q=timer+5+min").get_data(as_text=True)
    assert 'data-seconds="300"' in html and 'data-act="start"' in html


def test_card_only_on_the_first_page_of_the_web_tab(client, monkeypatch):
    with_card(monkeypatch, {"kind": "currency", "line": "1 USD = 1 EUR", "note": "n"})
    assert "1 USD = 1 EUR" in client.get("/search?q=usd+to+eur").get_data(as_text=True)
    assert "1 USD = 1 EUR" not in client.get("/search?q=usd+to+eur&page=2").get_data(as_text=True)
    assert "1 USD = 1 EUR" not in client.get("/search?q=usd+to+eur&t=images").get_data(as_text=True)


# --- the audio clips ------------------------------------------------------------

def test_audio_proxy(client, monkeypatch):
    url = "https://dictionary.cambridge.org/media/english/us_pron/x.mp3"
    assert client.get("/audio?u=" + url).status_code == 403
    assert client.get(proxy.link(url).replace("/img?", "/audio?")).status_code == 403  # a picture signature won't do
    monkeypatch.setattr(proxy, "fetch_audio", lambda u: (b"ID3", "audio/mpeg"))
    r = client.get(proxy.audio_link(url))
    assert r.status_code == 200 and r.mimetype == "audio/mpeg" and "max-age" in r.headers["Cache-Control"]


def test_audio_proxy_refuses_private_addresses(client):
    assert client.get(proxy.audio_link("http://127.0.0.1/x.mp3")).status_code == 502
    with pytest.raises(proxy.Refused):
        proxy.fetch_audio("http://169.254.169.254/x.mp3")


# --- time in places, and between them -----------------------------------------

import places  # noqa: E402

NOW = datetime(2026, 10, 21, 18, 35, tzinfo=timezone.utc)   # Germany on summer time, Ethiopia is always UTC+3


def zones(q):
    return places.answer(q, NOW)


def test_the_example_that_started_this():
    card = zones("ethiopia time to germany time")
    assert card["kind"] == "zones"
    assert (card["first"]["place"], card["first"]["clock"]) == ("ethiopia", "21:35")
    assert (card["second"]["place"], card["second"]["clock"]) == ("germany", "20:35")
    assert card["note"].startswith("germany is 1 hour behind ethiopia")
    assert "UTC+3" in card["first"]["zone"] and "UTC+2" in card["second"]["zone"] and "berlin" in card["second"]["zone"]


@pytest.mark.parametrize("q", ["ethiopia time in germany time", "ethiopia to germany time", "convert ethiopia time to germany time",
                               "what is the time in ethiopia in germany time"])
def test_the_same_question_asked_other_ways(q):
    card = zones(q)
    assert card and card["second"]["clock"] == "20:35"


def test_a_clock_time_is_converted():
    card = zones("3pm in ethiopia to germany")
    assert (card["first"]["clock"], card["second"]["clock"]) == ("3:00 pm", "2:00 pm")      # typed with pm, shown with pm
    card = zones("10am est to cet")
    assert card["second"]["clock"] == "4:00 pm" and "6 hours ahead of EST" in card["note"]
    assert zones("15:00 berlin to tokyo")["second"]["clock"] == "22:00"                      # typed in 24 hours, shown in 24
    assert zones("noon london to sydney")["second"]["clock"] == "10:00 pm"


def test_the_day_can_change_and_half_hour_zones_work():
    card = zones("midnight utc to pst")
    assert "the day before" in card["note"] and "tuesday 20 october" in card["note"]
    card = zones("india time to usa time")
    assert "9 hours 30 minutes behind india" in card["note"]
    assert zones("time difference between lagos and berlin")["note"].startswith("berlin is 1 hour ahead of lagos")
    assert "on the same time" in zones("lagos time to london time")["note"]   # both UTC+1 in October


def test_countries_cities_and_zone_names_are_all_places():
    for name, zone in [("germany", "Europe/Berlin"), ("ethiopia", "Africa/Addis_Ababa"), ("usa", "America/New_York"),
                       ("uk", "Europe/London"), ("south korea", "Asia/Seoul"), ("brazil", "America/Sao_Paulo"),
                       ("canada", "America/Toronto"), ("australia", "Australia/Sydney"), ("russia", "Europe/Moscow"),
                       ("tokyo", "Asia/Tokyo"), ("new york", "America/New_York"), ("mumbai", "Asia/Kolkata"),
                       ("beijing", "Asia/Shanghai"), ("est", "America/New_York"), ("cet", "Europe/Berlin"),
                       ("the netherlands", "Europe/Amsterdam"), ("germany time", "Europe/Berlin")]:
        assert places.resolve(name)[0] == zone, name
    assert places.resolve("atlantis") is None and places.resolve("time") is None


def test_a_single_place_still_works_and_names_the_city_behind_a_country():
    card = zones("time in germany")
    assert card["kind"] == "time" and card["clock"] == "20:35" and "berlin" in card["zone"]
    assert zones("what time is it in japan")["clock"] == "03:35" and zones("tokyo time")["place"] == "tokyo"


@pytest.mark.parametrize("q", ["paris to london", "usd to eur", "5 to 7", "time in atlantis", "3 to 5 pm", "km to miles", ""])
def test_things_that_are_not_time_questions_are_left_alone(q):
    assert zones(q) is None


def test_clock_parsing():
    assert places.parse_clock("3pm in tokyo") == (15, 0, True, "in tokyo")
    assert places.parse_clock("3:30 pm tokyo")[:3] == (15, 30, True)
    assert places.parse_clock("15:00 tokyo")[:3] == (15, 0, False)
    assert places.parse_clock("12am x")[:2] == (0, 0) and places.parse_clock("12pm x")[:2] == (12, 0)
    assert places.parse_clock("13pm x") is None and places.parse_clock("25:00 x") is None and places.parse_clock("3 tokyo") is None


def test_the_card_in_the_page(client):
    html = client.get("/search?q=ethiopia+time+to+germany+time").get_data(as_text=True)
    assert 'class="card small zones"' in html and re.search(r"germany is \d hours? behind ethiopia", html)  # 1 in summer, 2 in winter


# --- places nook has to look up ---------------------------------------------------

import asyncio  # noqa: E402
import json  # noqa: E402


@pytest.fixture
def learned_clean():
    places.LEARNED.clear()
    yield
    places.LEARNED.clear()


class FakeGeocoder:
    """Stands in for Open-Meteo: one canned answer, and a record of what was asked."""

    def __init__(self, text=None, fail=False):
        self.text, self.fail, self.asked = text or read("open_meteo_bonn.json"), fail, []

    async def get(self, url, params=None, **kw):
        self.asked.append(params["name"])
        if self.fail:
            raise RuntimeError("down")
        text = self.text

        class Reply:
            def raise_for_status(self): pass
            def json(self): return json.loads(text)
        return Reply()


def test_bonn_is_not_in_the_time_zone_tables_but_other_places_are(learned_clean):
    assert places.resolve("bonn") is None
    assert places.resolve("addis ababa").zone == "Africa/Addis_Ababa"


def test_the_geocoder_answer_is_read_carefully():
    data = json.loads(read("open_meteo_bonn.json"))
    assert places.parse_geocode(data, "bonn") == ("Europe/Berlin", "bonn, germany")   # the big one, not the airport or Bonnie
    assert places.parse_geocode(data, "bon") is None and places.parse_geocode({}, "bonn") is None
    assert places.parse_geocode(data, "bonn cologne airport") is None                  # airports are not places


def test_what_needs_looking_up(learned_clean):
    assert places.unknown_places("addis ababa time to bonn time") == ["bonn"]
    assert places.unknown_places("bonn time to addis ababa time") == ["bonn"]
    assert places.unknown_places("time in hallstatt") == ["hallstatt"]
    assert places.unknown_places("3pm in tokyo to bonn") == ["bonn"]
    for ordinary in ["python tutorial", "paris to london", "how to cook", "usd to eur", "define serendipity",
                     "ethiopia time to germany time", "time in tokyo", "5 to 7", "bonn to berlin", ""]:
        assert places.unknown_places(ordinary) == [], ordinary                          # nothing to look up


def test_learning_a_place_makes_the_question_answerable(learned_clean):
    client = FakeGeocoder()
    assert places.answer("addis ababa time to bonn time", NOW) is None
    assert asyncio.run(cards.lookup(client, "addis ababa time to bonn time")) is None   # it only learns
    assert client.asked == ["bonn"]
    card = places.answer("addis ababa time to bonn time", NOW)
    assert card["kind"] == "zones" and card["first"]["clock"] == "21:35" and card["second"]["clock"] == "20:35"
    assert card["note"].startswith("bonn is 1 hour behind addis ababa")
    assert "bonn, germany" in card["second"]["zone"] and card["credit"] == "place lookup: open-meteo.com"
    assert places.answer("ethiopia time to germany time", NOW)["credit"] == ""           # no credit when nothing was looked up
    assert places.answer("time in bonn", NOW)["clock"] == "20:35"


def test_a_place_is_only_asked_about_once(learned_clean):
    client = FakeGeocoder()
    asyncio.run(places.learn(client, ["bonn"]))
    asyncio.run(places.learn(client, ["bonn"]))
    assert client.asked == ["bonn"]
    nothing = FakeGeocoder('{"results": []}')
    asyncio.run(places.learn(nothing, ["zzzzz"]))
    asyncio.run(places.learn(nothing, ["zzzzz"]))                                         # "no such place" is remembered too
    assert nothing.asked == ["zzzzz"]


def test_a_geocoder_that_is_down_is_not_remembered_as_no_such_place(learned_clean):
    asyncio.run(places.learn(FakeGeocoder(fail=True), ["bonn"]))
    assert "bonn" not in places.LEARNED
    retry = FakeGeocoder()
    asyncio.run(places.learn(retry, ["bonn"]))
    assert retry.asked == ["bonn"] and places.resolve("bonn")


def test_at_most_two_places_are_looked_up_at_once(learned_clean):
    client = FakeGeocoder()
    asyncio.run(places.learn(client, ["a1", "b2", "c3"]))
    assert len(client.asked) == 2


def test_the_page_gets_the_card_after_the_lookup(client, monkeypatch, learned_clean):
    async def real_lookup(query, picked):
        return await cards.lookup(FakeGeocoder(), query)

    monkeypatch.setattr(nook, "ask_card", real_lookup)
    html = client.get("/search?q=addis+ababa+time+to+bonn+time").get_data(as_text=True)
    assert 'class="card small zones"' in html and "place lookup: open-meteo.com" in html
