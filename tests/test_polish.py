from pathlib import Path

import pytest

import app as nook
import proxy
from engines import Result, duckduckgo

FIX = Path(__file__).parent / "fixtures"


@pytest.fixture
def client():
    nook.cache.clear()
    nook.hits.clear()
    return nook.app.test_client()


def cookies(response):
    """Every cookie the response sets, as one string."""
    return " | ".join(response.headers.getlist("Set-Cookie"))


def res(url, rank=0, engine="duckduckgo"):
    return Result(title=url, url=url, snippet="s", engines=[engine], rank=rank)


def fake_web(pages, failed=()):
    async def fake(query, page=1, chosen=None, period=None, **kw):
        return list(pages.get(page, [])), list(failed)
    return fake


def test_duckduckgo_next_form_is_found():
    fields = duckduckgo.next_form((FIX / "duckduckgo.html").read_text(encoding="utf-8"))
    assert fields["q"] == "python tutorial" and fields["s"] and fields["vqd"]
    assert duckduckgo.next_form("<html><body>no results</body></html>") is None


def test_more_link_and_second_page_without_repeats(client, monkeypatch):
    pages = {1: [res("https://a.com/1"), res("https://b.com/2", 1)],
             2: [res("https://www.a.com/1/"), res("https://c.com/3")]}  # a.com repeats
    monkeypatch.setattr(nook, "ask", fake_web(pages))
    first = client.get("/search?q=cats").get_data(as_text=True)
    assert "page=2" in first and ">more<" in first and ">back<" not in first
    second = client.get("/search?q=cats&page=2").get_data(as_text=True)
    assert "c.com/3" in second and second.count("a.com/1") == 0   # the repeat is dropped
    assert ">back<" in second and 'href="/search?q=cats"' in second  # back goes to page 1, no ?page


def test_running_out_of_results(client, monkeypatch):
    monkeypatch.setattr(nook, "ask", fake_web({1: [res("https://a.com")]}))
    html = client.get("/search?q=cats&page=3").get_data(as_text=True)
    assert "everything i could find" in html and ">more<" not in html


def test_bad_page_numbers_are_ignored(client, monkeypatch):
    monkeypatch.setattr(nook, "ask", fake_web({1: [res("https://a.com")]}))
    assert client.get("/search?q=cats&page=banana").status_code == 200
    assert client.get("/search?q=cats&page=-4").status_code == 200


def test_answered_by_line(client, monkeypatch):
    monkeypatch.setattr(nook, "ask", fake_web({1: [res("https://a.com")]}, failed=["bing"]))
    html = client.get("/search?q=cats").get_data(as_text=True)
    assert "answered by duckduckgo" in html and "bing didn't answer" in html


def test_empty_states(client, monkeypatch):
    names = [e.NAME for e in nook.active]
    monkeypatch.setattr(nook, "ask", fake_web({}, failed=names))
    assert "nobody answered just now" in client.get("/search?q=zzz").get_data(as_text=True)
    monkeypatch.setattr(nook, "ask", fake_web({}, failed=[]))
    html = client.get("/search?q=zzz").get_data(as_text=True)
    assert "nothing found for" in html and "try fewer words" in html


def test_images_offer_no_more_link(client, monkeypatch):
    from engines import Image

    async def fake(engine, query, page=1, **kw):
        return [Image("t", "https://t.example/1.jpg", "https://f.example/1.jpg", "https://p.example")], []

    monkeypatch.setattr(nook, "ask_media", fake)
    assert ">more<" not in client.get("/search?q=cats&t=images").get_data(as_text=True)


def test_friendly_errors(client):
    r = client.get("/nope")
    assert r.status_code == 404 and "nothing lives here" in r.get_data(as_text=True)
    r = client.get("/img?u=https://x.example/a.png")
    assert r.status_code == 403 and "one nook gave out" in r.get_data(as_text=True)


