import asyncio
from datetime import datetime, timedelta, timezone

import httpx
import pytest

import answers
import app as nook
import merge
import news
from engines import Result


def res(url, rank=0, engine="e"):
    return Result(title=url, url=url, snippet="", engines=[engine], rank=rank)


@pytest.fixture(autouse=True)
def clean():
    merge.resting.clear()
    merge.strikes.clear()
    nook.cache.clear()
    nook.last_good.clear()
    nook.hits.clear()


# --- host collapsing -------------------------------------------------------

def test_site_of():
    assert merge.site_of("https://old.reddit.com/r/a") == "reddit.com"
    assert merge.site_of("https://www.bbc.co.uk/news") == "bbc.co.uk"
    assert merge.site_of("https://example.com/x") == "example.com"


def test_collapse_keeps_two_per_site_in_order():
    rs = [res(f"https://pinterest.com/{i}") for i in range(5)] + [res("https://other.com/1")]
    kept = merge.collapse(rs, 2)
    assert [r.url for r in kept] == ["https://pinterest.com/0", "https://pinterest.com/1", "https://other.com/1"]
    assert merge.collapse(rs, 0) == rs


# --- retry, resting ---------------------------------------------------------

class Engine:
    def __init__(self, name, script):
        self.NAME, self.script, self.calls = name, list(script), 0

    async def search(self, client, query, page=1):
        self.calls += 1
        step = self.script.pop(0) if self.script else []
        if isinstance(step, BaseException):
            raise step
        return step


def run(engines, page=1):
    return asyncio.run(merge.gather(None, engines, "q", page))


def test_one_quick_retry_rescues_a_flaky_engine():
    e = Engine("flaky", [[], [res("https://a.com")]])  # empty (throttled) first, fine second
    results, failed = run([e])
    assert [r.url for r in results] == ["https://a.com"] and failed == [] and e.calls == 2


def test_timeouts_are_not_retried():
    e = Engine("slow", [httpx.ReadTimeout("slow")])
    results, failed = run([e])
    assert results == [] and failed == ["slow"] and e.calls == 1


def test_two_failures_in_a_row_send_an_engine_to_rest_and_a_success_wakes_it():
    e = Engine("bad", [[], [], [], [], [res("https://a.com")]])
    run([e])
    assert not merge.is_resting("bad")           # one failed search is not enough
    run([e])
    assert merge.is_resting("bad")               # two are
    calls = e.calls
    results, failed = run([e])
    assert failed == ["bad"] and e.calls == calls  # left alone while resting
    merge.resting.clear()
    assert run([e])[0] and not merge.is_resting("bad")


def test_empty_later_pages_are_not_failures():
    e = Engine("bing", [[]])
    assert run([e], page=2) == ([], []) and e.calls == 1


# --- answers ----------------------------------------------------------------

def test_bangs():
    assert answers.bang_target("!w sourdough bread") == "https://en.wikipedia.org/wiki/Special:Search?search=sourdough%20bread"
    assert answers.bang_target("sourdough !yt").startswith("https://www.youtube.com/results?search_query=sourdough")
    assert answers.bang_target("!nope x") == "https://duckduckgo.com/?q=%21nope%20x" and answers.bang_target("!w") is None   # a bang we do not know goes to DuckDuckGo
    assert answers.bang_target("!arch pacman", {"arch": "https://wiki.archlinux.org/?search={}"}).endswith("search=pacman")
    assert answers.bang_target("!x y", {"x": "javascript:alert({})"}) is None  # only https templates


@pytest.mark.parametrize("q, expected", [
    ("12*7", "12*7 = 84"), ("2^10", "2^10 = 1,024"), ("(3+4)*5", "(3+4)*5 = 35"),
    ("10/4", "10/4 = 2.5"), ("12 x 7", "12 x 7 = 84"), ("1/3", "1/3 = 0.3333333333"),
])
def test_calculator(q, expected):
    assert answers.calculate(q) == expected


@pytest.mark.parametrize("q", ["42", "hello", "555-1234", "2024-10-21", "9**9**9", "1/0", "os.system('x')", "2 ** 10000", ""])
def test_calculator_refuses(q):
    assert answers.calculate(q) is None


