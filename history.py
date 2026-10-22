"""The past and the present day: `on this day`, `what happened on 22 october`, and for the /learn
page the word of the day (Wiktionary) and today's featured article (Wikipedia).

All from Wikimedia's free feeds, fetched by nook, remembered for hours."""
import re
import time
from datetime import datetime
from xml.etree import ElementTree as ET

from selectolax.lexbor import LexborHTMLParser

import wiki

MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
          "november", "december"]
_cache = {}
KEEP = 6 * 3600
_M = "|".join(MONTHS)


DAYS = [31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]


def parse(query, now=None):
    """-> (month, day) for 'on this day' style queries, else None."""
    q = re.sub(r"\s+", " ", query.strip().lower()).rstrip("?")
    today = now or datetime.now()
    if re.match(r"^(?:on this day|this day in history|today in history|history today|what happened today|"
                r"what happened on this day|what happened in history today)$", q):
        return today.month, today.day
    day_first = re.match(rf"^(?:what happened|events|history)(?: on| in)? (\d{{1,2}})(?:st|nd|rd|th)?(?: of)? ({_M})(?: in history)?$", q)
    month_first = re.match(rf"^(?:(?:what happened|events|history)(?: on| in)? )?({_M}) (\d{{1,2}})(?:st|nd|rd|th)?(?: in history| events)?$", q)
    if day_first:
        day, month = int(day_first.group(1)), MONTHS.index(day_first.group(2)) + 1
    elif month_first:
        day, month = int(month_first.group(2)), MONTHS.index(month_first.group(1)) + 1
    else:
        return None
    return (month, day) if 1 <= day <= DAYS[month - 1] else None


def parse_selected(data, limit=7):
    """A spread of the day's events, newest first, each with the Wikipedia page it is about."""
    items = []
    for e in (data or {}).get("selected", []) + (data or {}).get("events", []):
        text, year = (e.get("text") or "").strip(), e.get("year")
        if not text or year is None:
            continue
        page = next((p for p in e.get("pages", []) if (p.get("content_urls") or {}).get("desktop", {}).get("page")), None)
        items.append({"year": int(year), "text": text[:260],
                      "url": page["content_urls"]["desktop"]["page"] if page else ""})
    items.sort(key=lambda i: -i["year"])
    seen, out = set(), []
    for i in items:
        if i["year"] in seen:
            continue
        seen.add(i["year"])
        out.append(i)
    if len(out) > limit:       # spread them over the centuries instead of only the newest
        step = (len(out) - 1) / (limit - 1)
        out = [out[round(n * step)] for n in range(limit)]
    return out


async def _json(client, url):
    r = await client.get(url, headers=wiki.headers())
    r.raise_for_status()
    return r.json()


async def on_this_day(client, month, day):
    key = ("day", month, day)
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < KEEP:
        return hit[1]
    try:
        data = await _json(client, f"https://api.wikimedia.org/feed/v1/wikipedia/en/onthisday/selected/{month:02d}/{day:02d}")
    except Exception:
        return None
    items = parse_selected(data)
    card = {"kind": "history", "title": f"{day} {MONTHS[month - 1]}", "items": items} if items else None
    _cache[key] = (time.monotonic(), card)
    return card


async def lookup(client, query):
    when = parse(query)
    return await on_this_day(client, *when) if when else None


# --- the /learn page ---------------------------------------------------------------

def parse_wotd(xml):
    """The newest word of the day from Wiktionary's feed: {word, definition, url}."""
    A = "{http://www.w3.org/2005/Atom}"
    try:
        entries = ET.fromstring(xml).findall(f"{A}entry")
    except ET.ParseError:
        return None
    if not entries:
        return None
    summary = entries[-1].find(f"{A}summary")
    tree = LexborHTMLParser(summary.text or "") if summary is not None else None
    if tree is None:
        return None
    word = ""
    for a in tree.css("a[href*='#English']"):
        word = (a.attributes.get("title") or "").strip()
        if word:
            break
    if not word:
        return None
    li = tree.css_first("ol li")
    definition = re.sub(r"\s+", " ", li.text(deep=True)).strip() if li is not None else ""
    return {"word": word, "definition": definition[:220], "url": "https://en.wiktionary.org/wiki/" + word.replace(" ", "_")}


def parse_featured(data):
    tfa = (data or {}).get("tfa") or {}
    if not tfa.get("extract"):
        return None
    return {"title": re.sub(r"<[^>]+>", "", tfa.get("displaytitle") or tfa.get("title", "")).strip(),
            "text": tfa["extract"][:420], "image": (tfa.get("thumbnail") or {}).get("source", ""),
            "url": (tfa.get("content_urls") or {}).get("desktop", {}).get("page", "")}


async def learn(client, now=None):
    """-> {word, article, day}: whichever of them could be fetched."""
    today = now or datetime.now()
    key = ("learn", today.date())
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < KEEP:
        return hit[1]
    import asyncio
    jobs = await asyncio.gather(
        client.get("https://en.wiktionary.org/w/api.php", params={"action": "featuredfeed", "feed": "wotd", "feedformat": "atom"}, headers=wiki.headers()),
        _json(client, f"https://api.wikimedia.org/feed/v1/wikipedia/en/featured/{today:%Y/%m/%d}"),
        on_this_day(client, today.month, today.day), return_exceptions=True)
    out = {"word": None, "article": None, "day": None}
    if not isinstance(jobs[0], BaseException) and jobs[0].status_code == 200:
        out["word"] = parse_wotd(jobs[0].content)
    if not isinstance(jobs[1], BaseException):
        out["article"] = parse_featured(jobs[1])
    if not isinstance(jobs[2], BaseException):
        out["day"] = jobs[2]
    if any(out.values()):
        _cache[key] = (time.monotonic(), out)
    return out