def test_favicon(client):
    for path in ("/favicon.ico", "/static/favicon.svg"):
        r = client.get(path)
        assert r.status_code == 200 and r.mimetype == "image/svg+xml"
    assert 'rel="icon"' in client.get("/").get_data(as_text=True)


def test_footer_and_about(client):
    html = client.get("/").get_data(as_text=True)
    assert '<footer>' in html and 'href="/about"' in html and "nothing is logged" in html
    about = client.get("/about").get_data(as_text=True)
    assert "duckduckgo" in about and "bing" in about and "nothing is written down" in about


def test_home_is_bare_until_the_pencil_is_used(client):
    html = client.get("/").get_data(as_text=True)
    assert 'class="pencil"' in html and "<svg" in html
    assert 'class="personal" hidden' in html and 'class="editor" hidden' in html
    assert "home.js" in html


def test_throttled_second_page_is_not_called_the_end(client, monkeypatch):
    monkeypatch.setattr(nook, "ask", fake_web({1: [res("https://a.com")]}, failed=["duckduckgo"]))
    html = client.get("/search?q=cats&page=2").get_data(as_text=True)
    assert "nothing more for now" in html and "everything i could find" not in html
    # and that empty answer is not remembered
    monkeypatch.setattr(nook, "ask", fake_web({2: [res("https://c.com")]}))
    assert "c.com" in client.get("/search?q=cats&page=2").get_data(as_text=True)


def test_duckduckgo_paging_tells_the_end_from_a_throttle():
    import asyncio

    class Reply:
        def __init__(self, text):
            self.text = text
        def raise_for_status(self):
            pass

    class Client:
        def __init__(self, text):
            self.text = text
        async def post(self, *a, **k):
            return Reply(self.text)

    last_page = (FIX / "duckduckgo.html").read_text(encoding="utf-8").replace('value="Next"', 'value="x"')
    assert asyncio.run(duckduckgo.search(Client(last_page), "q", 2)) == []
    with pytest.raises(RuntimeError):
        asyncio.run(duckduckgo.search(Client("<html>please wait</html>"), "q", 2))


def test_bing_only_gives_the_first_page():
    import asyncio
    from engines import bing

    class Boom:
        async def get(self, *a, **k):
            raise AssertionError("should not ask bing for page two")

    assert asyncio.run(bing.search(Boom(), "q", 2)) == []


# --- choosing engines -------------------------------------------------------

def spy_ask(seen):
    async def fake(query, page=1, chosen=None, period=None, **kw):
        seen.append([e.NAME for e in chosen])
        return [res("https://a.com", engine=chosen[0].NAME)], []
    return fake


def test_every_engine_is_on_by_default(client, monkeypatch):
    seen = []
    monkeypatch.setattr(nook, "ask", spy_ask(seen))
    html = client.get("/search?q=cats").get_data(as_text=True)
    assert seen == [[e.NAME for e in nook.active]]
    assert 'class="engines"' in html and html.count('name="engine"') == len(nook.active)
    assert html.count(" checked>") == len(nook.active)


def test_the_button_is_on_home_and_web_results_only(client, monkeypatch):
    monkeypatch.setattr(nook, "ask", spy_ask([]))
    assert 'class="engines"' in client.get("/").get_data(as_text=True)
    assert 'class="engines"' in client.get("/search?q=cats").get_data(as_text=True)
    assert 'class="engines"' not in client.get("/news").get_data(as_text=True)


def test_saving_a_choice_sets_a_cookie_and_is_used(client, monkeypatch):
    seen = []
    monkeypatch.setattr(nook, "ask", spy_ask(seen))
    r = client.post("/engines", data={"engine": ["bing", "yahoo"], "next": "/search?q=cats"})
    assert r.status_code == 303 and r.headers["Location"] == "/search?q=cats"
    assert "nook_engines=bing.yahoo" in cookies(r)
    html = client.get("/search?q=cats").get_data(as_text=True)
    assert seen == [["bing", "yahoo"]]
    assert "answered by bing" in html
    assert html.count(" checked>") == 2                      # the panel shows what is on


