import asyncio
import math

import pytest

import app as nook
import cards
import facts
import figures
import plot
import translate


def run(coro):
    return asyncio.run(coro)


class Reply:
    def __init__(self, data):
        self.data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self.data


# --- percentages and number bases -------------------------------------------------

@pytest.mark.parametrize("query, big", [
    ("15% of 80", "12"), ("what is 15 percent of 80", "12"), ("20 is what percent of 50", "40%"),
    ("what percent of 50 is 20", "40%"), ("increase 80 by 15%", "92"), ("decrease 80 by 25%", "60"),
    ("20% off 80", "64"), ("change from 50 to 80", "+60%"), ("change from 80 to 40", "-50%"),
    ("255 in binary", "0b11111111"), ("255 in hex", "0xff"), ("0xff to decimal", "255"),
    ("ff hex to decimal", "255"), ("binary 1010 to decimal", "10"), ("1,000 in octal", None),
])
def test_percentages_and_bases(query, big):
    card = figures.answer(query)
    if big is None:
        assert card is None or card["kind"] == "fact"
    else:
        assert card["kind"] == "fact" and card["big"] == big


@pytest.mark.parametrize("query", ["hello in german", "10 in 20", "ab in binary", "what percent", "0 of 0", "cafe to decimal"])
def test_things_that_are_not_sums_are_left_alone(query):
    assert figures.answer(query) is None


def test_dividing_by_zero_is_not_an_error():
    assert figures.answer("5 is what percent of 0") is None


# --- plotting -----------------------------------------------------------------

@pytest.mark.parametrize("text, x, expected", [
    ("x^2+1", 2, 5), ("2x", 4, 8), ("3(x+1)", 1, 6), ("(x+1)(x-1)", 3, 8), ("-x", 2, -2), ("2^3^2", 0, 512),
    ("sqrt(x)", 9, 3), ("sin x", 0, 0), ("x*pi", 1, math.pi), ("abs(x)", -4, 4), ("2^-1", 0, 0.5), ("ln(e)", 0, 1),
])
def test_the_expression_parser(text, x, expected):
    f, _ = plot.compile_expr(text)
    assert f(x) == pytest.approx(expected)


@pytest.mark.parametrize("text", ["__import__('os')", "x; y", "open(1)", "x.real", "[1]", "2 +", "((x)", "sin(", "foo(x)"])
def test_nothing_but_maths_is_accepted(text):
    with pytest.raises((plot.Bad, RecursionError)):
        plot.compile_expr(text)


def test_domain_errors_leave_gaps_not_crashes():
    f, _ = plot.compile_expr("1/x")
    assert math.isnan(f(0))
    g, _ = plot.compile_expr("sqrt(x)")
    assert math.isnan(g(-1))
    h, _ = plot.compile_expr("(-8)^0.5")
    assert math.isnan(h(0))


def test_plot_queries():
    assert plot.parse("plot sin(x)") == (["sin(x)"], None, None)
    assert plot.parse("graph x^2 - 3 from -5 to 5") == (["x^2 - 3"], -5.0, 5.0)
    assert plot.parse("y = 2x + 1") == (["2x + 1"], None, None)
    assert plot.parse("plot sin(x), cos(x)")[0] == ["sin(x)", "cos(x)"]
    assert plot.parse("plot") is None and plot.parse("sin(x)") is None and plot.parse("flask plot") is None


def test_a_plot_card_is_drawn():
    card = plot.answer("plot x^2 from -3 to 3")
    assert card["kind"] == "plot" and len(card["series"]) == 1 and card["series"][0]["d"].startswith("M")
    assert card["axis_y"] is not None and card["note"] == "x from -3 to 3"
    two = plot.answer("plot sin(x), cos(x)")
    assert len(two["series"]) == 2 and "6.283" in two["note"]
    assert plot.answer("plot hello") is None and plot.answer("plot 1+") is None


def test_an_asymptote_is_not_joined_up():
    card = plot.answer("plot 1/x")
    assert card["series"][0]["d"].count("M") >= 2


