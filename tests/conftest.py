import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    """Tests never reach a search engine, dictionary or knowledge site unless they say so.

    A test that wants results patches nook.ask / nook.ask_media / nook.ask_card itself."""
    import app as nook
    from flask.testing import FlaskClient

    class Buffered(FlaskClient):
        """The results page streams, so a test must read it all before looking at what the search did."""
        def open(self, *args, **kw):
            kw.setdefault("buffered", True)
            return super().open(*args, **kw)
    monkeypatch.setattr(nook.app, "test_client_class", Buffered)

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

    async def no_suggest(prefix):
        return []

    async def no_suggestion(query):
        return None

    async def no_each(query):
        return []

    async def no_check():
        return []

    async def no_travel(a, b, mode):
        return None, None, [None, None]

    async def no_world():
        return None, None

    async def no_learn():
        return {"word": None, "article": None, "day": None}

    async def no_random():
        return None

    async def no_forecast(place, ll, unit):
        return None

    async def no_money(amount, source):
        return None

    async def no_gap(query, names):
        return None

    async def no_books(query):
        return None

    async def no_work(work_id):
        return None

    monkeypatch.setattr(nook, "ask_forecast", no_forecast)
    monkeypatch.setattr(nook, "ask_money", no_money)
    monkeypatch.setattr(nook, "ask_gap", no_gap)
    monkeypatch.setattr(nook, "ask_books", no_books)
    monkeypatch.setattr(nook, "ask_work", no_work)
    monkeypatch.setattr(nook, "ask_random", no_random)
    monkeypatch.setattr(nook, "get_place", lambda pid: None)
    monkeypatch.setattr(nook, "ask_suggestion", no_suggestion)
    monkeypatch.setattr(nook, "ask_each", no_each)
    monkeypatch.setattr(nook, "ask_check", no_check)
    monkeypatch.setattr(nook, "ask_travel", no_travel)
    monkeypatch.setattr(nook, "ask_world", no_world)
    monkeypatch.setattr(nook, "ask_learn", no_learn)
    monkeypatch.setattr(nook, "ask_suggest", no_suggest)
    monkeypatch.setattr(nook, "ask_related", no_related)
    monkeypatch.setattr(nook, "ask_news", no_news)
    monkeypatch.setattr(nook, "ask", no_results)
    monkeypatch.setattr(nook, "ask_media", no_media)
    monkeypatch.setattr(nook, "ask_card", no_card)
