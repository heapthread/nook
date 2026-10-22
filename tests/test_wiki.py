import asyncio

import pytest

import app as nook
import cards
import wiki


class Reply:
    def __init__(self, data):
        self.data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self.data


def page(title, extract="x" * 120, **extra):
    return {"pageid": 1, "title": title, "extract": extract, "fullurl": f"https://en.wikipedia.org/wiki/{title}", **extra}


class FakeWikipedia:
    """Answers the few Wikipedia / Wikidata calls wiki.find makes, from a small table."""

    def __init__(self, en=None, simple=None, hits=None, claims=None, media=None):
        self.en, self.simple, self.hits = en or {}, simple or {}, hits or []
        self.claims, self.media = claims or {}, media or {}
        self.asked = []

    async def get(self, url, params=None, headers=None):
        self.asked.append((url, dict(params or {})))
        params = params or {}
        if "wikidata" in url:
            return Reply({"claims": self.claims.get((params["entity"], params["property"]), {})})
        if "media-list" in url:
            return Reply(self.media)
        table = self.simple if "simple." in url else self.en
        if params.get("list") == "search":
            return Reply({"query": {"search": self.hits}})
        pages, redirects = [], []
        for title in params["titles"].split("|"):
            real = table.get(title)
            if isinstance(real, str):          # a redirect
                redirects.append({"from": title, "to": real})
                real = table.get(real)
            pages.append(real or {"title": title, "missing": True})
        return Reply({"query": {"redirects": redirects, "pages": pages}})


def run(coro):
    return asyncio.run(coro)


def test_covers_allows_near_words_but_not_missing_ones():
    assert wiki.covers("hotlink", "Inline linking", "Hotlinking")
    assert wiki.covers("alan turing", "Alan Turing")
    assert wiki.covers("münchen", "Munchen")
    assert not wiki.covers("python tutorial", "Python (programming language)", "")
    assert not wiki.covers("", "anything")


def test_language_follows_the_region():
    assert wiki.lang_for("de-de") == "de"
    assert wiki.lang_for("jp-jp") == "ja"
    assert wiki.lang_for("uk-en") == "en"
    assert wiki.lang_for("wt-wt") == "en" and wiki.lang_for(None) == "en"


def test_zoom_comes_from_the_size_of_the_place():
    assert wiki.zoom_for({"dim": "10000"}) == 11
    assert wiki.zoom_for({"dim": "1000000"}) == 5
    assert wiki.zoom_for({"type": "country"}) == 5
    assert wiki.zoom_for({}) == 12


def test_a_redirect_is_followed_and_a_vague_title_is_refused():
    data = {"query": {"redirects": [{"from": "Hotlink", "to": "Inline linking"}],
                      "pages": [page("Inline linking")]}}
    assert wiki.pick_page(data, ["Hotlink"])["title"] == "Inline linking"
    vague = {"query": {"pages": [page("Mercury", pageprops={"disambiguation": ""})]}}
    assert wiki.pick_page(vague, ["Mercury"]) is wiki.VAGUE
    assert wiki.pick_page({"query": {"pages": [{"title": "Nope", "missing": True}]}}, ["Nope"]) is None


def test_photographs_skip_flags_maps_and_icons():
    raw = {"items": [
        {"title": "File:Flag_of_Peru.svg", "type": "image", "showInGallery": True, "srcset": [{"src": "//x/a.png"}]},
        {"title": "File:Lima_street.jpg", "type": "image", "showInGallery": True, "srcset": [{"src": "//upload/b.jpg"}],
         "caption": {"text": "a street"}},
        {"title": "File:Lima_map.png", "type": "image", "showInGallery": True, "srcset": [{"src": "//x/c.png"}]},
        {"title": "File:Lead.jpg", "type": "image", "showInGallery": True, "leadImage": True, "srcset": [{"src": "//x/d.jpg"}]},
    ]}
    shots = wiki.parse_media(raw)
    assert [s["title"] for s in shots] == ["File:Lima_street.jpg"]
    assert shots[0]["src"] == "https://upload/b.jpg" and shots[0]["caption"] == "a street"


def test_hotlink_finds_inline_linking_and_its_simple_english_page():
    en = {"Hotlink": "Inline linking", "Inline linking": page("Inline linking", "Inline linking is the practice of embedding. " * 4)}
    simple = {"Hotlink": {"title": "Hotlink", "missing": True},
              "Hotlinking": page("Hotlinking", "Hotlinking is showing an image from another site. " * 3)}
    client = FakeWikipedia(en=en, simple=simple, hits=[{"title": "Hotlinking", "redirecttitle": "Hotlinking"}])
    card = run(wiki.find(client, "hotlink"))
    assert card["title"] == "Inline linking" and card["kind"] == "wiki"
    assert card["simple"]["title"] == "Hotlinking"