def test_plots_are_never_remembered_and_show_up(monkeypatch):
    nook.cache.clear()
    nook.hits.clear()
    html = nook.app.test_client().get("/search", query_string={"q": "plot sin(x)"}).get_data(as_text=True)
    assert 'class="card plot"' in html and 'class="curve c0"' in html and "y = sin(x)" in html


# --- translate ----------------------------------------------------------------

@pytest.mark.parametrize("query, expected", [
    ("hello in german", ("hello", None, "de")),
    ("translate good night to japanese", ("good night", None, "ja")),
    ("translate hello from english to french", ("hello", "en", "fr")),
    ("how do you say thank you in spanish", ("thank you", None, "es")),
    ('translate "see you soon" into italian', ("see you soon", None, "it")),
])
def test_translate_queries(query, expected):
    assert translate.parse(query) == expected


@pytest.mark.parametrize("query", ["time in german", "5 in german", "weather in english", "hello world", "translate hello",
                                   "100 usd in eur", "translate hello to klingon"])
def test_other_queries_are_not_translations(query):
    assert translate.parse(query) is None


def test_translate_answers():
    good = {"responseStatus": 200, "responseData": {"translatedText": "Gute Nacht &amp; so", "detectedLanguage": "en"}}
    card = translate.parse_answer(good, "good night", "de")
    assert card["result"] == "Gute Nacht & so" and card["from"] == "english" and card["to"] == "german"
    assert translate.parse_answer({"responseStatus": 429, "responseData": {"translatedText": "x"}}, "a", "de") is None
    assert translate.parse_answer({"responseStatus": 200, "responseData": {"translatedText": "MYMEMORY WARNING: QUOTA"}}, "a", "de") is None
    assert translate.parse_answer({}, "a", "de") is None


def test_translate_lookup_asks_once_and_remembers():
    translate._cache.clear()
    calls = []

    class Client:
        async def get(self, url, params=None):
            calls.append(params)
            return Reply({"responseStatus": 200, "responseData": {"translatedText": "hallo", "detectedLanguage": "en"}})
    c = Client()
    assert run(translate.lookup(c, "hello in german"))["result"] == "hallo"
    assert run(translate.lookup(c, "hello in german"))["result"] == "hallo"
    assert len(calls) == 1 and calls[0]["langpair"] == "autodetect|de"
    assert run(translate.lookup(c, "hello world")) is None


# --- facts and prices -----------------------------------------------------------

@pytest.mark.parametrize("query, expected", [
    ("capital of peru", ("peru", "capital")), ("population of japan", ("japan", "population")),
    ("germany population", ("germany", "population")), ("what is the capital of the netherlands", ("netherlands", "capital")),
    ("germany facts", ("germany", None)), ("facts about brazil", ("brazil", None)),
    ("what languages are spoken in switzerland", ("switzerland", "languages")),
    ("currency of japan", ("japan", "currency")),
])
def test_place_fact_queries(query, expected):
    assert facts.parse_place(query) == expected


@pytest.mark.parametrize("query", ["python population genetics tutorial", "capital", "how to be a capital letter", "facts"])
def test_other_queries_are_not_place_facts(query):
    assert facts.parse_place(query) is None


def test_price_queries():
    assert facts.parse_price("aapl stock") == ("aapl", False)
    assert facts.parse_price("stock price of apple") == ("apple", False)
    assert facts.parse_price("bitcoin price") == ("bitcoin", True)
    assert facts.parse_price("price of ethereum") == ("ethereum", True)
    assert facts.parse_price("hello") is None


def test_numbers_said_like_people_say_them():
    assert facts.human(83_280_000) == "83.3 million"
    assert facts.human(1_410_000_000) == "1.4 billion"
    assert facts.human(124_000_000) == "124 million"
    assert facts.human(8_300) == "8,300"


def statement(value, when=None, rank="normal", **extra):
    s = {"rank": rank, "mainsnak": {"datavalue": {"value": value}}}
    if when:
        s["qualifiers"] = {"P585": [{"datavalue": {"value": {"time": when}}}]}
    s.update(extra)
    return s


