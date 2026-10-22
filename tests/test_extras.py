import json

import pytest

import app as nook
import lenses
import proxy
import reader
import related
import tools
from engines import Result


@pytest.fixture
def client(monkeypatch):
    nook.cache.clear()
    nook.hits.clear()
    nook._mine.clear()
    return nook.app.test_client()


def got(client, path, **query):
    r = client.get(path, query_string=query) if query else client.get(path)
    return r, r.get_data(as_text=True)


# --- lenses -------------------------------------------------------------------------

def test_a_lens_is_a_list_of_sites_added_to_the_search():
    assert lenses.apply("flask", ["a.com", "b.org"]) == "flask (site:a.com OR site:b.org)"
    assert lenses.apply("flask", []) == "flask"


def test_config_changes_lenses():
    table = lenses.table({"recipes": ["seriouseats.com"], "code": ["github.com"], "academic": []})
    assert table["recipes"] == ["seriouseats.com"] and table["code"] == ["github.com"]
    assert "academic" not in table and "discussions" in table
    assert lenses.table({"bad": "not a list"}) == lenses.table(None)


def test_a_lens_changes_what_the_engines_hear_but_not_the_box(client, monkeypatch):
    heard = []

    async def ask(query, page=1, chosen=None, period=None, **kw):
        heard.append(query)
        return [Result(title="t", url="https://www.reddit.com/r/x", snippet="s", engines=["duckduckgo"], rank=0)], []
    monkeypatch.setattr(nook, "ask", ask)
    r, html = got(client, "/search", q="sourdough", l="discussions")
    assert heard == ["sourdough (site:reddit.com OR site:news.ycombinator.com OR site:stackoverflow.com "
                     "OR site:stackexchange.com OR site:lemmy.world OR site:quora.com)"]
    assert 'value="sourdough"' in html and '<span class="on">discussions</span>' in html
    assert "only reddit.com" in html
    assert "l=discussions" in html.split('class="pager"')[1] if 'class="pager"' in html else True


def test_an_unknown_lens_is_ignored(client, monkeypatch):
    heard = []

    async def ask(query, page=1, chosen=None, period=None, **kw):
        heard.append(query)
        return [], []
    monkeypatch.setattr(nook, "ask", ask)
    got(client, "/search", q="sourdough", l="nonsense")
    assert heard == ["sourdough"]


def test_a_lens_search_has_no_card_and_is_cached_apart(client, monkeypatch):
    asked = []

    async def card(query, picked):
        asked.append(query)
        return {"kind": "fact", "big": "x", "small": "y"}
    monkeypatch.setattr(nook, "ask_card", card)
    plain = got(client, "/search", q="5 plus 5")[1]
    lens = got(client, "/search", q="5 plus 5", l="code")[1]
    assert 'class="card small"' in plain and 'class="card small"' not in lens


# --- shared settings ----------------------------------------------------------------

def test_a_shared_link_carries_the_settings(client):
    r, html = got(client, "/search", q="x", eng="bing.yahoo", reg="de-de", saf="strict", per="w")
    assert 'data-share="eng=bing.yahoo&amp;per=w&amp;reg=de-de&amp;saf=strict"' in html
    assert "t=images&amp;eng=bing.yahoo" in html                   # tabs keep them
    assert "Set-Cookie" not in r.headers                          # but nothing is saved in the visitor's browser


def test_without_a_shared_link_the_cookies_decide(client):
    client.set_cookie("nook_region", "fr-fr")
    html = got(client, "/search", q="x")[1]
    assert 'data-share="reg=fr-fr"' in html and "&amp;reg=" not in html.split('class="tabs"')[1].split("</nav>")[0]


def test_a_link_cannot_set_nonsense(client):
    html = got(client, "/search", q="x", reg="zz-zz", saf="weird", per="q", eng="nothing")[1]
    assert 'data-share=""' in html


# --- suggestions --------------------------------------------------------------------