def test_a_different_choice_is_not_served_from_the_old_cache(client, monkeypatch):
    seen = []
    monkeypatch.setattr(nook, "ask", spy_ask(seen))
    client.get("/search?q=cats")
    client.set_cookie("nook_engines", "bing")
    client.get("/search?q=cats")
    assert len(seen) == 2


def test_choosing_everything_or_nothing_goes_back_to_the_default(client):
    everyone = [e.NAME for e in nook.active]
    r = client.post("/engines", data={"engine": everyone})
    assert "nook_engines=;" in cookies(r)       # deleted
    r = client.post("/engines", data={})
    assert "nook_engines=;" in cookies(r)


def test_unknown_engines_and_bad_redirects_are_ignored(client):
    r = client.post("/engines", data={"engine": ["bing", "evil"], "next": "//evil.example/x"})
    assert r.headers["Location"] == "/" and "nook_engines=bing" in cookies(r)
    assert "evil" not in cookies(r)
    r = client.post("/engines", data={"engine": ["bing"], "next": "https://evil.example"})
    assert r.headers["Location"] == "/"


def test_a_garbled_cookie_means_everything_is_on(client, monkeypatch):
    seen = []
    monkeypatch.setattr(nook, "ask", spy_ask(seen))
    client.set_cookie("nook_engines", "nonsense..also-nonsense")
    client.get("/search?q=cats")
    assert seen == [[e.NAME for e in nook.active]]


def test_wikipedia_is_explained_when_it_stays_off(client):
    assert "wikipedia stays off until a contact is set" in client.get("/").get_data(as_text=True)


# --- results that are easier to scan -----------------------------------------

def test_search_words_are_bold_and_markup_cannot_break():
    mark = nook.mark
    assert str(mark("Learn Python decorators fast", "python decorators")) == "Learn <b>Python</b> <b>decorators</b> fast"
    assert str(mark("a & b <script> 'quote' 39", "amp 39 lt")) == "a &amp; b &lt;script&gt; &#39;quote&#39; <b>39</b>"
    assert str(mark("Search the site", 'site:example.com "the"')) == "Search the site"   # operators and tiny words ignored
    assert str(mark("<i>", "")) == "&lt;i&gt;"


def test_snippets_lose_the_date_and_the_repeated_title():
    from merge import tidy
    assert tidy("Sep 19, 2026 · Decorators take a function as input.", "Decorators in Python - GeeksforGeeks") == \
        ("Decorators take a function as input.", "Sep 19, 2026")
    assert tidy("Python Decorators Introduction Learn Python Decorators in this tutorial.",
                "Python Decorators Introduction - pythonbasics.org") == ("Learn Python Decorators in this tutorial.", "")
    assert tidy("3 days ago - Fresh news here", "Something else entirely")[1] == "3 days ago"
    assert tidy("Plain snippet.", "Title") == ("Plain snippet.", "")
    assert tidy("", "x") == ("", "")


def test_results_show_the_date_and_icons_through_nook(client, monkeypatch):
    async def fake(query, page=1, chosen=None, period=None, **kw):
        return [res("https://www.example.com/post", engine="duckduckgo")], []

    r0 = res("https://www.example.com/post", engine="duckduckgo")
    r0.snippet, r0.date = "Learn decorators here", "Sep 19, 2026"
    async def fake2(query, page=1, chosen=None, period=None, **kw):
        return [r0], []

    monkeypatch.setattr(nook, "ask", fake2)
    html = client.get("/search?q=decorators").get_data(as_text=True)
    assert "Learn <b>decorators</b> here" in html and "Sep 19, 2026" in html
    assert 'class="ico" src="/img?u=https%3A%2F%2Ficons.duckduckgo.com%2Fip3%2Fwww.example.com.ico' in html
    client.set_cookie("nook_engines", "bing")
    nook.cache.clear()
    assert 'class="ico"' not in client.get("/search?q=decorators").get_data(as_text=True)  # no DuckDuckGo, no icons


