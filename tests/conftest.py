import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    """Tests never reach a search engine, dictionary or knowledge site unless they say so.

    A test that wants results patches nook.ask / nook.ask_media / nook.ask_card itself."""
    import app as nook

    async def no_results(query, page=1, chosen=None, period=None, **kw):
        return [], []

    async def no_media(engine, query, page=1, **kw):
        return [], []

    async def no_card(query, picked):
        return None

    async def no_news(selected):
        return [], []

    async def no_related(query, picked):
        return []

    monkeypatch.setattr(nook, "ask_related", no_related)
    monkeypatch.setattr(nook, "ask_news", no_news)
    monkeypatch.setattr(nook, "ask", no_results)
    monkeypatch.setattr(nook, "ask_media", no_media)
    monkeypatch.setattr(nook, "ask_card", no_card)
