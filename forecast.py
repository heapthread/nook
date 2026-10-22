"""The /weather page: a place's weather now, hour by hour for a day, and a week ahead.

Place search and forecast both come from Open-Meteo (free, no key), fetched by nook. Only the place
name, or the position you chose to share for this page, is sent."""
import re
import time
from datetime import date

import weather

GEOCODER = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST = "https://api.open-meteo.com/v1/forecast"
KEEP = 900
_cache = {}


def label(found):
    parts = [found.get("name", ""), found.get("admin1", ""), found.get("country", "")]
    out = []
    for p in parts:
        if p and p not in out:
            out.append(p)
    return ", ".join(out[:3]).lower()


def clean_unit(value):
    return "f" if value == "f" else "c"


def build(data, name, unit="c"):
    """Open-Meteo's answer -> what the page shows. None if it is not usable."""
    cur, daily, hourly = data.get("current") or {}, data.get("daily") or {}, data.get("hourly") or {}
    if "temperature_2m" not in cur or not daily.get("time") or not hourly.get("time"):
        return None
    deg = "°F" if unit == "f" else "°C"
    speed = "mph" if unit == "f" else "km/h"
    mark = str(cur.get("time", ""))[:13]
    start = next((i for i, t in enumerate(hourly["time"]) if t[:13] == mark), 0)
    hours = []
    for i in range(start, min(start + 24, len(hourly["time"]))):
        hours.append({"hour": "now" if i == start else hourly["time"][i][11:16], "temp": f"{round(hourly['temperature_2m'][i])}°",
                      "rain": (hourly.get("precipitation_probability") or [None] * 999)[i],
                      "text": weather.WORDS.get(hourly["weather_code"][i], "")})
    lows, highs = daily["temperature_2m_min"], daily["temperature_2m_max"]
    floor, ceiling = min(lows), max(highs)
    span = (ceiling - floor) or 1
    days = []
    for i, day in enumerate(daily["time"][:7]):
        days.append({
            "day": "today" if i == 0 else date.fromisoformat(day).strftime("%A").lower(),
            "text": weather.WORDS.get(daily["weather_code"][i], ""),
            "low": f"{round(lows[i])}°", "high": f"{round(highs[i])}°",
            "from": round((lows[i] - floor) / span * 100), "to": round((highs[i] - floor) / span * 100),
            "rain": (daily.get("precipitation_probability_max") or [None] * 9)[i],
            "wind": f"{round((daily.get('wind_speed_10m_max') or [0] * 9)[i])} {speed}",
            "uv": round((daily.get("uv_index_max") or [0] * 9)[i]),
        })
    return {
        "place": name, "unit": unit, "temp": f"{round(cur['temperature_2m'])}{deg}",
        "text": weather.WORDS.get(cur.get("weather_code"), ""),
        "feels": f"{round(cur['apparent_temperature'])}°" if "apparent_temperature" in cur else "",
        "wind": f"{round(cur['wind_speed_10m'])} {speed}" if "wind_speed_10m" in cur else "",
        "humidity": f"{round(cur['relative_humidity_2m'])}%" if "relative_humidity_2m" in cur else "",
        "sunrise": (daily.get("sunrise") or [""])[0][-5:], "sunset": (daily.get("sunset") or [""])[0][-5:],
        "hours": hours, "days": days, "uv": days[0]["uv"],
    }


async def lookup(client, place=None, ll=None, unit="c"):
    unit = clean_unit(unit)
    key = (place and place.lower(), ll, unit)
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < KEEP:
        return hit[1]
    try:
        if ll:
            lat, lon, name = ll[0], ll[1], "your location"
        else:
            r = await client.get(GEOCODER, params={"name": place, "count": 5, "language": "en", "format": "json"})
            r.raise_for_status()
            found = weather.best_place(r.json(), place) or next(iter((r.json().get("results") or [])), None)
            if not found:
                return None
            lat, lon, name = found["latitude"], found["longitude"], label(found)
        params = {
            "latitude": lat, "longitude": lon, "timezone": "auto", "forecast_days": 7,
            "current": "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m",
            "hourly": "temperature_2m,precipitation_probability,weather_code",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,sunrise,sunset,precipitation_probability_max,wind_speed_10m_max,uv_index_max",
        }
        if unit == "f":
            params.update(temperature_unit="fahrenheit", wind_speed_unit="mph")
        r = await client.get(FORECAST, params=params)
        r.raise_for_status()
        page = build(r.json(), name, unit)
    except Exception:
        return None
    if len(_cache) > 200:
        _cache.clear()
    _cache[key] = (time.monotonic(), page)
    return page


def valid_place(text):
    text = re.sub(r"\s+", " ", (text or "").strip())
    return text if 1 < len(text) <= 60 and re.fullmatch(r"[^\W\d_][\w .,'\-]*", text) else ""
