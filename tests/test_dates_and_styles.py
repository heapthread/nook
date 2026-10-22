from datetime import date

import pytest

import app as nook
import daterange
import merge
from engines import Result, duckduckgo

TODAY = date(2026, 10, 22)


@pytest.fixture
def client(monkeypatch):
    nook.cache.clear()
    nook.hits.clear()
    return nook.app.test_client()


@pytest.mark.parametrize("query, clean, span", [
    ("python after:2023", "python", ("2023-01-01", "2026-10-22")),
    ("olympics before:2000", "olympics", ("1995-01-01", "1999-12-31")),
    ("election during:2020", "election", ("2020-01-01", "2020-12-31")),
    ("climate after:2024-01 before:2024-07", "climate", ("2024-01-01", "2024-06-30")),
    ("news during:2024-02", "news", ("2024-02-01", "2024-02-29")),
    ("x after:2024-05-17", "x", ("2024-05-17", "2026-10-22")),
    ("x before:2024-05-17", "x", ("1995-01-01", "2024-05-16")),
    ("x before:2021 after:2023", "x", ("2020-12-31", "2023-01-01")),     # backwards: put the right way round
    ("AFTER:2023 python", "python", ("2023-01-01", "2026-10-22")),
    ("a  b   after:2020", "a b", ("2020-01-01", "2026-10-22")),
])
def test_date_operators(query, clean, span):
    assert daterange.parse(query, TODAY) == (clean, span)


@pytest.mark.parametrize("query", ["python", "before the storm", "after:", "after:20", "xafter:2020", "after:2020x", "site:example.com", "after:2023-13"])
def test_what_is_not_a_date_operator_is_left_alone(query):
    clean, span = daterange.parse(query, TODAY)
    assert span is None and (clean == query or query == "after:2023-13")


def test_a_search_that_is_only_an_operator_keeps_something_to_ask():
    assert daterange.parse("after:2020", TODAY)[0] == "after:2020"


def test_duckduckgo_takes_the_range(monkeypatch):
    sent = []

    class Client:
        async def post(self, url, data=None):
            sent.append(data)

            class R:
                text = ""

                def raise_for_status(s):
                    pass
            return R()
    import asyncio
    asyncio.run(duckduckgo.search(Client(), "x", date_range=("2020-01-01", "2020-12-31"), period="w"))
    assert sent[0]["df"] == "2020-01-01..2020-12-31"      # the exact range wins over "past week"
    asyncio.run(duckduckgo.search(Client(), "x", period="w"))
    assert sent[1]["df"] == "w"


def test_only_engines_that_can_are_asked_and_the_page_says_so(client, monkeypatch):
    heard = []

    async def ask(query, page=1, chosen=None, period=None, region=None, safe=None, date_range=None):
        heard.append((query, [e.NAME for e in chosen], date_range))
        return [Result(title="t", url="https://a.example/1", snippet="s", engines=["duckduckgo"], rank=0)], []
    monkeypatch.setattr(nook, "ask", ask)
    html = client.get("/search", query_string={"q": "python release after:2023"}).get_data(as_text=True)
    assert heard == [("python release", ["duckduckgo"], ("2023-01-01", date.today().isoformat()))]
    assert "only duckduckgo can do that" in html and 'value="python release after:2023"' in html


def test_with_a_lens_both_apply(client, monkeypatch):
    heard = []

    async def ask(query, page=1, chosen=None, period=None, region=None, safe=None, date_range=None):
        heard.append((query, date_range))
        return [], []
    monkeypatch.setattr(nook, "ask", ask)
    client.get("/search", query_string={"q": "flask before:2020", "l": "code"})
    assert heard[0][0].startswith("flask (site:github.com") and heard[0][1][1] == "2019-12-31"


def test_without_duckduckgo_the_operator_is_dropped_not_sent(client, monkeypatch):
    heard = []

    async def ask(query, page=1, chosen=None, period=None, region=None, safe=None, date_range=None):
        heard.append((query, date_range))
        return [], []
    monkeypatch.setattr(nook, "ask", ask)
    client.set_cookie("nook_engines", "bing.yahoo")
    html = client.get("/search", query_string={"q": "python after:2023"}).get_data(as_text=True)
    assert heard == [("python", None)] and "none of your engines can do" in html


def test_a_range_is_part_of_the_remembered_search(client, monkeypatch):
    calls = []

    async def ask(query, page=1, chosen=None, period=None, region=None, safe=None, date_range=None):
        calls.append(date_range)
        return [Result(title="t", url="https://a.example/1", snippet="s", engines=["duckduckgo"], rank=0)], []
    monkeypatch.setattr(nook, "ask", ask)
    client.get("/search", query_string={"q": "python after:2023"})
    client.get("/search", query_string={"q": "python after:2020"})
    client.get("/search", query_string={"q": "python after:2020"})
    assert len(calls) == 2


def test_merge_passes_the_range_only_to_engines_that_take_it():
    seen = {}

    class Takes:
        NAME, SUPPORTS_RANGE = "takes", True

        async def search(self, client, query, page=1, **kw):
            seen["takes"] = kw
            return [Result(title="t", url="https://a.example/1", snippet="", engines=["takes"], rank=0)]

    class Ignores:
        NAME = "ignores"

        async def search(self, client, query, page=1, **kw):
            seen["ignores"] = kw
            return [Result(title="t", url="https://b.example/1", snippet="", engines=["ignores"], rank=0)]
    import asyncio
    merge.strikes.clear()
    asyncio.run(merge.gather(None, [Takes(), Ignores()], "x", date_range=("2020-01-01", "2020-12-31")))
    assert seen["takes"] == {"date_range": ("2020-01-01", "2020-12-31")} and seen["ignores"] == {}


# --- your own styles ------------------------------------------------------------------------------

def test_the_styles_box_and_the_script_that_applies_them(client):
    html = client.get("/").get_data(as_text=True)
    assert 'name="css"' in html and "your own styles" in html
    assert html.index("theme.js") < html.index("style.css")            # applied before the page is drawn
    js = open(nook.ROOT / "static" / "theme.js", encoding="utf-8").read()
    assert "nook.css" in js and "adoptedStyleSheets" in js and "replaceSync" in js
    assert "style-src 'self'" in client.get("/").headers["Content-Security-Policy"]      # and the policy stays strict


def test_the_styles_are_saved_and_backed_up_with_everything_else():
    home = open(nook.ROOT / "static" / "home.js", encoding="utf-8").read()
    assert 'localStorage.setItem("nook.css"' in home and "location.reload()" in home
    assert 'k.indexOf("nook.") === 0' in home          # the backup takes every nook.* key, so the styles come along
