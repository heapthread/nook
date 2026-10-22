"""The /books page: search books and authors, from Open Library (free, no key).

Open Library has ratings but not written reviews, so each book links to a web search for reviews.
Covers are fetched by nook, like every other picture."""
import re
import time

SEARCH = "https://openlibrary.org/search.json"
FIELDS = "key,title,author_name,first_publish_year,cover_i,ratings_average,ratings_count,subject,edition_count,number_of_pages_median"
KEEP = 3600
_cache = {}


def cover(cover_id, size="M"):
    return f"https://covers.openlibrary.org/b/id/{int(cover_id)}-{size}.jpg" if cover_id else ""


def parse_search(data):
    out = []
    for d in (data or {}).get("docs", []):
        m = re.fullmatch(r"/works/(OL\d+W)", d.get("key", ""))
        if not (m and d.get("title")):
            continue
        rating = d.get("ratings_average")
        out.append({
            "id": m.group(1), "title": d["title"], "authors": ", ".join((d.get("author_name") or [])[:3]),
            "year": d.get("first_publish_year") or "", "cover": cover(d.get("cover_i")),
            "rating": f"{rating:.1f}" if rating else "", "votes": d.get("ratings_count") or 0,
            "editions": d.get("edition_count") or 0, "pages": d.get("number_of_pages_median") or "",
            "subjects": [s for s in (d.get("subject") or []) if len(s) < 30 and ":" not in s][:4],
        })
    return out


def description(value):
    text = value.get("value", "") if isinstance(value, dict) else (value or "")
    text = re.split(r"\r?\n-{3,}|\r?\n\s*\(?\[?source", text)[0]
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)            # markdown links -> their words
    return re.sub(r"\s+", " ", text).strip()[:1200]


def parse_work(work, authors, ratings):
    if not work.get("title"):
        return None
    average = (ratings or {}).get("summary", {}).get("average")
    count = (ratings or {}).get("summary", {}).get("count") or 0
    return {
        "id": work.get("key", "").rsplit("/", 1)[-1], "title": work["title"], "subtitle": work.get("subtitle", ""),
        "authors": authors, "description": description(work.get("description")),
        "cover": cover((work.get("covers") or [None])[0], "L"), "first": work.get("first_publish_date", ""),
        "subjects": [s for s in (work.get("subjects") or []) if len(s) < 40][:12],
        "rating": f"{average:.1f}" if average else "", "votes": count,
    }


async def search(client, query):
    key = query.strip().lower()
    hit = _cache.get(("s", key))
    if hit and time.monotonic() - hit[0] < KEEP:
        return hit[1]
    try:
        r = await client.get(SEARCH, params={"q": query, "limit": 16, "fields": FIELDS})
        r.raise_for_status()
        found = parse_search(r.json())
    except Exception:
        return None
    if len(_cache) > 200:
        _cache.clear()
    _cache[("s", key)] = (time.monotonic(), found)
    return found


async def work(client, work_id):
    if not re.fullmatch(r"OL\d{1,10}W", work_id or ""):
        return None
    hit = _cache.get(("w", work_id))
    if hit and time.monotonic() - hit[0] < KEEP:
        return hit[1]
    import asyncio
    try:
        r = await client.get(f"https://openlibrary.org/works/{work_id}.json")
        r.raise_for_status()
        data = r.json()
        keys = [a["author"]["key"] for a in data.get("authors", []) if (a.get("author") or {}).get("key", "").startswith("/authors/OL")][:3]

        async def one(k):
            a = await client.get(f"https://openlibrary.org{k}.json")
            return a.json().get("name", "") if a.status_code == 200 else ""
        names, rated = await asyncio.gather(asyncio.gather(*(one(k) for k in keys)),
                                            client.get(f"https://openlibrary.org/works/{work_id}/ratings.json"), return_exceptions=True)
        found = parse_work(data, ", ".join(n for n in (names if isinstance(names, list) else []) if n),
                           rated.json() if not isinstance(rated, BaseException) and rated.status_code == 200 else None)
    except Exception:
        return None
    _cache[("w", work_id)] = (time.monotonic(), found)
    return found