def test_a_place_gets_its_map_and_flag_a_person_does_not():
    claims = {("Q1", "P41"): {"P41": [{"rank": "normal", "mainsnak": {"datavalue": {"value": "Flag of Testland.svg"}}}]}}
    place = page("Testland", "Testland is a country. " * 6, coordinates=[{"lat": 51.0, "lon": 9.0, "type": "country"}],
                 pageprops={"wikibase_item": "Q1"})
    card = run(wiki.find(FakeWikipedia(en={"Testland": place}, claims=claims), "testland"))
    assert card["map"] == {"lat": 51.0, "lon": 9.0, "zoom": 5, "label": "Testland"}
    assert card["flag"].endswith("Flag_of_Testland.svg?width=160")
    person = page("Some Person", "Some Person was a writer. " * 6)
    card = run(wiki.find(FakeWikipedia(en={"Some Person": person}), "some person"))
    assert card["map"] is None and card["flag"] == ""


def test_a_flag_as_the_lead_picture_is_not_shown_twice():
    claims = {("Q1", "P41"): {"P41": [{"rank": "normal", "mainsnak": {"datavalue": {"value": "Flag of Testland.svg"}}}]}}
    place = page("Testland", "Testland is a country. " * 6, pageprops={"wikibase_item": "Q1"},
                 thumbnail={"source": "https://x/500px-Flag_of_Testland.svg.png"})
    card = run(wiki.find(FakeWikipedia(en={"Testland": place}, claims=claims), "testland"))
    assert card["flag"] and card["image"] == ""


def test_nothing_fitting_means_no_card():
    client = FakeWikipedia(hits=[{"title": "Python (programming language)", "redirecttitle": ""}])
    assert run(wiki.find(client, "python tutorial")) is None


def test_the_card_comes_before_duckduckgo_when_wikipedia_has_it(monkeypatch):
    async def fake(client, topic, lang="en"):
        return {"kind": "wiki", "title": "Bonn", "text": "t", "map": None, "flag": "", "image": "", "pictures": [],
                "simple": None, "url": "u", "source": "Wikipedia", "about": ""}
    monkeypatch.setattr(wiki, "lookup", fake)
    card = run(cards.lookup(object(), "bonn", with_knowledge=True))
    assert card["kind"] == "wiki"


@pytest.fixture
def client(monkeypatch):
    nook.cache.clear()
    nook.hits.clear()
    return nook.app.test_client()


WIKI_CARD = {"kind": "wiki", "title": "Bonn", "about": "city", "text": "Bonn is a city.", "url": "https://en.wikipedia.org/wiki/Bonn",
             "source": "Wikipedia", "image": "https://upload.wikimedia.org/a.jpg", "flag": "https://commons.wikimedia.org/f.png",
             "pictures": [{"src": "https://upload.wikimedia.org/b.jpg", "caption": "x", "title": "File:B.jpg", "page": "https://en.wikipedia.org/wiki/File:B.jpg"}],
             "simple": {"title": "Bonn", "text": "Bonn is a town.", "url": "https://simple.wikipedia.org/wiki/Bonn"},
             "map": {"lat": 50.7, "lon": 7.1, "zoom": 11, "label": "Bonn"}, "qid": "Q586"}


def serve_card(monkeypatch):
    async def fake(query, picked):
        return dict(WIKI_CARD)
    monkeypatch.setattr(nook, "ask_card", fake)


def test_the_card_shows_pictures_flag_and_a_map(client, monkeypatch):
    serve_card(monkeypatch)
    html = client.get("/search", query_string={"q": "bonn"}).get_data(as_text=True)
    assert 'class="nmap"' in html and "map.js" in html
    assert html.count('src="/img?u=') >= 3          # lead picture, flag, one more photograph
    assert "in simple words" in html and "Bonn is a town." in html
    assert "bigger map" in html and "/maps?lat=50.7" in html


def test_text_only_leaves_out_pictures_flag_and_map(client, monkeypatch):
    serve_card(monkeypatch)
    client.set_cookie("nook_pics", "off")
    html = client.get("/search", query_string={"q": "bonn"}).get_data(as_text=True)
    assert 'class="nmap"' not in html and "/img?u=" not in html
    assert "see it on a map" in html and "Bonn is a city." in html


def test_pictures_and_suggestions_can_be_switched_off(client):
    r = client.post("/engines", data={"pics": "off", "suggest": "off", "next": "/"})
    cookies = " ".join(r.headers.getlist("Set-Cookie"))
    assert "nook_pics=off" in cookies and "nook_suggest=off" in cookies
    r = client.post("/engines", data={"next": "/"})
    assert "nook_pics=;" in " ".join(r.headers.getlist("Set-Cookie"))


def test_wikipedia_images_use_a_polite_user_agent():
    import proxy
    proxy.CONTACT = "me@example.com"
    assert proxy._headers_for("https://upload.wikimedia.org/x.jpg", {"User-Agent": "Mozilla"})["User-Agent"] == "nook/1.0 (me@example.com)"
    assert proxy._headers_for("https://example.com/x.jpg", {"User-Agent": "Mozilla"})["User-Agent"] == "Mozilla"
    proxy.CONTACT = ""
