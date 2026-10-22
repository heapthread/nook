from datetime import date

import pytest

import app as nook
import cards
import dates
import figures
import me
import texttools
from engines import Result


@pytest.fixture
def client(monkeypatch):
    nook.cache.clear()
    nook.hits.clear()
    nook.spelling.clear()
    return nook.app.test_client()


def page(client, path, **query):
    return client.get(path, query_string=query).get_data(as_text=True) if query else client.get(path).get_data(as_text=True)


def results(*urls):
    return [Result(title=f"title {n}", url=u, snippet="a snippet", engines=["bing"], rank=n) for n, u in enumerate(urls)]


# --- the page appears before the results do --------------------------------------------

def test_the_top_of_the_page_is_sent_before_the_engines_answer(client, monkeypatch):
    async def ask(query, page=1, chosen=None, period=None, **kw):
        return results("https://a.example/1"), []
    monkeypatch.setattr(nook, "ask", ask)
    chunks = list(client.get("/search", query_string={"q": "flask"}, buffered=False).response)
    first, rest = chunks[0].decode(), b"".join(chunks[1:]).decode()
    assert 'name="q" value="flask"' in first and 'class="loading"' in first and "title 0" not in first
    assert 'class="loaded"' in rest and "title 0" in rest and "<html" not in rest
    assert (first + rest).count("<title>") == 1


def test_a_remembered_search_is_one_piece(client, monkeypatch):
    async def ask(query, page=1, chosen=None, period=None, **kw):
        return results("https://a.example/1"), []
    monkeypatch.setattr(nook, "ask", ask)
    client.get("/search", query_string={"q": "flask"})
    chunks = list(client.get("/search", query_string={"q": "flask"}, buffered=False).response)
    assert len(chunks) == 1 and 'class="loading"' not in chunks[0].decode()


def test_a_failure_while_streaming_ends_the_page_politely(client, monkeypatch):
    async def ask(query, page=1, chosen=None, period=None, **kw):
        raise RuntimeError("boom")
    monkeypatch.setattr(nook, "ask", ask)
    html = page(client, "/search", q="flask")
    assert "something went wrong" in html and html.rstrip().endswith("</html>")


def test_loading_line_goes_away_by_itself():
    css = open(nook.ROOT / "static" / "style.css", encoding="utf-8").read()
    assert ".loading:has(~ .loaded)" in css


# --- results that say a little more ---------------------------------------------------------

def test_addresses_become_trails_and_odd_results_get_a_label():
    assert nook.crumbs("https://www.example.com/a/b%20c/d/e/f") == "example.com › a › b c › d"
    assert nook.kind_of("https://x.example/report.PDF") == "pdf"
    assert nook.kind_of("https://www.youtube.com/watch?v=abcdefghijk") == "video"
    assert nook.kind_of("https://old.reddit.com/r/x") == "forum" and nook.kind_of("https://x.example/") is None
    assert nook.youtube_id("https://youtu.be/abcdefghijk") == "abcdefghijk" and nook.youtube_id("https://x.example/") == ""


def test_the_results_show_trails_badges_and_video_thumbnails(client, monkeypatch):
    async def ask(query, page=1, chosen=None, period=None, **kw):
        return results("https://en.wikipedia.org/wiki/Bonn", "https://x.example/a.pdf", "https://www.youtube.com/watch?v=abcdefghijk"), []
    monkeypatch.setattr(nook, "ask", ask)
    html = page(client, "/search", q="bonn")
    assert "en.wikipedia.org › wiki › Bonn" in html and '<span class="badge">pdf</span>' in html
    assert 'class="thumb"' in html and "i.ytimg.com" not in html.replace("%2F", "/").split('class="thumb"')[0]
    nook.cache.clear()
    client.set_cookie("nook_pics", "off")
    assert 'class="thumb"' not in page(client, "/search", q="bonn")


def test_news_and_maps_are_one_click_from_a_search(client):
    html = page(client, "/search", q="bonn")
    nav = html.split('class="tabs"')[1].split("</nav>")[0]
    assert "/news?w=all&amp;q=bonn" in nav and "/maps?q=bonn" in nav