def test_suggestions(client, monkeypatch):
    async def fake(prefix):
        return [prefix + " one", prefix + " two"]
    monkeypatch.setattr(nook, "ask_suggest", fake)
    assert client.get("/suggest", query_string={"q": "py"}).get_json() == ["py one", "py two"]
    assert client.get("/suggest", query_string={"q": "p"}).get_json() == []
    client.set_cookie("nook_suggest", "off")
    assert client.get("/suggest", query_string={"q": "py"}).get_json() == []


def test_suggestions_need_duckduckgo(client, monkeypatch):
    async def fake(prefix):
        return ["x"]
    monkeypatch.setattr(nook, "ask_suggest", fake)
    client.set_cookie("nook_engines", "bing")
    assert client.get("/suggest", query_string={"q": "py"}).get_json() == []


def test_suggestions_are_rate_limited(client, monkeypatch):
    async def fake(prefix):
        return []
    monkeypatch.setattr(nook, "ask_suggest", fake)
    codes = {client.get("/suggest", query_string={"q": "py"}).status_code for _ in range(260)}
    assert 429 in codes


def test_suggestion_parsing():
    import asyncio

    class Client:
        async def get(self, url, params=None):
            class R:
                def raise_for_status(self):
                    pass

                def json(self):
                    return ["py", ["python", "python", "  pyt  hon ", 5, "x" * 200]]
            return R()
    related._typed.clear()
    assert asyncio.run(related.suggest(Client(), "py")) == ["python", "pyt hon"]


def test_the_switch_is_in_the_page(client):
    assert 'data-suggest="1"' in got(client, "/")[1]
    client.set_cookie("nook_suggest", "off")
    assert 'data-suggest="0"' in got(client, "/")[1]


# --- peek ---------------------------------------------------------------------------

def test_peek_gives_the_opening_of_a_signed_address(client, monkeypatch):
    url = "https://example.com/post"
    monkeypatch.setattr(reader, "article", lambda u, f="": (["short", "A long enough first paragraph of the page. " * 3,
                                                           "And a second one that goes on for a while longer. " * 4], "page"))
    r = client.get("/peek", query_string={"u": url, "s": proxy.sign(url, "read")})
    text = r.get_json()["text"]
    assert r.status_code == 200 and text.startswith("A long enough") and "short" not in text and len(text) <= 703


def test_peek_refuses_unsigned_addresses_and_empty_pages(client, monkeypatch):
    assert client.get("/peek", query_string={"u": "http://127.0.0.1/", "s": "bad"}).status_code == 403
    assert client.get("/peek", query_string={"u": "http://127.0.0.1/"}).status_code == 403
    url = "https://example.com/blocked"
    monkeypatch.setattr(reader, "article", lambda u, f="": ([], "partial"))
    assert client.get("/peek", query_string={"u": url, "s": proxy.sign(url, "read")}).get_json() == {"text": ""}


def test_results_say_when_engines_agree(client, monkeypatch):
    async def ask(query, page=1, chosen=None, period=None, **kw):
        return [Result(title="both", url="https://a.example/1", snippet="s", engines=["duckduckgo", "bing"], rank=0),
                Result(title="one", url="https://b.example/2", snippet="s", engines=["yahoo"], rank=1)], []
    monkeypatch.setattr(nook, "ask", ask)
    html = got(client, "/search", q="x")[1]
    assert html.count('class="agree"') == 1 and 'title="found by duckduckgo, bing"' in html


# --- the ctrl+k box and the pages of their own ----------------------------------------

def test_palette_data(client):
    r = client.get("/palette.json")
    data = r.get_json()
    assert ["tools", "/tools"] in data["pages"] and "w" in data["bangs"]
    assert ["translate", "hello in german"] in data["examples"] or any(e[1] == "hello in german" for e in data["examples"])
    assert "max-age" in r.headers["Cache-Control"]