def test_small_pictures_are_remembered(monkeypatch):
    calls = []

    def fake_get(url, headers, accept, limit):
        calls.append(url)
        return b"\x89PNG", "image/png", None

    monkeypatch.setattr(proxy, "_get", fake_get)
    proxy._small.clear()
    assert proxy.fetch("https://icons.example/a.ico") == (b"\x89PNG", "image/png")
    assert proxy.fetch("https://icons.example/a.ico") == (b"\x89PNG", "image/png")
    assert calls == ["https://icons.example/a.ico"]


def test_script_and_shortcut_hint_are_on_every_page(client):
    for path in ("/", "/search?q=x", "/news", "/about"):
        html = client.get(path).get_data(as_text=True)
        assert "nook.js" in html and "press ? for shortcuts" in html


def test_home_has_places_for_recent_and_saved_but_shows_nothing_yet(client):
    html = client.get("/").get_data(as_text=True)
    assert 'class="recent" hidden' in html and 'class="saved" hidden' in html
    assert 'name="recent"' in html and 'name="showSaved"' in html


# --- time filter ------------------------------------------------------------

def test_the_dropdown_offers_a_time_filter(client):
    html = client.get("/").get_data(as_text=True)
    assert 'name="period"' in html and "past week" in html and 'value="y"' in html


def test_saving_a_time_filter_sets_its_cookie(client):
    r = client.post("/engines", data={"period": "w", "engine": [e.NAME for e in nook.active]})
    assert "nook_period=w" in cookies(r)
    r = client.post("/engines", data={"period": "nonsense"})
    assert "nook_period=;" in cookies(r)  # unknown values just clear it


def test_only_engines_that_can_filter_are_asked(client, monkeypatch):
    seen = []

    async def spy(query, page=1, chosen=None, period=None, **kw):
        seen.append(([e.NAME for e in chosen], period))
        return [res("https://a.com", engine=chosen[0].NAME)], []

    monkeypatch.setattr(nook, "ask", spy)
    client.set_cookie("nook_period", "w")
    html = client.get("/search?q=news").get_data(as_text=True)
    assert seen == [(["duckduckgo", "yahoo"], "w")]
    assert "past week: only duckduckgo and yahoo can do that." in html
    seen.clear(); nook.cache.clear()
    client.set_cookie("nook_period", "y")                      # yahoo has no "past year"
    client.get("/search?q=news")
    assert seen == [(["duckduckgo"], "y")]
    seen.clear(); nook.cache.clear()
    client.set_cookie("nook_engines", "bing.seznam")           # nothing chosen can filter: ask without
    html = client.get("/search?q=news").get_data(as_text=True)
    assert seen == [(["bing", "seznam"], None)] and "can do that" not in html


def test_a_different_period_is_not_served_from_the_old_cache(client, monkeypatch):
    seen = []

    async def spy(query, page=1, chosen=None, period=None, **kw):
        seen.append(period)
        return [res("https://a.com")], []

    monkeypatch.setattr(nook, "ask", spy)
    client.get("/search?q=news")
    client.set_cookie("nook_period", "d")
    client.get("/search?q=news")
    assert seen == [None, "d"]


def test_engines_only_get_the_period_they_understand():
    import asyncio
    import merge

    class Fussy:
        def __init__(self, name, supports):
            self.NAME, self.calls = name, []
            if supports:
                self.SUPPORTS_TIME = {"w"}

        async def search(self, client, query, page=1, **kw):
            self.calls.append(kw)
            return [res(f"https://{self.NAME}.com", engine=self.NAME)]

    a, b = Fussy("a", True), Fussy("b", False)
    asyncio.run(merge.gather(None, [a, b], "q", 1, "w"))
    asyncio.run(merge.gather(None, [a, b], "q", 1, "d"))   # "d" is not in a's set
    assert a.calls == [{"period": "w"}, {}] and b.calls == [{}, {}]