def test_an_empty_search_offers_other_places(client):
    html = page(client, "/search", q="zzzzqqqq")
    assert "ask somewhere else" in html and "%21brave%20zzzzqqqq" in html


def test_several_failures_link_to_the_status_page(client, monkeypatch):
    async def ask(query, page=1, chosen=None, period=None, **kw):
        return results("https://a.example/1"), ["yahoo", "seznam"]
    monkeypatch.setattr(nook, "ask", ask)
    assert 'href="/status"' in page(client, "/search", q="x")


def test_how_long_it_took_is_shown_for_a_fresh_search_only(client, monkeypatch):
    async def ask(query, page=1, chosen=None, period=None, **kw):
        return results("https://a.example/1"), []
    monkeypatch.setattr(nook, "ask", ask)
    assert 'class="soft took"' in page(client, "/search", q="x")
    assert 'class="soft took"' not in page(client, "/search", q="x")      # remembered: no waiting to report


# --- favour a site, open in new tabs, the quiet menu -------------------------------------------

def test_a_site_is_hidden_or_favoured_never_both(client):
    r = client.post("/sites", data={"site": "example.com"})
    assert "nook_hide=example.com" in " ".join(r.headers.getlist("Set-Cookie"))
    r = client.post("/sites", data={"site": "example.com", "kind": "prefer"})
    cookies = " ".join(r.headers.getlist("Set-Cookie"))
    assert "nook_prefer=example.com" in cookies and "nook_hide=;" in cookies
    assert client.post("/sites", data={"site": "example.com", "kind": "bogus"}).status_code == 400
    assert client.post("/sites", data={"site": "not a site", "kind": "prefer"}).status_code == 400


def test_open_in_a_new_tab_is_a_cookie(client):
    assert 'data-newtab="0"' in page(client, "/")
    assert "nook_tab=new" in " ".join(client.post("/engines", data={"newtab": "new", "next": "/"}).headers.getlist("Set-Cookie"))
    assert 'data-newtab="1"' in page(client, "/") and "open results" in page(client, "/")


def test_the_menu_script_is_on_every_page_and_hides_the_extras(client):
    assert "menu.js" in page(client, "/search", q="x")
    js = open(nook.ROOT / "static" / "menu.js", encoding="utf-8").read()
    for word in ("more from", "favour site", "archive", "copy link", "kind=prefer", "web.archive.org"):
        assert word in js


# --- the little cards ------------------------------------------------------------------------

def test_a_calendar():
    card = dates.answer("calendar october 2026", today=date(2026, 10, 22))
    assert card["kind"] == "calendar" and card["title"] == "october 2026" and card["today"] == 22
    assert card["rows"][0]["days"] == [0, 0, 0, 1, 2, 3, 4] and card["rows"][0]["week"] == 40 and len(card["rows"]) == 5
    assert dates.answer("calendar next month", today=date(2026, 12, 5))["title"] == "january 2027"
    assert dates.answer("march 2027 calendar", today=date(2026, 12, 5))["today"] is None
    assert dates.answer("calendar 2028 february", today=date(2026, 1, 1))["rows"][-1]["days"][1] == 29
    assert dates.answer("calendar of doom", today=date(2026, 1, 1)) is None


def test_stopwatch_and_pomodoro():
    assert cards.local("stopwatch") == {"kind": "stopwatch"}
    assert cards.local("pomodoro") == {"kind": "timer", "seconds": 1500}


@pytest.mark.parametrize("query, expected", [
    ("word count the quick brown fox", "4 words"), ("character count hello", "5 characters"),
    ("uppercase hello world", "HELLO WORLD"), ("title case hello world", "Hello World"),
    ("reverse stressed", "desserts"), ("slugify Héllo, Wörld!", "hello-world"),
])
def test_text_tools(query, expected):
    card = texttools.answer(query)
    assert expected in (card["value"] if card["kind"] == "tool" else card["big"])


def test_choosing_for_you():
    for _ in range(20):
        card = texttools.answer("choose between pizza, pasta or soup")
        assert card["big"] in ("pizza", "pasta", "soup") and card["small"] == "picked from pizza, pasta, soup"
    assert texttools.answer("should i stay or go")["big"] in ("stay", "go")
    assert texttools.answer("choose pizza") is None and texttools.answer("hello") is None