def test_the_latest_population_wins_and_rows_are_filled():
    raw = {"population": [statement({"amount": "+80000000"}, "+2019-01-01T00:00:00Z"),
                          statement({"amount": "+83500000"}, "+2023-01-01T00:00:00Z")],
           "area": [statement({"amount": "+357588", "unit": "http://www.wikidata.org/entity/Q712226"})],
           "capital": [statement({"id": "Q64"})], "calling code": [statement("+49")]}
    rows = facts.rows_from(raw, {"Q64": "Berlin"})
    assert rows == {"population": "83.5 million", "area": "357,588 km²", "capital": "Berlin", "calling code": "+49"}


def test_an_area_in_other_units_is_skipped():
    raw = {"area": [statement({"amount": "+5", "unit": "http://www.wikidata.org/entity/Q25343"})]}
    assert facts.rows_from(raw, {}) == {}


def test_place_facts_build_a_card(monkeypatch):
    async def fake_lookup(client, topic, lang="en"):
        return {"qid": "Q1", "title": "Peru", "about": "Country in South America", "flag": "https://f", "url": "https://w"}

    async def fake_raw(client, entity, prop):
        return {"P36": [statement({"id": "Q2"})]}.get(prop, [])

    async def fake_labels(client, ids):
        return {"Q2": "Lima"}
    monkeypatch.setattr(facts.wiki, "lookup", fake_lookup)
    monkeypatch.setattr(facts, "_raw", fake_raw)
    monkeypatch.setattr(facts, "_labels", fake_labels)
    card = run(facts.place_facts(None, "peru", "capital"))
    assert card["kind"] == "facts" and card["big"] == ("capital", "Lima") and card["title"] == "Peru"
    assert run(facts.place_facts(None, "peru", "population")) is None      # nothing known: no card


def test_picking_the_right_quote():
    data = {"quotes": [{"quoteType": "FUTURE", "symbol": "SAAPL=F", "shortname": "Apple futures"},
                       {"quoteType": "EQUITY", "symbol": "AAPL", "shortname": "Apple Inc.", "longname": "Apple Inc."},
                       {"quoteType": "CRYPTOCURRENCY", "symbol": "BTC-USD", "shortname": "Bitcoin USD"}]}
    assert facts.pick_quote(data, "apple", False)["symbol"] == "AAPL"
    assert facts.pick_quote(data, "aapl", False)["symbol"] == "AAPL"
    assert facts.pick_quote(data, "bitcoin", True)["symbol"] == "BTC-USD"
    assert facts.pick_quote(data, "apple", True) is None            # "apple price" is not a crypto question
    assert facts.pick_quote(data, "zzz", False) is None


def test_a_price_card_from_a_chart():
    closes = [100 + i for i in range(10)]
    chart = {"chart": {"result": [{"meta": {"symbol": "AAPL", "currency": "USD", "regularMarketPrice": 109.0},
                                  "indicators": {"quote": [{"close": closes}]}}]}}
    card = facts.parse_chart(chart, {"longname": "Apple Inc."})
    assert card["price"] == "109.00" and card["change"] == "+1.00 (+0.93%)" and card["up"] and card["spark"].startswith("M")
    assert facts.parse_chart({}, {}) is None


def test_every_new_card_has_a_template(monkeypatch):
    nook.cache.clear()
    nook.hits.clear()
    client = nook.app.test_client()
    samples = [
        {"kind": "translate", "original": "hi", "result": "hallo", "from": "english", "to": "german"},
        {"kind": "facts", "title": "Peru", "about": "", "flag": "", "big": ("capital", "Lima"), "rows": [("area", "1 km²")], "url": "u", "source": "Wikidata"},
        {"kind": "stock", "name": "Apple", "symbol": "AAPL", "price": "1.00", "currency": "USD", "change": "+0 (+0%)", "up": True, "spark": "M0 0 L1 1", "note": "n"},
    ]
    for card in samples:
        async def fake(query, picked, card=card):
            return card
        monkeypatch.setattr(nook, "ask_card", fake)
        nook.cache.clear()
        html = client.get("/search", query_string={"q": "x " + card["kind"]}).get_data(as_text=True)
        assert f'class="card {card["kind"]}' in html


