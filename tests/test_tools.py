import asyncio
import json
import re
from datetime import datetime, timezone

import pytest

import app as nook
import cards
import devtools
import wordtools


@pytest.fixture
def client():
    nook.cache.clear()
    nook.hits.clear()
    return nook.app.test_client()


# --- developer tools ------------------------------------------------------------

def test_uuid_and_passwords_are_random_and_well_formed():
    a, b = devtools.answer("uuid"), devtools.answer("uuid")
    assert re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}", a["value"]) and a["value"] != b["value"]
    for q, size in [("password", 20), ("random password 12", 12), ("generate password 64", 64), ("32 character password", 32)]:
        card = devtools.answer(q)
        assert len(card["value"]) == size and card["again"], q
        assert any(c.islower() for c in card["value"]) and any(c.isupper() for c in card["value"])
        assert any(c.isdigit() for c in card["value"]) and any(not c.isalnum() for c in card["value"])
    assert devtools.answer("password 3") is None and devtools.answer("password 500") is None


def test_hashes_match_the_real_ones():
    assert devtools.answer("sha256 of hello")["value"] == "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
    assert devtools.answer("md5 of hello")["value"] == "5d41402abc4b2a76b9719d911017c592"
    assert devtools.answer("SHA1 of Hello")["value"] == "f7ff9e8b7bb2e09b70935a5d785e0cc5d9d0abf0"   # case of the text is kept
    assert devtools.answer("hash sha512 x")["value"].startswith("a4abd4448c49562d")
    assert devtools.answer('sha256 "hello"')["value"].startswith("2cf24dba")
    assert devtools.answer("sha256") is None and devtools.answer("md5 hello") is None


def test_base64_and_urls():
    assert devtools.answer("base64 encode hello")["value"] == "aGVsbG8="
    assert devtools.answer("base64 decode aGVsbG8=")["value"] == "hello"
    assert devtools.answer("base64 decode aGVsbG8")["value"] == "hello"        # missing padding is fine
    assert devtools.answer("base64 decode ###") is None and devtools.answer("b64 decode /w==") is None   # not text
    assert devtools.answer("url encode a b&c")["value"] == "a%20b%26c"
    assert devtools.answer("url decode a%20b%26c")["value"] == "a b&c"


def test_colours():
    for q in ["#ff8800", "#f80", "rgb(255, 136, 0)", "rgb 255 136 0", "hsl(32, 100%, 50%)", "color #FF8800 to rgb"]:
        card = devtools.answer(q)
        assert card["kind"] == "colour" and card["hex"] == "#ff8800" and card["rgb"] == "rgb(255, 136, 0)", q
        assert card["hsl"] == "hsl(32, 100%, 50%)", q
    assert devtools.answer("#000")["hsl"] == "hsl(0, 0%, 0%)" and devtools.answer("#ffffff")["hsl"] == "hsl(0, 0%, 100%)"
    assert devtools.answer("rgb(300, 0, 0)") is None and devtools.answer("#ff88") is None and devtools.answer("hsl(400, 10%, 10%)") is None


def test_unix_time():
    assert devtools.answer("epoch 1700000000")["value"] == "tuesday 14 november 2023, 22:13:20 utc"
    assert devtools.answer("unix timestamp 1700000000000")["note"] == "in milliseconds"
    now = datetime(2026, 10, 21, 12, tzinfo=timezone.utc)
    assert devtools.answer("unix time", now)["value"] == str(int(now.timestamp()))
    assert devtools.answer("2026-10-21 to epoch")["value"] == "1792540800"
    assert devtools.answer("2026-02-30 to epoch") is None


def test_lorem_ipsum():
    assert len(devtools.answer("lorem ipsum 3 paragraphs")["value"].split("\n\n")) == 3
    assert len(devtools.answer("lorem 12 words")["value"].rstrip(".").split()) == 12
    assert devtools.answer("lorem ipsum 2 sentences")["value"].count(".") == 2
    assert devtools.answer("lorem") and devtools.answer("lorem 99 paragraphs") is None