@pytest.mark.parametrize("query, big", [("roman numerals 2026", "MMXXVI"), ("1994 in roman", "MCMXCIV"), ("xiv in decimal", "14"),
                                        ("mcmxcix to number", "1999"), ("roman 4", "IV")])
def test_roman_numerals(query, big):
    assert figures.answer(query)["big"] == big


@pytest.mark.parametrize("query", ["roman numerals 4000", "iiii in decimal", "mim in decimal", "roman numerals 0", "civil in decimal"])
def test_only_proper_roman_numerals(query):
    assert figures.answer(query) is None


def test_things_about_you():
    assert me.answer("my ip", "203.0.113.9", "UA")["big"] == "203.0.113.9"
    assert "your own computer" in me.answer("what is my ip", "127.0.0.1", "UA")["small"]
    assert me.answer("my user agent", "1.1.1.1", "Mozilla/5.0 test")["value"] == "Mozilla/5.0 test"
    assert me.answer("my ip", "", "UA") is None and me.answer("hello", "1.1.1.1", "UA") is None


def test_the_search_answers_my_ip(client):
    html = page(client, "/search", q="my ip")
    assert "127.0.0.1" in html and 'class="card small"' in html


def test_new_cards_have_templates(client, monkeypatch):
    for card in (dates.answer("calendar", today=date(2026, 10, 22)), {"kind": "stopwatch"}):
        async def fake(query, picked, card=card):
            return card
        monkeypatch.setattr(nook, "ask_card", fake)
        nook.cache.clear()
        html = page(client, "/search", q="x " + card["kind"])
        assert f'class="card {card["kind"]}' in html or f'class="card small {card["kind"]}' in html
    assert 'class="today"' in html or "stopwatch" in html


# --- the home page's word, surprise me, and the rest ---------------------------------------------------

def test_the_home_page_can_show_a_word(client, monkeypatch):
    async def learn():
        return {"word": {"word": "serendipity", "definition": "luck", "url": "u"}, "article": None, "day": None}
    monkeypatch.setattr(nook, "ask_learn", learn)
    assert client.get("/daily.json").get_json()["word"] == "serendipity"
    html = page(client, "/")
    assert 'name="daily"' in html and 'class="daily"' in html
    assert "daily.json" in open(nook.ROOT / "static" / "home.js", encoding="utf-8").read()


def test_surprise_me(client, monkeypatch):
    async def title():
        return "Édith Piaf"
    monkeypatch.setattr(nook, "ask_random", title)
    r = client.get("/surprise")
    assert r.status_code == 302 and r.headers["Location"] == "/search?q=%C3%89dith%20Piaf"

    async def nothing():
        return None
    monkeypatch.setattr(nook, "ask_random", nothing)
    assert client.get("/surprise").headers["Location"] == "/"


def test_recent_searches_appear_when_the_empty_box_is_clicked():
    js = open(nook.ROOT / "static" / "suggest.js", encoding="utf-8").read()
    assert '"focus"' in js and "nook.recent" in js and ".recent" in js


def test_a_way_past_the_header_and_other_kindnesses(client):
    html = page(client, "/")
    assert 'class="skip" href="#main"' in html and 'id="main"' in html
    css = open(nook.ROOT / "static" / "style.css", encoding="utf-8").read()
    assert "prefers-reduced-motion" in css and "focus-visible" in css and "@media print" in css


def test_the_reader_shows_progress_and_answers_can_be_copied():
    assert "progress" in open(nook.ROOT / "static" / "reader.js", encoding="utf-8").read()
    assert "copyans" in open(nook.ROOT / "static" / "extras.js", encoding="utf-8").read()
    assert "stopwatch" in open(nook.ROOT / "static" / "card.js", encoding="utf-8").read()


def test_the_footer_is_small(client):
    footer = page(client, "/about").split("<footer>")[1]
    assert footer.count("<a ") == 3 and "nothing is logged" in footer


def test_a_host_without_a_disk_can_set_the_secret_and_contact_in_the_environment(monkeypatch):
    monkeypatch.setenv("NOOK_SECRET", "from-the-environment")
    assert nook.load_secret() == "from-the-environment"
