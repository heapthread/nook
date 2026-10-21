from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import app as nook
import news
import proxy

FIX = Path(__file__).parent / "fixtures"


def story(title, source, hours_ago, wing="centre"):
    return news.Story(title, f"https://x.com/{title}", source, wing,
                      when=datetime.now(timezone.utc) - timedelta(hours=hours_ago))


# --- news ---------------------------------------------------------------

def test_parse_rss_with_media_images():
    stories = news.parse((FIX / "feed_bbc.xml").read_bytes(), "BBC News", "centre")
    assert len(stories) > 10
    assert all(s.title and s.url.startswith("http") and s.when for s in stories)
    assert any(s.image.startswith("http") for s in stories)
    assert all("<" not in s.summary for s in stories)


def test_parse_rdf_feed():
    stories = news.parse((FIX / "feed_dw.xml").read_bytes(), "DW", "centre")
    assert len(stories) > 10 and all(s.url.startswith("http") for s in stories)


def test_mix_caps_each_outlet_and_sorts_newest_first():
    a = [story(f"a{i}", "A", i) for i in range(1, 6)]
    b = [story("b1", "B", 0.5)]
    picked = news.mix([a, b], per_source=2, total=10)
    assert [s.title for s in picked] == ["b1", "a1", "a2"]


def test_ago():
    now = datetime.now(timezone.utc)
    assert news.ago(now - timedelta(minutes=5)) == "5m ago"
    assert news.ago(now - timedelta(hours=3)) == "3h ago"
    assert news.ago(now - timedelta(days=2)) == "2d ago"
    assert news.ago(None) == ""


def test_feeds_file_is_valid():
    feeds = news.load_feeds(nook.ROOT / "feeds.toml")
    for wing in news.WINGS:
        assert sum(f["wing"] == wing for f in feeds) >= 3, wing


@pytest.fixture
def client():
    nook.cache.clear()
    nook.hits.clear()
    return nook.app.test_client()


def test_news_page_wings_and_pictures(client, monkeypatch):
    s = story("headline", "BBC", 1)
    s.image = "https://img.example/a.jpg"

    async def fake(selected):
        return [[s]], []

    monkeypatch.setattr(nook, "ask_news", fake)
    html = client.get("/news?w=centre&p=0").get_data(as_text=True)
    assert "headline" in html and 'class="pic"' not in html
    html = client.get("/news?w=centre&p=1").get_data(as_text=True)
    assert 'class="pic"' in html and "/img?u=" in html and "img.example" not in html.split("/img?u=")[0]
    assert "https%3A%2F%2Fimg.example%2Fa.jpg" in html
    # the choice is remembered
    r = client.get("/news?w=centre&p=1")
    assert "nook_news=centre|1" in r.headers["Set-Cookie"]
    assert client.get("/news").get_data(as_text=True).count('class="pic"') == 1


def test_home_links_to_news(client):
    assert 'href="/news"' in client.get("/").get_data(as_text=True)


# --- privacy ------------------------------------------------------------

def test_every_page_carries_privacy_headers(client):
    r = client.get("/")
    assert r.headers["Referrer-Policy"] == "no-referrer"
    assert "img-src 'self'" in r.headers["Content-Security-Policy"]


def test_img_refuses_unsigned_and_forged(client):
    assert client.get("/img?u=https://example.com/a.png").status_code == 403
    assert client.get("/img?u=https://example.com/a.png&s=" + "0" * 32).status_code == 403
    good = proxy.link("https://example.com/a.png")
    assert client.get(good.replace("a.png", "b.png")).status_code == 403


@pytest.mark.parametrize("url", ["http://127.0.0.1/a.png", "http://localhost/a.png",
                                 "http://192.168.1.1/a.png", "http://[::1]/a.png",
                                 "http://169.254.169.254/latest", "file:///c:/windows/win.ini",
                                 "ftp://example.com/a.png"])
def test_img_refuses_private_addresses_even_when_signed(client, url):
    assert client.get(proxy.link(url)).status_code == 502


def test_img_passes_on_pictures_only(client, monkeypatch):
    monkeypatch.setattr(proxy, "fetch", lambda url: (b"\x89PNG", "image/png"))
    r = client.get(proxy.link("https://example.com/a.png"))
    assert r.status_code == 200 and r.mimetype == "image/png"
    assert "max-age" in r.headers["Cache-Control"]


def test_pages_never_point_the_browser_at_third_parties(client, monkeypatch):
    from engines import bing_images, duckduckgo_videos
    images = bing_images.parse((FIX / "bing_images.html").read_text(encoding="utf-8"))
    videos = duckduckgo_videos.parse((FIX / "ddg_videos.json").read_text(encoding="utf-8"))

    async def fake(engine, query, page=1, **kw):
        return (images if engine is bing_images else videos), []

    monkeypatch.setattr(nook, "ask_media", fake)
    import re
    for tab in ("images", "videos"):
        html = client.get(f"/search?q=x&t={tab}").get_data(as_text=True)
        srcs = re.findall(r'<img[^>]+src="([^"]+)"', html)
        assert srcs and all(s.startswith("/img?") for s in srcs), tab
    html = client.get("/watch", query_string={"v": "https://www.youtube.com/watch?v=jNQXAC9IVRw"}).get_data(as_text=True)
    assert '<img class="poster" src="/img?' in html
    assert "youtube.com/iframe_api" not in html  # only loaded by player.js after a click