@pytest.mark.parametrize("q", ["python uuid library", "how to hash passwords", "sha256 hashing", "md5 collision", "sha1 vs sha256", "hello", "the color red", "epoch games"])
def test_ordinary_searches_are_left_alone(q):
    assert devtools.answer(q) is None


def test_tools_in_the_page(client):
    html = client.get("/search?q=sha256+of+hello").get_data(as_text=True)
    assert 'class="card tool"' in html and "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824" in html
    assert 'data-copy="tool-value"' in html
    one, two = (client.get("/search?q=uuid").get_data(as_text=True).split('id="tool-value">')[1].split("<")[0] for _ in range(2))
    assert one != two                                                   # fresh every time, never remembered
    html = client.get("/search?q=%23ff8800").get_data(as_text=True)
    assert 'class="card colour"' in html and 'fill="#ff8800"' in html and "rgb(255, 136, 0)" in html


def test_a_colour_cannot_inject_markup():
    assert devtools.answer('#ff8800"><script>') is None and devtools.answer("rgb(1,2,3)<b>") is None


# --- word tools ------------------------------------------------------------------

@pytest.mark.parametrize("q, param, word", [
    ("rhymes with orange", "rel_rhy", "orange"), ("what rhymes with love", "rel_rhy", "love"), ("love rhymes", "rel_rhy", "love"),
    ("synonyms for happy", "rel_syn", "happy"), ("antonyms of hot", "rel_ant", "hot"), ("opposite of cold", "rel_ant", "cold"),
    ("words that end in tion", "sp_suffix", "tion"), ("words starting with pre", "sp_prefix", "pre"),
    ("words that contain zz", "sp_inside", "zz"), ("adjectives to describe rain", "rel_jjb", "rain"),
])
def test_word_questions(q, param, word):
    assert wordtools.parse(q)[:2] == (param, word)


@pytest.mark.parametrize("q", ["hello", "rhymes", "words", "synonyms", "how to rhyme", "words with friends"])
def test_not_word_questions(q):
    assert wordtools.parse(q) is None


def test_datamuse_parameters():
    assert wordtools.params_for("sp_suffix", "tion") == {"sp": "*tion"}
    assert wordtools.params_for("sp_prefix", "pre") == {"sp": "pre*"}
    assert wordtools.params_for("sp_inside", "zz") == {"sp": "*zz*"}
    assert wordtools.params_for("rel_rhy", "love") == {"rel_rhy": "love"}


def test_word_lists_are_cleaned():
    raw = json.dumps([{"word": "dove"}, {"word": "above"}, {"word": "love"}, {"word": "dove"}, {"word": "<b>x</b>"}, {"word": "of love"}])
    assert wordtools.parse_words(raw, "love") == ["dove", "above", "of love"]
    assert wordtools.parse_words("nope", "x") == []


class FakeDatamuse:
    def __init__(self, words=("dove", "above", "glove"), fail=False):
        self.calls, self.words, self.fail = [], words, fail

    async def get(self, url, params=None, **kw):
        self.calls.append(params)
        if self.fail:
            raise RuntimeError("down")
        data = json.dumps([{"word": w} for w in self.words])

        class Reply:
            text = data
            def raise_for_status(self): pass
        return Reply()


def test_word_lookup_and_memory():
    wordtools._cache.clear()
    client = FakeDatamuse()
    card = asyncio.run(wordtools.lookup(client, "rhymes with love"))
    assert card["kind"] == "words" and card["title"] == "rhymes with love" and card["words"] == ["dove", "above", "glove"]
    asyncio.run(wordtools.lookup(client, "rhymes with love"))
    assert len(client.calls) == 1
    assert asyncio.run(wordtools.lookup(FakeDatamuse(fail=True), "rhymes with joy")) is None
    assert asyncio.run(wordtools.lookup(FakeDatamuse(words=()), "rhymes with zzzz")) is None


def test_word_card_in_the_page(client, monkeypatch):
    wordtools._cache.clear()

    async def real(query, picked):
        return await cards.lookup(FakeDatamuse(), query)

    monkeypatch.setattr(nook, "ask_card", real)
    html = client.get("/search?q=rhymes+with+love").get_data(as_text=True)
    assert 'class="card words"' in html and "rhymes with love" in html and 'href="/search?q=define+dove"' in html