def test_duckduckgo_and_yahoo_send_the_filter():
    import asyncio
    from engines import yahoo

    sent = {}

    class Reply:
        text = ""
        def raise_for_status(self): pass

    class Client:
        async def post(self, url, data=None, **kw):
            sent["ddg"] = data
            return Reply()

        async def get(self, url, params=None, **kw):
            sent["yahoo"] = params
            return Reply()

    asyncio.run(duckduckgo.search(Client(), "q", 1, period="w"))
    asyncio.run(yahoo.search(Client(), "q", 1, period="d"))
    assert sent["ddg"]["df"] == "w" and sent["yahoo"]["btf"] == "d"
    asyncio.run(duckduckgo.search(Client(), "q", 1, period="d"))
    asyncio.run(yahoo.search(Client(), "q", 1, period="y"))   # not supported there: left out
    assert "btf" not in sent["yahoo"]


# --- region and safe search ---------------------------------------------------

def spy_engines(monkeypatch):
    seen = []

    async def spy(query, page=1, chosen=None, period=None, **kw):
        seen.append(([e.NAME for e in chosen], kw))
        return [res("https://a.com", engine=chosen[0].NAME)], []

    monkeypatch.setattr(nook, "ask", spy)
    return seen


def test_the_dropdown_has_region_and_safe_search(client):
    html = client.get("/").get_data(as_text=True)
    assert 'name="region"' in html and 'value="de-de"' in html and ">germany<" in html and ">all regions<" in html
    assert 'name="safe"' in html and ">strict<" in html and ">off<" in html


def test_region_and_safe_search_are_saved_as_cookies(client):
    r = client.post("/engines", data={"region": "de-de", "safe": "strict", "engine": [e.NAME for e in nook.active]})
    assert "nook_region=de-de" in cookies(r) and "nook_safe=strict" in cookies(r)
    r = client.post("/engines", data={"region": "atlantis", "safe": "moderate"})
    assert "nook_region=;" in cookies(r) and "nook_safe=;" in cookies(r)      # unknown values just clear them


def test_a_region_asks_only_engines_that_have_one(client, monkeypatch):
    seen = spy_engines(monkeypatch)
    client.set_cookie("nook_region", "de-de")
    html = client.get("/search?q=news").get_data(as_text=True)
    assert seen == [(["duckduckgo", "yahoo"], {"region": "de-de"})] or seen[0][0] == ["duckduckgo", "yahoo"]
    assert "germany: only duckduckgo and yahoo can do that." in html
    seen.clear(); nook.cache.clear()
    client.set_cookie("nook_region", "jp-jp")                                   # yahoo has no japan site
    client.get("/search?q=news")
    assert seen[0][0] == ["duckduckgo"]
    seen.clear(); nook.cache.clear()
    client.set_cookie("nook_region", "wt-wt")                                   # "all regions": only duckduckgo understands
    assert "all regions: only duckduckgo can do that." in client.get("/search?q=news").get_data(as_text=True)


def test_strict_safe_search_leaves_out_engines_that_cannot_enforce_it(client, monkeypatch):
    seen = spy_engines(monkeypatch)
    client.set_cookie("nook_safe", "strict")
    html = client.get("/search?q=news").get_data(as_text=True)
    assert "seznam" not in seen[0][0] and "duckduckgo" in seen[0][0] and "bing" in seen[0][0]
    assert "strict safe search: only" in html
    seen.clear(); nook.cache.clear()
    client.set_cookie("nook_safe", "off")                                       # "off" never narrows who is asked
    client.get("/search?q=news")
    assert "seznam" in seen[0][0]


def test_nobody_can_do_it_means_asking_without_and_saying_so(client, monkeypatch):
    seen = spy_engines(monkeypatch)
    client.set_cookie("nook_engines", "seznam")
    client.set_cookie("nook_region", "de-de")
    html = client.get("/search?q=news").get_data(as_text=True)
    assert seen[0][0] == ["seznam"] and "none of your engines can do germany" in html


