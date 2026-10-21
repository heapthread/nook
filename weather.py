"""The weather card: now, the next few days, sunrise and sunset. Place search and forecast both
come from Open-Meteo (free, no key), fetched by nook and remembered for a while."""
import re
import time

GEOCODER = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST = "https://api.open-meteo.com/v1/forecast"
KEEP = 900  # a forecast is good for fifteen minutes
_cache = {}  # place -> (when, card)

# WMO weather codes
WORDS = {
    0: "clear sky", 1: "mostly clear", 2: "partly cloudy", 3: "overcast", 45: "fog", 48: "freezing fog",
    51: "light drizzle", 53: "drizzle", 55: "heavy drizzle", 56: "freezing drizzle", 57: "freezing drizzle",
    61: "light rain", 63: "rain", 65: "heavy rain", 66: "freezing rain", 67: "freezing rain",
    71: "light snow", 73: "snow", 75: "heavy snow", 77: "snow grains", 80: "light showers",
    81: "showers", 82: "heavy showers", 85: "snow showers", 86: "heavy snow showers",
    95: "thunderstorm", 96: "thunderstorm with hail", 99: "thunderstorm with hail",
}


def place_in(query):
    """'weather in bonn', 'bonn weather', 'forecast for oslo', 'sunrise in lagos' -> the place, or None."""
    q = re.sub(r"\s+", " ", query.strip().lower()).rstrip("?")
    for pattern in (
        r"^(?:what(?:'s| is) the )?(?:weather|forecast|temperature)(?: forecast)?(?: like)?(?: in| for| at)? (.+)$",
        r"^(?:what(?:'s| is) the )?weather(?: like)?$",
        r"^(.+?) (?:weather|forecast|temperature)$",
        r"^(?:sunrise|sunset)(?: and sunset)?(?: times?)?(?: in| for| at)? (.+)$",
        r"^(.+?) (?:sunrise|sunset)(?: times?)?$",
    ):
        m = re.match(pattern, q)
        if m and m.groups():
            place = re.sub(r"^(?:the )?(?:current )?", "", m.group(1)).strip()
            chatter = {"how", "what", "is", "are", "will", "it", "going", "be", "today", "tomorrow", "now", "like",
                       "there", "outside", "the", "this", "weekend", "week", "in", "for", "at", "on", "of"}
            if re.fullmatch(r"[a-z][a-z .'\-]{1,40}", place) and not chatter & set(place.split()):
                return place
    return None


def best_place(data, name):
    """The populated place called exactly `name` (the biggest, if several)."""
    from places import _norm
    best = None
    for item in (data or {}).get("results") or []:
        if _norm(item.get("name", "")) != _norm(name) or not str(item.get("feature_code", "")).startswith("PPL"):
            continue
        if best is None or (item.get("population") or 0) > (best.get("population") or 0):
            best = item
    return best


def _t(value):
    return f"{round(value)}°"


def parse_forecast(data, label):
    cur, daily = data.get("current") or {}, data.get("daily") or {}
    if "temperature_2m" not in cur or not daily.get("time"):
        return None
    from datetime import date
    days = []
    for i, day in enumerate(daily["time"][:5]):
        name = "today" if i == 0 else date.fromisoformat(day).strftime("%A").lower()
        days.append({"day": name, "text": WORDS.get(daily["weather_code"][i], ""),
                     "low": _t(daily["temperature_2m_min"][i]), "high": _t(daily["temperature_2m_max"][i]),
                     "rain": daily["precipitation_probability_max"][i] if daily.get("precipitation_probability_max") else None})
    celsius = cur["temperature_2m"]
    return {
        "kind": "weather", "place": label,
        "temp": f"{round(celsius)}°C", "temp_f": f"{round(celsius * 9 / 5 + 32)}°F",
        "text": WORDS.get(cur.get("weather_code"), ""),
        "feels": _t(cur["apparent_temperature"]) if "apparent_temperature" in cur else "",
        "wind": f"{round(cur['wind_speed_10m'])} km/h" if "wind_speed_10m" in cur else "",
        "humidity": f"{round(cur['relative_humidity_2m'])}%" if "relative_humidity_2m" in cur else "",
        "days": days,
        "sunrise": (daily.get("sunrise") or [""])[0][-5:], "sunset": (daily.get("sunset") or [""])[0][-5:],
        "credit": "weather: open-meteo.com",
    }


async def lookup(client, place):
    hit = _cache.get(place)
    if hit and time.monotonic() - hit[0] < KEEP:
        return hit[1]
    try:
        r = await client.get(GEOCODER, params={"name": place, "count": 10, "language": "en", "format": "json"})
        r.raise_for_status()
        found = best_place(r.json(), place)
        if not found:
            return None
        r = await client.get(FORECAST, params={
            "latitude": found["latitude"], "longitude": found["longitude"], "timezone": "auto", "forecast_days": 5,
            "current": "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,sunrise,sunset,precipitation_probability_max",
        })
        r.raise_for_status()
        label = f"{found['name'].lower()}, {found['country'].lower()}" if found.get("country") else found["name"].lower()
        card = parse_forecast(r.json(), label)
    except Exception:
        return None
    if len(_cache) > 200:
        _cache.clear()
    _cache[place] = (time.monotonic(), card)
    return card
