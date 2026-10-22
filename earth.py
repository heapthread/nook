"""The earth and space, right now: `earthquakes today`, `where is the iss`.

Earthquakes come from the US Geological Survey's public feed, the space station's position from
wheretheiss.at. Neither needs a key. Fetched by nook, remembered for a short while."""
import re
import time
from datetime import datetime, timezone

QUAKES = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/{band}_{span}.geojson"
ISS = "https://api.wheretheiss.at/v1/satellites/25544"
_cache = {}


def parse(query):
    """-> ("quakes", span) / ("iss", None) / None."""
    q = re.sub(r"\s+", " ", query.strip().lower()).rstrip("?")
    if re.match(r"^(?:where is|where's|locate|find|show) (?:the )?(?:iss|international space station|space station)$", q) or \
            q in ("iss", "iss location", "iss position", "iss now", "space station location", "space station now"):
        return "iss", None
    m = re.match(r"^(?:recent |latest |big |major |strong )?(?:earthquakes?|quakes)(?: (today|now|right now|this week|this month|recent|latest|near me))?$", q) or \
        re.match(r"^(?:earthquakes?|quakes) (?:in the )?(?:last|past) (day|week|month)$", q)
    if m:
        word = (m.group(1) or "today")
        span = "month" if "month" in word else "week" if "week" in word else "day"
        return "quakes", span
    return None


def ago(ms, now=None):
    secs = int(((now or time.time() * 1000) - ms) / 1000)
    if secs < 90:
        return "just now"
    if secs < 3600:
        return f"{secs // 60} min ago"
    if secs < 86400:
        return f"{secs // 3600} h ago"
    return f"{secs // 86400} d ago"


def parse_quakes(data, now=None, limit=10):
    items = []
    for f in (data or {}).get("features", []):
        try:
            mag = float(f["properties"]["mag"])
            lon, lat = f["geometry"]["coordinates"][:2]
            items.append({"mag": mag, "place": (f["properties"].get("place") or "somewhere").strip(),
                          "when": ago(f["properties"]["time"], now), "ms": f["properties"]["time"],
                          "url": f["properties"].get("url") or "", "lat": lat, "lon": lon,
                          "depth": f["geometry"]["coordinates"][2] if len(f["geometry"]["coordinates"]) > 2 else None})
        except (KeyError, TypeError, ValueError, IndexError):
            continue
    items.sort(key=lambda i: -i["mag"])
    return items[:limit]


def quake_card(items, span):
    words = {"day": "in the last day", "week": "in the last week", "month": "in the last month"}[span]
    return {"kind": "quakes", "title": f"earthquakes {words}", "items": items,
            "markers": [{"lat": i["lat"], "lon": i["lon"], "label": f"M{i['mag']:.1f} {i['place']}", "on": i["mag"] >= 6}
                        for i in items],
            "note": "magnitude 4.5 and above · US Geological Survey"}


def parse_iss(data):
    try:
        return {"kind": "iss", "lat": round(float(data["latitude"]), 2), "lon": round(float(data["longitude"]), 2),
                "alt": round(float(data["altitude"])), "speed": round(float(data["velocity"])),
                "visibility": str(data.get("visibility", "")).replace("eclipsed", "in the earth's shadow").replace("daylight", "in daylight")}
    except (KeyError, TypeError, ValueError):
        return None


async def quakes(client, span="day"):
    key = ("quakes", span)
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < 300:
        return hit[1]
    try:
        r = await client.get(QUAKES.format(band="4.5", span=span))
        r.raise_for_status()
        items = parse_quakes(r.json())
    except Exception:
        return None
    card = quake_card(items, span) if items else None
    _cache[key] = (time.monotonic(), card)
    return card


async def iss(client):
    hit = _cache.get("iss")
    if hit and time.monotonic() - hit[0] < 10:
        return hit[1]
    try:
        r = await client.get(ISS)
        r.raise_for_status()
        card = parse_iss(r.json())
    except Exception:
        return None
    _cache["iss"] = (time.monotonic(), card)
    return card


async def lookup(client, query):
    parsed = parse(query)
    if not parsed:
        return None
    return await (iss(client) if parsed[0] == "iss" else quakes(client, parsed[1]))
