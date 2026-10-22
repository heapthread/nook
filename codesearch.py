"""The /code page: ask GitHub, npm, MDN, Stack Overflow and PyPI at once and list what each says.
Fetched by nook, so the visitor's browser never talks to them. All five are free and keyless."""
import asyncio
import html
import re
import time
from urllib.parse import quote

KEEP = 600
_cache = {}


def _short(text, limit=160):
    text = " ".join((text or "").split())
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0].rstrip(",.;:") + "..."


def _repos(data):
    return [{"title": r["full_name"], "url": r["html_url"], "text": _short(r.get("description")),
             "meta": " · ".join(x for x in (r.get("language"), f"{r.get('stargazers_count', 0):,} stars") if x)}
            for r in (data.get("items") or [])[:5]]


def _npm(data):
    out = []
    for o in (data.get("objects") or [])[:5]:
        p = o.get("package") or {}
        if p.get("name"):
            out.append({"title": p["name"], "url": (p.get("links") or {}).get("npm") or f"https://www.npmjs.com/package/{p['name']}",
                        "text": _short(p.get("description")), "meta": p.get("version", "")})
    return out


def _mdn(data):
    return [{"title": d["title"], "url": "https://developer.mozilla.org" + d["mdn_url"],
             "text": _short(d.get("summary")), "meta": ""}
            for d in (data.get("documents") or [])[:5] if d.get("title") and d.get("mdn_url")]


def _so(data):
    return [{"title": html.unescape(i["title"]), "url": i["link"], "text": "",
             "meta": " · ".join([f"{i.get('score', 0)} votes", f"{i.get('answer_count', 0)} answers"] + (i.get("tags") or [])[:3])}
            for i in (data.get("items") or [])[:5] if i.get("title") and i.get("link")]


def _pypi(data):
    info = (data or {}).get("info") or {}
    if not info.get("name"):
        return []
    return [{"title": info["name"], "url": f"https://pypi.org/project/{info['name']}/",
             "text": _short(info.get("summary")), "meta": info.get("version", "")}]


SOURCES = [
    ("github", "https://api.github.com/search/repositories", lambda q: {"q": q, "per_page": 5, "sort": "stars"}, _repos),
    ("npm", "https://registry.npmjs.org/-/v1/search", lambda q: {"text": q, "size": 5}, _npm),
    ("mdn", "https://developer.mozilla.org/api/v1/search", lambda q: {"q": q, "locale": "en-US"}, _mdn),
    ("stack overflow", "https://api.stackexchange.com/2.3/search/advanced",
     lambda q: {"q": q, "site": "stackoverflow", "pagesize": 5, "order": "desc", "sort": "relevance"}, _so),
]


async def _one(client, name, url, params, parse):
    r = await client.get(url, params=params)
    r.raise_for_status()
    return name, parse(r.json())


async def _package(client, q):
    name = q.strip().lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9._\-]{0,60}", name):
        return "pypi", []
    r = await client.get(f"https://pypi.org/pypi/{quote(name)}/json")
    if r.status_code == 404:
        return "pypi", []
    r.raise_for_status()
    return "pypi", _pypi(r.json())


async def search(client, query):
    """-> (sections [(name, [items])], names of sources that didn't answer)."""
    key = query.strip().lower()
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < KEEP:
        return hit[1]
    jobs = [_one(client, n, u, p(query), f) for n, u, p, f in SOURCES] + [_package(client, query)]
    done = await asyncio.gather(*jobs, return_exceptions=True)
    names = [s[0] for s in SOURCES] + ["pypi"]
    sections, failed = [], []
    for name, outcome in zip(names, done):
        if isinstance(outcome, BaseException):
            failed.append(name)
        elif outcome[1]:
            sections.append(outcome)
    result = (sections, failed)
    if sections:
        if len(_cache) > 100:
            _cache.clear()
        _cache[key] = (time.monotonic(), result)
    return result