def test_every_example_is_something_nook_answers():
    """An example on /tools that turned into an ordinary search would be a broken promise."""
    import cards
    import figures
    import plot
    import translate
    import facts
    import weather
    import dates
    import wordtools
    import answers
    import places
    import me
    import netinfo
    import packages
    import routes
    import earth
    import history
    skipped = ("by date", "narrow it down", "anything on wikipedia", "weather", "time anywhere", "money", "definitions", "facts", "prices")
    for _, items in tools.CATALOG:
        for title, examples in items:
            if title in skipped:
                continue
            for example in examples:
                handled = (cards.local(example) or answers.answer(example) or translate.parse(example)
                           or wordtools.parse(example) or facts.parse(example)
                           or routes.parse(example) or earth.parse(example) or history.parse(example)
                           or me.answer(example, "1.2.3.4", "UA") or packages.parse(example) or netinfo.parse(example))
                assert handled, f"{title}: {example}"
    assert weather.place_in("weather in bonn") and facts.parse("capital of peru") and cards.define_word("define serendipity")


def test_the_pages_open(client):
    for path in ("/tools", "/shelf", "/code", "/today", "/maps", "/news?w=mine"):
        r, html = got(client, path)
        assert r.status_code == 200 and "nook" in html, path
    html = got(client, "/tools")[1]
    assert "hello in german" in html and "!yt" in html and "discussions" in html
    footer = html.split("<footer>")[1]
    for page in ("about", "news", "tools"):      # the footer stays small; /tools lists every other page
        assert f'href="/{page}"' in footer
    assert footer.count("<a ") == 3
    for page in ("maps", "shelf", "code", "today", "travel", "world", "learn", "watching", "status", "versus"):
        assert f'href="/{page}"' in html


def test_the_code_page(client, monkeypatch):
    async def ask(query):
        return [("github", [{"title": "pallets/flask", "url": "https://github.com/pallets/flask", "text": "a web framework", "meta": "Python"}]),
                ("npm", [])][:1], ["mdn"]
    monkeypatch.setattr(nook, "ask_code", ask)
    html = got(client, "/code", q="flask")[1]
    assert "pallets/flask" in html and "mdn didn't answer" in html


def test_code_search_parsers():
    import codesearch
    assert codesearch._repos({"items": [{"full_name": "a/b", "html_url": "https://github.com/a/b", "description": None,
                                          "stargazers_count": 1200, "language": "Go"}]})[0]["meta"] == "Go · 1,200 stars"
    assert codesearch._npm({"objects": [{"package": {"name": "x", "version": "1.0.0", "links": {"npm": "https://n/x"}}}]})[0]["url"] == "https://n/x"
    assert codesearch._mdn({"documents": [{"title": "fetch", "mdn_url": "/en-US/docs/Web/API/fetch", "summary": "s"}]})[0]["url"].startswith("https://developer.mozilla.org/")
    assert codesearch._so({"items": [{"title": "a &amp; b", "link": "https://so/1", "score": 3, "answer_count": 2, "tags": ["python"]}]})[0]["title"] == "a & b"
    assert codesearch._pypi({"info": {"name": "flask", "summary": "s", "version": "3"}})[0]["url"] == "https://pypi.org/project/flask/"
    assert codesearch._pypi({}) == []


def test_today_remembers_choices_in_a_cookie(client, monkeypatch):
    r = client.post("/today", data={"weather": "bonn\nnew york", "clocks": "tokyo", "news": "on"})
    cookie = " ".join(r.headers.getlist("Set-Cookie"))
    assert r.status_code == 303 and "nook_today=" in cookie and "new_york" in cookie
    assert nook.app.test_request_context  # the cookie is read back below

    async def ask(weather_places, clock_places):
        return [{"temp": "12°C", "place": "bonn", "text": "cloudy", "feels": "10°C", "days": [{"low": "8°", "high": "13°"}]}], \
               [{"kind": "time", "clock": "21:05", "place": "tokyo", "day": "friday", "zone": "JST"}]

    async def news(selected):
        return [], []
    monkeypatch.setattr(nook, "ask_today", ask)
    monkeypatch.setattr(nook, "ask_news", news)
    client.set_cookie("nook_today", "bonn~new_york|tokyo|1")
    html = got(client, "/today")[1]
    assert "12°C" in html and "21:05" in html and "headlines" in html and "bonn\nnew york" in html


