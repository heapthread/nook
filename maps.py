"""Maps, the nook way.

The picture of the map comes from OpenStreetMap's tiles (or whichever tile server `tile_url` in
config.toml names). Tiles are fetched by nook and passed on, so the visitor's browser only talks
to nook, and nook remembers tiles for a while, which is what OpenStreetMap's tile rules ask of
anyone who serves their maps. Finding a place by name uses OpenStreetMap's Nominatim, one question
a second at most, as its rules require."""
import math
import re
import threading
import time
from collections import OrderedDict

import httpx

TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
CREDIT = "© OpenStreetMap contributors"
CREDIT_URL = "https://www.openstreetmap.org/copyright"
SEARCH_URL = "https://nominatim.openstreetmap.org/search"
CONTACT = ""   # shown to OpenStreetMap's servers in the User-Agent, as their rules ask
KEEP_TILES = 900
KEEP_PLACES = 3600

_tiles = OrderedDict()   # (z, x, y) -> (when, bytes)
_places = {}             # (query, language) -> (when, [places])
_gate = threading.Lock()
_last = [0.0]


def configure(tile_url=None, credit=None, credit_url=None, contact=""):
    global TILE_URL, CREDIT, CREDIT_URL, CONTACT
    CONTACT = contact or ""
    if tile_url:
        TILE_URL = tile_url
    if credit:
        CREDIT = credit
    if credit_url:
        CREDIT_URL = credit_url


def headers():
    who = CONTACT or "self-hosted metasearch page"
    return {"User-Agent": f"nook/1.0 ({who})", "Accept": "image/png,image/*;q=0.8,application/json;q=0.8"}


def valid_tile(z, x, y):
    return 0 <= z <= 19 and 0 <= x < 2 ** z and 0 <= y < 2 ** z


def tile(z, x, y):
    """The picture (PNG bytes) of one map tile. Raises httpx.HTTPError if the tile server says no."""
    key = (z, x, y)
    hit = _tiles.get(key)
    if hit and time.monotonic() - hit[0] < 7 * 86400:
        _tiles.move_to_end(key)
        return hit[1]
    r = httpx.get(TILE_URL.format(z=z, x=x, y=y), headers=headers(), timeout=8, follow_redirects=True)
    r.raise_for_status()
    if len(r.content) > 400_000:
        raise httpx.HTTPError("that tile is far too big")
    _tiles[key] = (time.monotonic(), r.content)
    while len(_tiles) > KEEP_TILES:
        _tiles.popitem(last=False)
    return r.content


def zoom_from_box(box):
    """How far in to show a place from its bounding box [south, north, west, east]."""
    try:
        south, north, west, east = (float(v) for v in box)
    except (TypeError, ValueError):
        return 12
    span = max(abs(east - west), abs(north - south) * 1.6, 0.0005)
    return max(3, min(17, int(math.log2(360 / span)) + 1))   # about two tiles across the page


def parse(data):
    """Nominatim's answer -> a short list of places a map can show."""
    out = []
    for item in data if isinstance(data, list) else []:
        try:
            lat, lon = float(item["lat"]), float(item["lon"])
        except (KeyError, TypeError, ValueError):
            continue
        name = (item.get("display_name") or "").strip()
        if not name:
            continue
        head, _, rest = name.partition(", ")
        kind = (item.get("type") or item.get("category") or "").replace("_", " ")
        out.append({"name": head, "where": rest[:110], "kind": kind, "lat": lat, "lon": lon,
                    "zoom": zoom_from_box(item.get("boundingbox")),
                    "osm": f"https://www.openstreetmap.org/?mlat={lat:.5f}&mlon={lon:.5f}#map={zoom_from_box(item.get('boundingbox'))}/{lat:.5f}/{lon:.5f}"})
    return out[:6]


_raw = {}   # (endpoint, params) -> (when, answer)


def nominatim(endpoint, params):
    """A raw Nominatim answer (a list), for the places pages. One question a second at most, remembered for an hour."""
    key = (endpoint, tuple(sorted((k, str(v)) for k, v in params.items())))
    hit = _raw.get(key)
    if hit and time.monotonic() - hit[0] < KEEP_PLACES:
        return hit[1]
    with _gate:
        wait = 1.05 - (time.monotonic() - _last[0])
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.monotonic()
        r = httpx.get(f"https://nominatim.openstreetmap.org/{endpoint}", params={**params, "format": "jsonv2"},
                      headers=headers(), timeout=10)
    r.raise_for_status()
    data = r.json()
    if len(_raw) > 300:
        _raw.clear()
    _raw[key] = (time.monotonic(), data)
    return data


def search(query, language="en"):
    """Places called `query`, remembered for an hour. Raises httpx.HTTPError when OpenStreetMap is unreachable."""
    key = (re.sub(r"\s+", " ", query.strip().lower()), language)
    hit = _places.get(key)
    if hit and time.monotonic() - hit[0] < KEEP_PLACES:
        return hit[1]
    with _gate:  # Nominatim's rule: at most one question a second
        wait = 1.05 - (time.monotonic() - _last[0])
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.monotonic()
        r = httpx.get(SEARCH_URL, params={"q": query, "format": "jsonv2", "limit": 6, "accept-language": language},
                      headers=headers(), timeout=8)
    r.raise_for_status()
    found = parse(r.json())
    if len(_places) > 200:
        _places.clear()
    _places[key] = (time.monotonic(), found)
    return found