@pytest.mark.parametrize("q, expected", [
    ("5 km in miles", "5 km = 3.10686 miles"), ("100 f to c", "100 f = 37.7778 c"),
    ("2 kg to lb", "2 kg = 4.40925 lb"), ("1 gb in mb", "1 gb = 1,000 mb"),
    ("1,000 m to km", "1,000 m = 1 km"),
])
def test_conversions(q, expected):
    assert answers.convert(q) == expected


@pytest.mark.parametrize("q", ["5 km in kg", "banana in cups", "how to convert", "5 foo to bar"])
def test_conversions_refuse(q):
    assert answers.answer(q) is None


# --- news: the same story, told by others -----------------------------------

def story(title, source, wing, hours=1):
    return news.Story(title, f"https://{source}.example/{abs(hash(title))}", source, wing,
                      when=datetime.now(timezone.utc) - timedelta(hours=hours))


def test_coverage_links_the_same_story_across_wings():
    a = story("Senate passes sweeping border security bill after late night vote", "BBC", "centre")
    b = story("Senate passes border security bill in late night vote", "Fox", "right", 2)
    c = story("Scientists discover new species of deep sea octopus", "Guardian", "left")
    old = story("Senate passes border security bill in late night vote", "NYT", "left", 200)
    out = news.with_coverage([a], [a, b, c, old])
    assert [t.source for t in out[0].also] == ["Fox"]       # not itself, not unrelated, not last week's
    assert a.also == []                                        # the cached story is not touched


def test_top_stories_puts_widely_covered_stories_first_and_lists_each_once():
    a = story("Senate passes sweeping border security bill after late night vote", "BBC", "centre", 5)
    b = story("Senate passes border security bill in late night vote", "Fox", "right", 6)
    c = story("Senate border security bill passes after late night vote", "Guardian", "left", 7)
    newer = story("Scientists discover new species of deep sea octopus", "Vox", "left", 1)
    stale = story("Old news from last week about the harbour", "NPR", "left", 200)
    top = news.top_stories([newer, a, b, c, stale])
    assert [s.source for s in top] == ["BBC", "Vox"]           # the covered story leads, though older
    assert sorted(t.source for t in top[0].also) == ["Fox", "Guardian"]
    assert all(s.source != "NPR" for s in top)                   # nothing from last week
    assert a.also == []                                          # cached stories are not touched


def test_top_stories_caps_lone_stories_per_outlet():
    lone = [story(f"Completely different topic number {i} about {w}", "Same", "left", i + 1)
            for i, w in enumerate(["whales", "volcanoes", "tractors", "violins", "glaciers"])]
    assert len(news.top_stories(lone, per_source=3)) == 3


def test_a_feed_that_fails_keeps_showing_what_we_had(monkeypatch):
    feed = {"name": "X", "url": "https://x.example/rss", "wing": "centre"}
    s = story("Something happened today", "X", "centre")
    news._cache[feed["url"]] = (0, [s])  # old enough to need a refetch

    class Down:
        async def get(self, url):
            raise httpx.ConnectError("down")

    assert asyncio.run(news._one(Down(), feed)) == [s]
    news._cache.clear()
    with pytest.raises(httpx.ConnectError):
        asyncio.run(news._one(Down(), feed))


# --- the app ----------------------------------------------------------------

@pytest.fixture
def client():
    return nook.app.test_client()


def fake_web(results, failed=()):
    async def fake(query, page=1, chosen=None, period=None, **kw):
        return list(results), list(failed)
    return fake


def test_bang_redirects(client):
    r = client.get("/search?q=!gh+flask")
    assert r.status_code == 302 and r.headers["Location"] == "https://github.com/search?q=flask"


def test_instant_answer_shows_above_results(client, monkeypatch):
    monkeypatch.setattr(nook, "ask", fake_web([res("https://a.com", engine="duckduckgo")]))
    html = client.get("/search?q=12*7").get_data(as_text=True)
    assert '<p class="answer">12*7 = 84</p>' in html and "a.com" in html
    assert 'class="answer"' not in client.get("/search?q=cats").get_data(as_text=True)


