"""Vector map tiles and fonts, fetched by nook from OpenFreeMap and passed on, so the visitor's
browser only ever talks to nook. Both are remembered for a while."""
import re
import threading
import time
from collections import OrderedDict

import httpx

TILEJSON = "https://tiles.openfreemap.org/planet"
FONTS = "https://tiles.openfreemap.org/fonts/{stack}/{range}.pbf"
STACKS = {"Noto Sans Regular", "Noto Sans Bold", "Noto Sans Italic"}
KEEP_TILES, KEEP_FONTS = 1500, 60
_tiles = OrderedDict()
_fonts = OrderedDict()
_template = [0.0, ""]
_lock = threading.Lock()
UA = {"User-Agent": "nook/1.0 (self-hosted metasearch page)"}


def configure(contact=""):
    if contact:
        UA["User-Agent"] = f"nook/1.0 ({contact})"


def valid_tile(z, x, y):
    return 0 <= z <= 14 and 0 <= x < 2 ** z and 0 <= y < 2 ** z


def template():
    """The current address pattern of the planet tiles. It changes when the map data is refreshed."""
    with _lock:
        if _template[1] and time.monotonic() - _template[0] < 3600:
            return _template[1]
    r = httpx.get(TILEJSON, headers=UA, timeout=8, follow_redirects=True)
    r.raise_for_status()
    found = r.json()["tiles"][0]
    if not found.startswith("https://tiles.openfreemap.org/"):
        raise httpx.HTTPError("unexpected tile address")
    with _lock:
        _template[:] = [time.monotonic(), found]
    return found


def _kept(store, key, limit, make):
    hit = store.get(key)
    if hit:
        store.move_to_end(key)
        return hit
    body = make()
    store[key] = body
    while len(store) > limit:
        store.popitem(last=False)
    return body


def tile(z, x, y):
    def make():
        r = httpx.get(template().format(z=z, x=x, y=y), headers=UA, timeout=10, follow_redirects=True)
        if r.status_code == 404:
            return b""            # no data here: an empty tile is a valid answer
        r.raise_for_status()
        if len(r.content) > 3_000_000:
            raise httpx.HTTPError("that tile is far too big")
        return r.content
    return _kept(_tiles, (z, x, y), KEEP_TILES, make)


def font(stack, rng):
    if stack not in STACKS or not re.fullmatch(r"\d{1,5}-\d{1,5}", rng):
        raise ValueError("no such font")

    def make():
        r = httpx.get(FONTS.format(stack=stack.replace(" ", "%20"), range=rng), headers=UA, timeout=10, follow_redirects=True)
        r.raise_for_status()
        return r.content
    return _kept(_fonts, (stack, rng), KEEP_FONTS, make)
