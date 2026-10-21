import asyncio
import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

import app as nook
import cards
import dates
import weather

FIX = Path(__file__).parent / "fixtures"
TODAY = date(2026, 10, 21)   # a Wednesday


def read(name):
    return (FIX / name).read_text(encoding="utf-8")


def ask(q):
    return dates.answer(q, TODAY, datetime(2026, 10, 21, 12, tzinfo=timezone.utc))


@pytest.fixture
def client():
    nook.cache.clear()
    nook.hits.clear()
    return nook.app.test_client()


# --- dates ----------------------------------------------------------------------

def test_easter_is_right():
    assert dates.easter(2026) == date(2026, 4, 5) and dates.easter(2027) == date(2027, 3, 28)
    assert dates.easter(2024) == date(2024, 3, 31) and dates.easter(2000) == date(2000, 4, 23)


@pytest.mark.parametrize("text, expected", [
    ("2027-03-01", date(2027, 3, 1)), ("1 march 2027", date(2027, 3, 1)), ("march 1, 2027", date(2027, 3, 1)),
    ("1st of march 2027", date(2027, 3, 1)), ("christmas", date(2026, 12, 25)), ("halloween", date(2026, 10, 31)),
    ("new years eve", date(2026, 12, 31)), ("thanksgiving", date(2026, 11, 26)), ("tomorrow", date(2026, 10, 22)),
    ("friday", date(2026, 10, 23)), ("next wednesday", date(2026, 10, 28)), ("1 january", date(2027, 1, 1)),
    ("21 october", date(2026, 10, 21)), ("valentine's day", date(2027, 2, 14)),
])
def test_dates_are_understood(text, expected):
    assert dates.parse_date(text, TODAY) == expected


@pytest.mark.parametrize("text", ["nonsense", "31 february 2027", "2027-13-01", "", "march"])
def test_things_that_are_not_dates(text):
    assert dates.parse_date(text, TODAY) is None


def test_days_until():
    card = ask("days until christmas")
    assert card["big"] == "65 days" and "friday 25 december 2026" in card["small"] and "9 weeks 2 days" in card["small"]
    assert ask("how many days until 2027-03-01")["big"] == "131 days"
    assert ask("countdown to halloween")["big"] == "10 days"
    assert ask("days until easter")["small"].count("sunday 28 march 2027") == 1
    since = ask("days since 2026-10-01")
    assert since["big"] == "20 days" and since["small"].startswith("since 2026-10-01")
    assert ask("days until today")["big"] == "today"
    assert ask("days until nonsense") is None and ask("how many days") is None


def test_adding_and_subtracting():
    assert ask("45 days from now")["big"] == "saturday 5 december 2026"
    assert ask("in 3 weeks")["big"] == "wednesday 11 november 2026"
    assert ask("10 days ago")["big"] == "sunday 11 october 2026"
    assert ask("3 months from now")["big"] == "thursday 21 january 2027"
    assert ask("100 days from 2026-12-25")["big"] == "sunday 4 april 2027"
    assert dates._add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)             # no 31st of february
    assert ask("999999999 days from now") is None


def test_what_day():
    assert ask("what day is 1 march 2027")["big"] == "monday"
    assert ask("what day was 2000-01-01")["big"] == "saturday"
    assert ask("what day is christmas")["big"] == "friday"


def test_age():
    card = ask("how old is someone born 12 may 1990")
    assert card["big"] == "36 years old" and "36 years 5 months 9 days" in card["small"] and "next birthday in 203 days" in card["small"]
    assert "birthday today" in ask("age 1985-10-21")["small"]
    assert ask("born 2030-01-01") is None                                           # not born yet


def test_between_dates():
    card = ask("days between 2026-01-01 and 2026-12-25")
    assert card["big"] == "358 days" and "51 weeks 1 day" in card["small"]


