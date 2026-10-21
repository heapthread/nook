from pathlib import Path

import pytest

import app as nook
from engines import bing_images, duckduckgo_videos

FIX = Path(__file__).parent / "fixtures"


@pytest.fixture
def client(monkeypatch):
    nook.cache.clear()
    nook.hits.clear()
    return nook.app.test_client()


def test_watch_youtube(client):
    r = client.get("/watch", query_string={"v": "https://www.youtube.com/watch?v=oQrV4j1qA5Q", "title": "a <b>"})
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert 'data-kind="youtube"' in html and 'data-source="oQrV4j1qA5Q"' in html
    assert "<b>" not in html  # titles are escaped


def test_watch_direct_file(client):
    r = client.get("/watch", query_string={"v": "https://example.com/clip.mp4?x=1"})
    assert r.status_code == 200 and 'data-kind="file"' in r.get_data(as_text=True)


@pytest.mark.parametrize("bad", ["", "javascript:alert(1)", "https://example.com/page", "file:///c:/a.mp4"])
def test_watch_refuses_everything_else(client, bad):
    assert client.get("/watch", query_string={"v": bad}).status_code == 404


def test_image_and_video_tabs_render(client, monkeypatch):
    images = bing_images.parse((FIX / "bing_images.html").read_text(encoding="utf-8"))
    videos = duckduckgo_videos.parse((FIX / "ddg_videos.json").read_text(encoding="utf-8"))

    async def fake(engine, query, page=1, **kw):
        return (images if engine is bing_images else videos), []

    monkeypatch.setattr(nook, "ask_media", fake)
    html = client.get("/search?q=red+panda&t=images").get_data(as_text=True)
    assert 'class="grid"' in html and "images.js" in html
    html = client.get("/search?q=red+panda&t=videos").get_data(as_text=True)
    assert 'class="clip"' in html and "/watch?v=" in html
