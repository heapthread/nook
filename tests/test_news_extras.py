from datetime import datetime, timedelta, timezone

import pytest

import app as nook
import news


@pytest.fixture
def client():
    nook.cache.clear()
    nook.hits.clear()
    news._cache.clear()
    return nook.app.test_client()


def story(title, source, wing, hours=1, summary=""):
    return news.Story(title, f"https://{source.lower()}.example/{abs(hash(title))}", source, wing, summary=summary,
                      when=datetime.now(timezone.utc) - timedelta(hours=hours))


STORIES = [
    story("Senate passes border security bill after late night vote", "BBC", "centre", 2),
    story("Border security bill passes the Senate in late night vote", "Fox", "right", 3),
    story("Scientists discover new species of deep sea octopus", "Vox", "left", 1, "A strange creature found near the border of two ocean currents"),
    story("Markets rally as inflation cools", "Guardian", "left", 5),
]


def serve(monkeypatch):
    async def fake(selected):
        by_source = {}
        for s in STORIES:
            by_source.setdefault(s.source, []).append(s)
        return list(by_source.values()), []
    monkeypatch.setattr(nook, "ask_news", fake)


def test_matching_needs_every_word_and_ignores_case():
    assert [s.source for s in news.matching(STORIES, "senate BORDER")] == ["BBC", "Fox"]          # newest first
    assert [s.source for s in news.matching(STORIES, "border")] == ["Vox", "BBC", "Fox"]            # the summary counts too
    assert news.matching(STORIES, "senate octopus") == [] and news.matching(STORIES, "") == [] and news.matching(STORIES, "a ?") == []


def test_searching_the_news_all_wings(client, monkeypatch):
    serve(monkeypatch)
    html = client.get("/news?w=all&q=senate").get_data(as_text=True)
    assert "Senate passes border" in html or "passes the Senate" in html
    assert "octopus" not in html and "Markets rally" not in html
    assert "match" in html and "&ldquo;senate&rdquo;" in html and "clear" in html
    assert 'value="senate"' in html


def test_searching_inside_one_wing(client, monkeypatch):
    serve(monkeypatch)
    html = client.get("/news?w=left&q=border").get_data(as_text=True)
    assert "octopus" in html and "Senate" not in html.split("<article")[1] and "Markets" not in html


def test_nothing_matching_says_so(client, monkeypatch):
    serve(monkeypatch)
    html = client.get("/news?w=all&q=zeppelin").get_data(as_text=True)
    assert "nothing in the feeds mentions that." in html and "0 matches" in html


def test_the_search_survives_switching_wing_and_pictures(client, monkeypatch):
    serve(monkeypatch)
    html = client.get("/news?w=left&q=border").get_data(as_text=True)
    assert "q=border" in html.split('class="tabs"')[1].split("</nav>")[0]                    # wing tabs keep the search
    assert "p=1&amp;q=border" in html                                                         # and so does the pictures toggle
    assert 'name="w" value="left"' in html


def test_no_search_means_the_normal_page(client, monkeypatch):
    serve(monkeypatch)
    html = client.get("/news?w=all").get_data(as_text=True)
    assert "match" not in html.split("</nav>")[1].split("<article")[0] and "octopus" in html


def test_stories_carry_their_time_for_the_new_marker(client, monkeypatch):
    serve(monkeypatch)
    html = client.get("/news?w=all").get_data(as_text=True)
    assert 'data-when="20' in html and 'class="note newcount" hidden' in html
    assert html.index("</article>") < html.index("news.js")                                   # the script comes after the stories
    assert 'data-when' not in client.get("/news?w=all&q=zeppelin").get_data(as_text=True)


def test_a_search_with_html_is_just_text(client, monkeypatch):
    serve(monkeypatch)
    html = client.get('/news?w=all&q=<script>alert(1)</script>').get_data(as_text=True)
    assert "<script>alert(1)</script>" not in html and "&lt;script&gt;" in html