def test_today_week_and_moon():
    assert ask("what is todays date") == {"kind": "fact", "big": "wednesday 21 october 2026", "small": "week 43 · day 294 of 365"}
    assert ask("week number")["big"] == "week 43"
    moon = ask("moon phase")
    assert moon["big"] == "waxing gibbous" and "next full moon" in moon["small"]
    new = dates.moon(datetime(2000, 1, 6, 18, 14, tzinfo=timezone.utc))
    assert new["big"] == "new moon" and new["small"].startswith("0% lit")
    full = dates.moon(datetime(2000, 1, 21, 4, 40, tzinfo=timezone.utc))
    assert full["big"] == "full moon" and full["small"].startswith("100% lit")


@pytest.mark.parametrize("q", ["python tutorial", "hello", "days", "age", "what time is it in tokyo", "5 km in miles"])
def test_other_queries_are_left_alone(q):
    assert ask(q) is None


def test_dates_card_in_the_page(client):
    html = client.get("/search?q=days+until+christmas").get_data(as_text=True)
    assert 'class="card small"' in html and "until christmas" in html


# --- weather ----------------------------------------------------------------------

@pytest.mark.parametrize("q, place", [
    ("weather in bonn", "bonn"), ("bonn weather", "bonn"), ("weather bonn", "bonn"), ("forecast for oslo", "oslo"),
    ("what's the weather in new york", "new york"), ("sunrise in lagos", "lagos"), ("lagos sunset", "lagos"),
    ("temperature in cairo", "cairo"),
])
def test_weather_questions(q, place):
    assert weather.place_in(q) == place


@pytest.mark.parametrize("q", ["weather", "how is the weather", "what is the weather like today", "python weather api",
                               "weather in", "will it rain tomorrow", "weather forecast tomorrow", ""])
def test_not_weather_questions_worth_a_lookup(q):
    assert weather.place_in(q) is None


def test_forecast_card():
    card = weather.parse_forecast(json.loads(read("open_meteo_forecast.json")), "bonn, germany")
    assert card["kind"] == "weather" and card["place"] == "bonn, germany"
    assert card["temp"] == "12°C" and card["temp_f"] == "53°F" and card["text"] == "overcast"
    assert card["feels"] == "9°" and card["wind"] == "13 km/h" and card["humidity"] == "80%"
    assert [d["day"] for d in card["days"]][0] == "today" and len(card["days"]) == 5
    assert all("°" in d["low"] and "°" in d["high"] for d in card["days"])
    assert card["sunrise"] and card["sunset"] and card["credit"] == "weather: open-meteo.com"
    assert weather.parse_forecast({}, "x") is None


class FakeOpenMeteo:
    def __init__(self, fail=False):
        self.calls, self.fail = [], fail

    async def get(self, url, params=None, **kw):
        self.calls.append(url)
        if self.fail:
            raise RuntimeError("down")
        text = read("open_meteo_bonn.json") if "geocoding" in url else read("open_meteo_forecast.json")

        class Reply:
            def raise_for_status(self): pass
            def json(self): return json.loads(text)
        return Reply()


def test_weather_lookup_and_memory():
    weather._cache.clear()
    client = FakeOpenMeteo()
    card = asyncio.run(weather.lookup(client, "bonn"))
    assert card["place"] == "bonn, germany" and len(client.calls) == 2
    asyncio.run(weather.lookup(client, "bonn"))
    assert len(client.calls) == 2                                                    # remembered for a while
    assert asyncio.run(weather.lookup(FakeOpenMeteo(fail=True), "oslo")) is None     # a service that is down: no card
    assert asyncio.run(weather.lookup(FakeOpenMeteo(), "zzzz")) is None                # a name the service did not match


def test_the_card_in_the_page(client, monkeypatch):
    weather._cache.clear()

    async def real(query, picked):
        return await cards.lookup(FakeOpenMeteo(), query)

    monkeypatch.setattr(nook, "ask_card", real)
    html = client.get("/search?q=weather+in+bonn").get_data(as_text=True)
    assert 'class="card weather"' in html and "bonn, germany" in html and "overcast" in html
    assert "sunrise" in html and "weather: open-meteo.com" in html and "today" in html