def test_old_results_when_nobody_answers(client, monkeypatch):
    monkeypatch.setattr(nook, "ask", fake_web([res("https://a.com", engine="duckduckgo")]))
    client.get("/search?q=cats")
    nook.cache.clear()  # the five-minute memory has run out, the day-long copy has not
    monkeypatch.setattr(nook, "ask", fake_web([], failed=[e.NAME for e in nook.active]))
    html = client.get("/search?q=cats").get_data(as_text=True)
    assert "a.com" in html and "nobody is answering right now" in html and "answered by" not in html
    assert "nobody answered just now" not in html


def test_no_old_results_for_a_search_never_seen(client, monkeypatch):
    monkeypatch.setattr(nook, "ask", fake_web([], failed=[e.NAME for e in nook.active]))
    assert "nobody answered just now" in client.get("/search?q=never+seen").get_data(as_text=True)


def test_news_shows_how_others_told_it(client, monkeypatch):
    a = story("Senate passes sweeping border security bill after late night vote", "BBC", "centre")
    b = story("Senate passes border security bill in late night vote", "Fox", "right", 2)

    async def fake(selected):
        return [[a], [b]], []

    monkeypatch.setattr(nook, "ask_news", fake)
    html = client.get("/news?w=centre").get_data(as_text=True)
    assert "also told by" in html and "Fox" in html and "(right)" in html
    assert html.count("Senate passes") == 1  # the right-wing telling is not listed on its own here


def test_wikipedia_stays_off_without_a_contact():
    from engines import wikipedia
    assert wikipedia not in nook.active


def test_secret_is_made_once_and_kept(tmp_path, monkeypatch):
    monkeypatch.setattr(nook, "ROOT", tmp_path)
    monkeypatch.setitem(nook.config, "secret", "")
    first = nook.load_secret()
    assert len(first) >= 32 and (tmp_path / ".secret").read_text() == first
    assert nook.load_secret() == first
    monkeypatch.setitem(nook.config, "secret", "from-config")
    assert nook.load_secret() == "from-config"


# --- compare ------------------------------------------------------------------

def test_compare_lays_a_story_out_by_wing(client, monkeypatch):
    import proxy
    a = story("Senate passes sweeping border security bill after late night vote", "BBC", "centre")
    b = story("Senate passes border security bill in late night vote", "Fox", "right", 2)
    c = story("Senate border security bill passes after late night vote", "Guardian", "left", 3)
    other = story("Scientists discover new species of deep sea octopus", "Vox", "left")
    news._cache.clear()
    news._cache["feed"] = (0, [a, b, c, other])
    html = client.get(proxy.compare_link(a.url, "all")).get_data(as_text=True)
    assert html.count('class="cmp-wing"') == 3                       # left, centre, right
    assert html.index(">left<") < html.index(">centre<") < html.index(">right<")
    assert "octopus" not in html
    assert "far left, far right" in html                             # and says who did not run it
    assert "3 outlets" in html
    assert 'href="/read?u=' in html                                   # each opens in the reader
    news._cache.clear()


def test_compare_needs_a_signature_and_a_story_we_still_hold(client):
    import proxy
    assert client.get("/compare?u=https://x.example/a").status_code == 403
    assert client.get(proxy.compare_link("https://x.example/gone")).status_code == 404
    news._cache.clear()


def test_news_links_to_compare_only_for_stories_with_company(client, monkeypatch):
    a = story("Senate passes sweeping border security bill after late night vote", "BBC", "centre")
    b = story("Senate passes border security bill in late night vote", "Fox", "right", 2)
    lone = story("Scientists discover new species of deep sea octopus", "BBC", "centre", 3)

    async def fake(selected):
        return [[a, lone], [b]], []

    monkeypatch.setattr(nook, "ask_news", fake)
    html = client.get("/news?w=centre").get_data(as_text=True)
    assert html.count('class="cmp"') == 1 and "/compare?u=" in html
    news._cache.clear()
