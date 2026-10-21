import json
import re

from . import Video

NAME = "duckduckgo videos"
SUPPORTS_SAFE = True
SAFE = {"strict": "1", "off": "-2"}


def can_region(code):
    return True


def _views(n):
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M views"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K views"
    return f"{n} views"


def parse(text):
    out = []
    for item in json.loads(text).get("results", []):
        thumbs = item.get("images") or {}
        thumb = thumbs.get("medium") or thumbs.get("large") or thumbs.get("small") or ""
        if not (item.get("content") and item.get("title") and thumb):
            continue
        views = (item.get("statistics") or {}).get("viewCount")
        parts = [item.get("uploader") or item.get("publisher") or "",
                 _views(views) if views else "",
                 (item.get("published") or "")[:10]]
        out.append(Video(
            title=item["title"],
            url=item["content"],
            thumb=thumb,
            duration=item.get("duration", ""),
            meta=" · ".join(p for p in parts if p),
        ))
    return out


async def search(client, query, page=1, region=None, safe=None, **_):
    # DuckDuckGo wants a one-off token (vqd) taken from its search page first.
    landing = await client.get("https://duckduckgo.com/", params={"q": query, "iax": "videos", "ia": "videos"})
    landing.raise_for_status()
    m = re.search(r"vqd=[\"']?([\d-]+)", landing.text)
    if not m:
        raise RuntimeError("no vqd token")
    r = await client.get("https://duckduckgo.com/v.js", params={
        "l": region or "us-en", "o": "json", "q": query, "vqd": m.group(1), "f": ",,,,,", "p": SAFE.get(safe, "1"),
        "s": (page - 1) * 59,
    }, headers={"Referer": "https://duckduckgo.com/"})
    r.raise_for_status()
    return parse(r.text)