def test_today_cleans_what_it_stores(client):
    r = client.post("/today", data={"weather": "bonn;<script>\n\n", "clocks": "", "news": ""})
    cookie = " ".join(r.headers.getlist("Set-Cookie"))
    assert "<" not in cookie and ";<" not in cookie.split("nook_today=")[1].split(";")[0]
    r = client.post("/today", data={})
    assert "nook_today=;" in " ".join(r.headers.getlist("Set-Cookie"))


# --- your own feeds --------------------------------------------------------------------

RSS = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>My blog</title>
<item><title>First post</title><link>https://blog.example/1</link><pubDate>Mon, 20 Oct 2026 10:00:00 GMT</pubDate></item>
<item><title>Second post</title><link>https://blog.example/2</link></item></channel></rss>"""


def test_a_feed_can_be_added_and_read(client, monkeypatch):
    monkeypatch.setattr(proxy, "is_public", lambda u: True)
    monkeypatch.setattr(proxy, "fetch_feed", lambda u: RSS)
    r = client.post("/feeds", data={"act": "add", "url": "https://blog.example/feed.xml"})
    assert r.status_code == 303 and "nook_myfeeds=" in " ".join(r.headers.getlist("Set-Cookie"))
    html = got(client, "/news", w="mine")[1]
    assert "First post" in html and "Second post" in html and "My blog" in html
    assert "https://blog.example/feed.xml" in html and "mine" in html.split('class="tabs"')[1]
    assert 'href="/read?u=https%3A%2F%2Fblog.example%2F1' in html


def test_unsafe_feed_addresses_are_refused(client, monkeypatch):
    r = client.post("/feeds", data={"act": "add", "url": "http://127.0.0.1:8080/"})
    assert "can%27t%20reach" in r.headers["Location"] and "nook_myfeeds=http" not in " ".join(r.headers.getlist("Set-Cookie"))
    r = client.post("/feeds", data={"act": "add", "url": "file:///etc/passwd"})
    assert "web%20address" in r.headers["Location"]
    r = client.post("/feeds", data={"act": "add", "url": "javascript:alert(1)"})
    assert "web%20address" in r.headers["Location"]


def test_feeds_can_be_removed_and_are_limited(client, monkeypatch):
    monkeypatch.setattr(proxy, "is_public", lambda u: True)
    for n in range(nook.MINE_MAX):
        client.post("/feeds", data={"act": "add", "url": f"https://f{n}.example/rss"})
    r = client.post("/feeds", data={"act": "add", "url": "https://one-too-many.example/rss"})
    assert "already" in r.headers["Location"]
    r = client.post("/feeds", data={"act": "remove", "url": "https://f0.example/rss"})
    assert "f0.example" not in " ".join(r.headers.getlist("Set-Cookie")) and "f1.example" in " ".join(r.headers.getlist("Set-Cookie"))


def test_a_broken_feed_is_named_not_fatal(client, monkeypatch):
    monkeypatch.setattr(proxy, "is_public", lambda u: True)
    client.set_cookie("nook_myfeeds", "https://down.example/rss")

    def boom(url):
        raise proxy.Refused("nope")
    monkeypatch.setattr(proxy, "fetch_feed", boom)
    html = got(client, "/news", w="mine")[1]
    assert "down.example didn't answer" in html


def test_feed_titles():
    import news
    assert news.feed_title(RSS) == "My blog"
    assert news.feed_title(b"<feed xmlns='http://www.w3.org/2005/Atom'><title>An atom feed</title></feed>") == "An atom feed"
    assert news.feed_title(b"not xml") == ""


def test_backup_knows_the_new_cookies():
    js = open(nook.ROOT / "static" / "home.js", encoding="utf-8").read()
    for name in ("nook_pics", "nook_suggest", "nook_myfeeds", "nook_today"):
        assert name in js


def test_nothing_new_reaches_another_site(client):
    for path in ("/tools", "/shelf", "/code", "/today", "/maps", "/news?w=mine"):
        r, html = got(client, path)
        assert "default-src 'none'" in r.headers["Content-Security-Policy"]
        assert "http://" not in html.replace("http://www.w3.org", "")
