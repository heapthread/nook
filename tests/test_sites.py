import pytest

import app as nook
from engines import Image, Result, Video


@pytest.fixture
def client():
    nook.cache.clear()
    nook.hits.clear()
    return nook.app.test_client()


def res(url, rank=0):
    return Result(title=url, url=url, snippet="s", engines=["bing"], rank=rank)


def serve(monkeypatch, urls):
    async def fake(query, page=1, chosen=None, period=None, **kw):
        return [res(u, i) for i, u in enumerate(urls)], []
    monkeypatch.setattr(nook, "ask", fake)


def cookies(r):
    return " | ".join(r.headers.getlist("Set-Cookie"))


@pytest.mark.parametrize("text, site", [
    ("pinterest.com", "pinterest.com"), ("https://www.Pinterest.com/pin/123?x=1", "pinterest.com"),
    ("  www.reddit.com/r/python ", "reddit.com"), ("bbc.co.uk", "bbc.co.uk"), ("HTTP://Old.Reddit.com", "old.reddit.com"),
])
def test_sites_are_cleaned(text, site):
    with nook.app.test_request_context():
        assert nook.clean_site(text) == site


@pytest.mark.parametrize("text", ["", "pinterest", "not a site", "a b.com", "-x.com", "x.c", "javascript:alert(1)", "<b>.com", "x" * 100 + ".com"])
def test_things_that_are_not_sites(text):
    with nook.app.test_request_context():
        assert nook.clean_site(text) is None


def test_a_site_matches_itself_and_its_subdomains_only():
    assert nook.on_site("https://old.reddit.com/x", ["reddit.com"]) and nook.on_site("https://reddit.com/x", ["reddit.com"])
    assert not nook.on_site("https://notreddit.com/x", ["reddit.com"]) and not nook.on_site("https://reddit.com.evil.io/x", ["reddit.com"])
    assert not nook.on_site("", ["reddit.com"])


def test_the_dropdown_has_the_site_boxes(client):
    html = client.get("/").get_data(as_text=True)
    assert 'name="hide"' in html and 'name="prefer"' in html


def test_saving_the_lists(client):
    r = client.post("/engines", data={"hide": "pinterest.com\nhttps://www.quora.com/x, junk ; pinterest.com", "prefer": "wikipedia.org"})
    assert "nook_hide=pinterest.com|quora.com" in cookies(r) and "nook_prefer=wikipedia.org" in cookies(r)
    r = client.post("/engines", data={"hide": "", "prefer": "nonsense"})
    assert "nook_hide=;" in cookies(r) and "nook_prefer=;" in cookies(r)


def test_hidden_sites_are_left_out_and_counted(client, monkeypatch):
    serve(monkeypatch, ["https://a.com/1", "https://www.pinterest.com/2", "https://old.reddit.com/3", "https://b.com/4"])
    client.set_cookie("nook_hide", "pinterest.com|reddit.com")
    html = client.get("/search?q=cats").get_data(as_text=True)
    assert "a.com/1" in html and "b.com/4" in html
    assert "pinterest.com/2" not in html and "reddit.com/3" not in html          # the box listing them is not a result
    assert "2 results hidden by your site list." in html


def test_preferred_sites_come_first_in_the_same_order(client, monkeypatch):
    serve(monkeypatch, ["https://a.com/1", "https://wikipedia.org/2", "https://b.com/3", "https://en.wikipedia.org/4"])
    client.set_cookie("nook_prefer", "wikipedia.org")
    html = client.get("/search?q=cats").get_data(as_text=True)
    order = [html.index(x) for x in ("wikipedia.org/2", "en.wikipedia.org/4", "a.com/1", "b.com/3")]
    assert order == sorted(order)
    assert "hidden by your site list" not in html


def test_no_lists_means_nothing_changes(client, monkeypatch):
    serve(monkeypatch, ["https://a.com/1", "https://b.com/2"])
    html = client.get("/search?q=cats").get_data(as_text=True)
    assert "hidden by" not in html and html.index("a.com/1") < html.index("b.com/2")


def test_the_site_list_applies_to_images_and_videos_too():
    with nook.app.test_request_context(headers={"Cookie": "nook_hide=tiktok.com|pinterest.com"}):
        videos = [Video("a", "https://www.tiktok.com/x", "t"), Video("b", "https://www.youtube.com/watch?v=abcdefghijk", "t")]
        images = [Image("a", "t", "https://i.pinimg.com/x.jpg", "https://www.pinterest.com/pin/1"), Image("b", "t", "https://x.com/1.jpg", "https://x.com/p")]
        assert [v.title for v in nook.apply_sites(videos)[0]] == ["b"]
        assert [i.title for i in nook.apply_sites(images)[0]] == ["b"]            # images are judged by their page, not the file


