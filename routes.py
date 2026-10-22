"""`distance from bonn to berlin`, `how far is paris from london`, `drive from bonn to cologne`,
`walk from bonn to cologne`, `bike from ... to ...`.

Places are found with OpenStreetMap's place search (the same one the maps page uses) and the way
between them with OpenStreetMap's free routing service. Where no road runs between two places
(across an ocean) nook says how far it is in a straight line and draws that."""
import asyncio
import math
import re
import time

import maps

HOST = "https://routing.openstreetmap.de"
PROFILES = {"drive": ("routed-car", "by car"), "walk": ("routed-foot", "on foot"), "bike": ("routed-bike", "by bike")}
MODES = {"drive": "drive", "driving": "drive", "car": "drive", "walk": "walk", "walking": "walk", "foot": "walk",
         "cycle": "bike", "cycling": "bike", "bike": "bike", "biking": "bike", "bicycle": "bike"}
KEEP = 3600
_cache = {}

_WORD = r"drive|driving|walk|walking|cycle|cycling|bike|biking"
_PLACE = r"[^\W\d_][\w .,'\-]{0,38}"


def _place(text):
    t = re.sub(r"\s+", " ", text.strip().strip(".,"))
    return t if 2 <= len(t) <= 40 and len(t.split()) <= 5 and "time" not in t.split() else None


def parse(query):
    """-> (from, to, mode) or None."""
    q = re.sub(r"\s+", " ", query.strip().lower()).rstrip("?")
    mode = "drive"
    tail = re.search(r" by (car|bike|bicycle|foot)$", q)
    if tail:
        mode = MODES[tail.group(1)]
        q = q[:tail.start()]
    if tail:
        m = re.match(r"^(.+?) to (.+)$", q)
        if m and _place(m.group(1)) and _place(m.group(2)):
            return _place(m.group(1)), _place(m.group(2)), mode
    m = re.match(rf"^how far is (.+?) from (.+)$", q)
    if m and _place(m.group(1)) and _place(m.group(2)):
        return _place(m.group(2)), _place(m.group(1)), mode
    m = re.match(rf"^(?:how long (?:does it take )?(?:to )?|how far (?:is it )?(?:to )?)?({_WORD})(?: distance)?(?: from)? (.+?) to (.+)$", q)
    if m and _place(m.group(2)) and _place(m.group(3)):
        return _place(m.group(2)), _place(m.group(3)), MODES[m.group(1)]
    m = re.match(r"^(?:distance|route|directions?|travel time|how far)(?: from| between)? (.+?) (?:to|and) (.+)$", q)
    if m and _place(m.group(1)) and _place(m.group(2)):
        return _place(m.group(1)), _place(m.group(2)), mode
    m = re.match(r"^(.+?) to (.+?) (?:distance|route|directions?)$", q)
    if m and _place(m.group(1)) and _place(m.group(2)):
        return _place(m.group(1)), _place(m.group(2)), mode
    return None


def haversine(a, b):
    """Kilometres in a straight line between two (lat, lon) points."""
    (la1, lo1), (la2, lo2) = (math.radians(a[0]), math.radians(a[1])), (math.radians(b[0]), math.radians(b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371.0088 * math.asin(math.sqrt(h))


def span(seconds):
    minutes = round(seconds / 60)
    if minutes < 1:
        return "under a minute"
    if minutes < 60:
        return f"{minutes} min"
    hours, minutes = divmod(minutes, 60)
    if hours < 24:
        return f"{hours} h {minutes} min" if minutes else f"{hours} h"
    days, hours = divmod(hours, 24)
    return f"{days} d {hours} h" if hours else f"{days} d"


def thin(points, limit=300):
    if len(points) <= limit:
        return points
    step = len(points) / limit
    out = [points[int(i * step)] for i in range(limit)]
    return out + [points[-1]]


def fit(points):
    """Centre and zoom that show every point."""
    lats, lons = [p[0] for p in points], [p[1] for p in points]
    box = [min(lats), max(lats), min(lons), max(lons)]
    zoom = maps.zoom_from_box([str(v) for v in box])
    return (box[0] + box[1]) / 2, (box[2] + box[3]) / 2, max(2, zoom - 1)


def build(a, b, mode, route):
    """The card, from two places and OSRM's answer (None when no road joins them)."""
    start, end = (a["lat"], a["lon"]), (b["lat"], b["lon"])
    crow = haversine(start, end)
    if route:
        path = [[lat, lon] for lon, lat in route["geometry"]["coordinates"]]
        km, seconds, how = route["distance"] / 1000, route["duration"], PROFILES[mode][1]
    else:
        path, km, seconds, how = [list(start), list(end)], crow, None, "in a straight line"
    lat, lon, zoom = fit(path)
    return {"kind": "route", "from": a["label"], "to": b["label"], "how": how, "km": round(km, 1 if km < 100 else 0),
            "mi": round(km * 0.621371, 1 if km < 100 else 0), "crow": round(crow, 1 if crow < 100 else 0),
            "time": span(seconds) if seconds else "", "straight": route is None,
            "line": thin(path), "lat": lat, "lon": lon, "zoom": zoom,
            "markers": [{"lat": start[0], "lon": start[1], "label": a["label"], "on": True},
                        {"lat": end[0], "lon": end[1], "label": b["label"], "on": True}]}


async def geocode(text):
    found = await asyncio.to_thread(maps.search, text)
    if not found:
        return None
    first = found[0]
    country = first["where"].split(", ")[-1] if first["where"] else ""
    return {"lat": first["lat"], "lon": first["lon"],
            "label": first["name"] + (f", {country}" if country and country != first["name"] else "")}


async def find_route(client, a, b, mode):
    profile = PROFILES[mode][0]
    url = f"{HOST}/{profile}/route/v1/driving/{a['lon']},{a['lat']};{b['lon']},{b['lat']}"
    try:
        r = await client.get(url, params={"overview": "full", "geometries": "geojson"})
        r.raise_for_status()
        data = r.json()
        if data.get("code") != "Ok" or not data.get("routes"):
            return None
        # the service only knows its own map: a place outside it gets snapped to the nearest road far away
        if any(w.get("distance", 0) > 3000 for w in data.get("waypoints", [])):
            return None
        return data["routes"][0]
    except Exception:
        return None


async def lookup(client, query):
    parsed = parse(query)
    if not parsed:
        return None
    key = parsed
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < KEEP:
        return hit[1]
    try:
        a, b = await asyncio.gather(geocode(parsed[0]), geocode(parsed[1]))
    except Exception:
        return None
    if not a or not b:
        return None
    route = await find_route(client, a, b, parsed[2])
    card = build(a, b, parsed[2], route)
    if len(_cache) > 200:
        _cache.clear()
    _cache[key] = (time.monotonic(), card)
    return card
