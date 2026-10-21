"""Related searches: what people also type after what you typed, from DuckDuckGo's suggestion
service. Fetched by nook, never by the visitor's browser."""
import json
import re
import time

URL = "https://duckduckgo.com/ac/"
KEEP = 3600
_cache = {}  # query -> (when, [suggestions])


def parse(raw, query):
    """DuckDuckGo answers [query, [suggestion, ...]]. Keep a few that are really different."""
    try:
        data = json.loads(raw)
        items = data[1]
    except (ValueError, IndexError, TypeError, KeyError):
        return []
    base = re.sub(r"\s+", " ", query.strip().lower())
    out = []
    for item in items:
        text = re.sub(r"\s+", " ", item).strip() if isinstance(item, str) else ""
        if text and text.lower() != base and len(text) <= 70 and text not in out:
            out.append(text)
    return out[:6]


async def lookup(client, query):
    key = query.strip().lower()
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < KEEP:
        return hit[1]
    try:
        r = await client.get(URL, params={"q": query, "type": "list"})
        r.raise_for_status()
        found = parse(r.text, query)
    except Exception:
        return []  # not remembered: try again next time
    if len(_cache) > 300:
        _cache.clear()
    _cache[key] = (time.monotonic(), found)
    return found