def test_the_hide_site_button(client):
    r = client.post("/sites", data={"site": "https://www.pinterest.com/pin/1"})
    assert r.status_code == 204 and "nook_hide=pinterest.com" in cookies(r)
    client.set_cookie("nook_hide", "pinterest.com")
    r = client.post("/sites", data={"site": "quora.com"})
    assert "nook_hide=pinterest.com|quora.com" in cookies(r)
    assert client.post("/sites", data={"site": "nonsense"}).status_code == 400
    assert client.post("/sites", data={}).status_code == 400


def test_a_tampered_cookie_is_ignored(client, monkeypatch):
    serve(monkeypatch, ["https://a.com/1"])
    client.set_cookie("nook_hide", "<script>|a b|..|a.com")
    html = client.get("/search?q=cats").get_data(as_text=True)
    assert "a.com/1" not in html.split("<main")[1] and "<script>|" not in html          # only the real site counted
    assert "&lt;script&gt;" not in html


def test_the_lists_show_in_the_dropdown(client):
    client.set_cookie("nook_hide", "pinterest.com|quora.com")
    html = client.get("/").get_data(as_text=True)
    assert "pinterest.com\nquora.com</textarea>" in html


# --- related searches ---------------------------------------------------------------

import asyncio  # noqa: E402
import json  # noqa: E402

import related  # noqa: E402


def test_related_suggestions_are_cleaned():
    raw = json.dumps(["python decorators", ["python decorators", "python  decorators explained", "python decorators examples",
                                              "python decorators examples", "x" * 80, "", 5, "python decorators syntax"]])
    assert related.parse(raw, "Python Decorators") == ["python decorators explained", "python decorators examples", "python decorators syntax"]
    assert related.parse("nope", "x") == [] and related.parse("[]", "x") == [] and related.parse('["x", [1, 2]]', "x") == []


def test_at_most_six():
    raw = json.dumps(["q", [f"q {i}" for i in range(20)]])
    assert len(related.parse(raw, "q")) == 6


class FakeSuggest:
    def __init__(self, fail=False):
        self.calls, self.fail = [], fail

    async def get(self, url, params=None, **kw):
        self.calls.append(params)
        if self.fail:
            raise RuntimeError("down")

        class Reply:
            text = json.dumps(["cats", ["cats", "cats and dogs", "cats musical"]])
            def raise_for_status(self): pass
        return Reply()


def test_suggestions_are_remembered_and_failures_are_not():
    related._cache.clear()
    client = FakeSuggest()
    assert asyncio.run(related.lookup(client, "Cats")) == ["cats and dogs", "cats musical"]
    asyncio.run(related.lookup(client, "cats"))
    assert len(client.calls) == 1
    related._cache.clear()
    assert asyncio.run(related.lookup(FakeSuggest(fail=True), "cats")) == [] and not related._cache


def test_related_searches_in_the_page(client, monkeypatch):
    async def fake(query, picked):
        return ["cats and dogs", "cats musical"]

    monkeypatch.setattr(nook, "ask_related", fake)
    serve(monkeypatch, ["https://a.com/1"])
    html = client.get("/search?q=cats").get_data(as_text=True)
    assert 'class="related"' in html and 'href="/search?q=cats%20and%20dogs"' in html
    assert 'class="related"' not in client.get("/search?q=cats&t=images").get_data(as_text=True)
    assert 'class="related"' not in client.get("/search?q=cats&page=2").get_data(as_text=True)


REAL_ASK_RELATED = nook.ask_related  # captured before the offline fixture replaces it


def test_related_only_asks_while_duckduckgo_is_on(monkeypatch):
    class Engine:
        def __init__(self, name):
            self.NAME = name

    calls = []

    async def fake_lookup(client, query):
        calls.append(query)
        return ["asked"]

    monkeypatch.setattr(related, "lookup", fake_lookup)
    assert asyncio.run(REAL_ASK_RELATED("cats", [Engine("bing"), Engine("duckduckgo")])) == ["asked"]
    assert asyncio.run(REAL_ASK_RELATED("cats", [Engine("bing"), Engine("yahoo")])) == [] and calls == ["cats"]