def test_a_new_region_is_not_served_from_the_old_cache(client, monkeypatch):
    seen = spy_engines(monkeypatch)
    client.get("/search?q=news")
    client.set_cookie("nook_region", "fr-fr")
    client.get("/search?q=news")
    assert len(seen) == 2


def test_engines_send_the_settings_they_understand():
    import asyncio
    import regions
    from engines import bing, duckduckgo_videos, yahoo

    sent = {}

    class Reply:
        text = ""
        def raise_for_status(self): pass
        def json(self): return {}

    class Client:
        async def post(self, url, data=None, **kw):
            sent["ddg"] = data
            return Reply()

        async def get(self, url, params=None, **kw):
            sent[url.split("/")[2]] = params
            return Reply()

    asyncio.run(duckduckgo.search(Client(), "q", 1, region="de-de", safe="strict"))
    assert sent["ddg"]["kl"] == "de-de" and sent["ddg"]["kp"] == "1"
    asyncio.run(duckduckgo.search(Client(), "q", 1, safe="off"))
    assert sent["ddg"]["kp"] == "-2" and "kl" not in sent["ddg"]
    asyncio.run(yahoo.search(Client(), "q", 1, region="de-de", safe="strict"))
    assert "de.search.yahoo.com" in sent and sent["de.search.yahoo.com"]["vm"] == "r"
    asyncio.run(yahoo.search(Client(), "q", 1))
    assert "search.yahoo.com" in sent and "vm" not in sent["search.yahoo.com"]
    asyncio.run(bing.search(Client(), "q", 1, safe="strict", region="de-de"))
    assert sent["www.bing.com"] == {"q": "q", "adlt": "strict"}                # bing never gets a region
    assert regions.yahoo_site("uk-en") == "uk" and regions.yahoo_site("jp-jp") is None and regions.yahoo_site("wt-wt") is None
    assert yahoo.can_region("de-de") and not yahoo.can_region("tw-tzh") and not hasattr(bing, "can_region")


def test_engines_only_get_options_they_support():
    import asyncio
    import merge

    class Plain:
        NAME, got = "plain", []
        async def search(self, client, query, page=1, **kw):
            self.got.append(kw)
            return [res("https://plain.com")]

    class Capable(Plain):
        NAME, got = "capable", []
        SUPPORTS_SAFE = True
        def can_region(self, code):
            return code == "de-de"

    p, c = Plain(), Capable()
    asyncio.run(merge.gather(None, [p, c], "q", 1, None, "de-de", "strict"))
    asyncio.run(merge.gather(None, [p, c], "q", 1, None, "fr-fr", "off"))
    assert p.got == [{}, {}] and c.got == [{"region": "de-de", "safe": "strict"}, {"safe": "off"}]


def test_media_tabs_get_region_and_safe_search_where_supported(client, monkeypatch):
    got = []

    async def spy(engine, query, page=1, **kw):
        got.append((engine.NAME, kw))
        return [], []

    monkeypatch.setattr(nook, "ask_media", spy)
    client.set_cookie("nook_region", "de-de")
    client.set_cookie("nook_safe", "strict")
    client.get("/search?q=cats&t=videos")
    client.get("/search?q=cats&t=images")
    assert got == [("duckduckgo videos", {"region": "de-de", "safe": "strict"}),
                   ("bing images", {"region": "de-de", "safe": "strict"})]


# --- notes, backup ------------------------------------------------------------------

def test_the_home_page_has_notes_and_backup(client):
    html = client.get("/").get_data(as_text=True)
    assert 'class="notes" hidden' in html and 'name="notes"' in html                    # off until switched on with the pencil
    assert 'data-act="backup"' in html and 'data-act="restore"' in html and 'type="file"' in html
    assert "a few notes" in html