def test_lookup_tries_translation_then_facts_then_wikipedia(monkeypatch):
    seen = []

    async def t(client, query):
        seen.append("translate")
        return None

    async def f(client, query, lang="en"):
        seen.append("facts")
        return None

    async def w(client, topic, lang="en"):
        seen.append("wiki")
        return None
    monkeypatch.setattr(cards.translate, "lookup", t)
    monkeypatch.setattr(cards.facts, "lookup", f)
    monkeypatch.setattr(cards.wiki, "lookup", w)
    run(cards.lookup(object(), "capital of peru", with_knowledge=False))
    assert seen == ["translate", "facts", "wiki"] or seen == ["translate", "facts"]


# --- long sentences, and things that used to be true -------------------------------

def test_a_long_sentence_can_be_translated():
    text = "ich esse einen grünen apfel während du eine banane isst"
    assert translate.parse(text + " in english") == (text, None, "en")
    assert translate.parse("one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen "
                           "sixteen seventeen eighteen nineteen twenty twenty one twenty two twenty three twenty four "
                           "twenty five twenty six twenty seven twenty eight twenty nine thirty one in german") is None


def test_text_that_is_already_in_the_language_is_not_a_translation():
    said = {"responseStatus": 200, "responseData": {"translatedText": "how to write a letter", "detectedLanguage": "en"}}
    assert translate.parse_answer(said, "how to write a letter", "en") is None
    assert translate.parse_answer(said, "how to write a letter", "de")["to"] == "german"


@pytest.mark.parametrize("query, expected", [
    ("old capital of germany", ("germany", "former capital")),
    ("former capital of japan", ("japan", "former capital")),
    ("what was the previous capital of brazil", ("brazil", "former capital")),
    ("capitals of germany in history", ("germany", "former capital")),
    ("france old currency", ("france", "former currency")),
    ("what was the currency of germany in history", ("germany", "former currency")),
    ("capital of germany", ("germany", "capital")),
])
def test_queries_about_the_past(query, expected):
    assert facts.parse_place(query) == expected


def test_former_things_are_listed_with_their_years():
    def ended(name_id, start, end):
        q = {"P582": [{"datavalue": {"value": {"time": f"+{end}-01-01T00:00:00Z"}}}]}
        if start:
            q["P580"] = [{"datavalue": {"value": {"time": f"+{start}-01-01T00:00:00Z"}}}]
        return {"mainsnak": {"datavalue": {"value": {"id": name_id}}}, "qualifiers": q}
    labels = {"Q1": "Bonn", "Q2": "Kyoto", "Q3": "Edo"}
    line = facts.former_line([ended("Q1", 1949, 1999), ended("Q1", 1973, 1990), ended("Q2", 794, 1868), ended("Q3", None, 1603)], labels)
    assert line == "Bonn 1949-1999; Kyoto 794-1868; Edo ?-1603"


def test_the_past_comes_from_ended_statements(monkeypatch):
    async def fake_lookup(client, topic, lang="en"):
        return {"qid": "Q183", "title": "Germany", "about": "", "flag": "", "url": "u"}
    seen = []

    async def fake_raw(client, entity, prop, ended=False):
        seen.append((prop, ended))
        q = {"P582": [{"datavalue": {"value": {"time": "+1990-01-01T00:00:00Z"}}}], "P580": [{"datavalue": {"value": {"time": "+1949-01-01T00:00:00Z"}}}]}
        return [{"mainsnak": {"datavalue": {"value": {"id": "Q1"}}}, "qualifiers": q}] if ended else []

    async def fake_labels(client, ids):
        return {"Q1": "Bonn"}
    monkeypatch.setattr(facts.wiki, "lookup", fake_lookup)
    monkeypatch.setattr(facts, "_raw", fake_raw)
    monkeypatch.setattr(facts, "_labels", fake_labels)
    card = run(facts.place_facts(None, "germany", "former capital"))
    assert seen == [("P36", True)] and card["big"] == ("former capitals", "Bonn 1949-1990")


def test_the_map_keeps_old_tiles_while_new_ones_load():
    js = open(nook.ROOT / "static" / "map.js", encoding="utf-8").read()
    assert "sweep" in js and "scale(" in js and "nodes[k].remove()" not in js
