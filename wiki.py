"""A smart look-up in Wikipedia for whatever was typed.

Nothing is hardcoded about any topic. A short query is tried as an article title first (so
redirects work: "hotlink" leads to "Inline linking"), then as a Wikipedia search, and a search
hit is only used when it really covers every word that was typed. The card also gets, when the
article has them: a picture, a few more pictures, the flag of the country it is about, the
place on a map, and the Simple English version of the same subject.

Everything is fetched by nook, never by the visitor's browser."""
import asyncio
import math
import re
import time
import unicodedata
from urllib.parse import quote

TTL = 3600
CONTACT = ""  # shared with the wikipedia engine; Wikimedia asks every client to say who it is
_cache = {}   # (host, query) -> (when, card or None)

# a region's language part ("de" in "de-de") -> the Wikipedia that speaks it
LANGS = {
    "en": "en", "de": "de", "fr": "fr", "es": "es", "it": "it", "nl": "nl", "pt": "pt", "pl": "pl",
    "sv": "sv", "da": "da", "no": "no", "fi": "fi", "cs": "cs", "sk": "sk", "sl": "sl", "hr": "hr",
    "hu": "hu", "ro": "ro", "bg": "bg", "el": "el", "tr": "tr", "ru": "ru", "uk": "uk", "ar": "ar",
    "et": "et", "lv": "lv", "lt": "lt", "is": "is", "jp": "ja", "kr": "ko", "zh": "zh", "tzh": "zh",
}
STOP = {"the", "of", "a", "an", "and", "in", "on", "for", "to", "de", "la", "le", "von", "der", "die", "das"}
SKIP_PICTURE = re.compile(r"flag|map|logo|icon|symbol|signature|coat[_ ]of|seal|locator|commons-|wiki|diagram|chart", re.I)


def lang_for(region):
    """The Wikipedia language for a region code like "de-de"; English when there is none."""
    return LANGS.get((region or "").split("-")[-1], "en")


def headers():
    who = CONTACT or "self-hosted metasearch page"
    return {"User-Agent": f"nook/1.0 ({who})", "Api-User-Agent": f"nook/1.0 ({who})"}


def _fold(text):
    text = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in text if not unicodedata.combining(c)).lower()


def _words(text):
    return [w for w in re.findall(r"[a-z0-9]+", _fold(text)) if w not in STOP]


def _close(a, b):
    return a == b or (min(len(a), len(b)) >= 4 and (a.startswith(b) or b.startswith(a)))


def covers(query, *texts):
    """Does every word of the query show up (or nearly: hotlink / hotlinking) in these texts?"""
    wanted = _words(query)
    have = [w for t in texts for w in _words(t)]
    return bool(wanted) and all(any(_close(w, h) for h in have) for w in wanted)


def zoom_for(coords):
    """How far in to look at a place: from the size Wikipedia gives it, else from its kind."""
    try:
        size = float(coords.get("dim") or 0)
    except (TypeError, ValueError):
        size = 0
    if size > 0:
        return max(3, min(15, round(math.log2(26_700_000 / size))))
    return {"country": 5, "state": 7, "adm1st": 7, "adm2nd": 9, "city": 11, "isle": 9, "mountain": 11,
            "river": 9, "airport": 13, "landmark": 14, "edu": 15}.get(coords.get("type") or "", 12)


# --- the Wikipedia calls ---------------------------------------------------

async def _api(client, host, **params):
    params.update(format="json", formatversion=2)
    r = await client.get(f"https://{host}/w/api.php", params=params, headers=headers())
    r.raise_for_status()
    return r.json()


def _paragraphs(extract, limit=560):
    """The opening of an article as plain text, cut after a whole sentence."""
    text = re.sub(r"\s*\n\s*", "\n", extract or "").strip()
    first = text.split("\n")
    out = first[0]
    for more in first[1:]:
        if len(out) >= 200:
            break
        out += " " + more
    if len(out) > limit:
        cut = out[:limit]
        stop = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
        out = cut[:stop + 1] if stop > 120 else cut.rstrip() + "..."
    return out.strip()


def _variants(query):
    q = re.sub(r"\s+", " ", query.strip())
    titled = " ".join(w[:1].upper() + w[1:] for w in q.split(" "))
    return [q] if q == titled else [q, titled]


VAGUE = {}  # the title is a disambiguation page: it means too many things to pick one


def pick_page(data, variants):
    """The first real article among the titles asked for. VAGUE if the title names many things."""
    query = data.get("query") or {}
    moved = {r["from"]: r["to"] for r in query.get("redirects", [])}
    moved.update({r["from"]: r["to"] for r in query.get("normalized", [])})
    pages = {p.get("title"): p for p in query.get("pages", [])}
    for v in variants:
        title = v
        for _ in range(3):
            title = moved.get(title, title)
        page = pages.get(title)
        if page and not page.get("missing"):
            if "disambiguation" in (page.get("pageprops") or {}):
                return VAGUE
            if len(page.get("extract") or "") >= 40:
                return page
    return None


DETAILS = dict(action="query", redirects=1, prop="extracts|pageimages|pageprops|coordinates|info|description",
               exintro=1, explaintext=1, exsentences=6, exlimit="max", piprop="thumbnail", pithumbsize=500,
               ppprop="wikibase_item|disambiguation", coprop="type|dim|country", inprop="url")


async def _by_title(client, host, titles):
    data = await _api(client, host, titles="|".join(titles), **DETAILS)
    return pick_page(data, titles)


async def _by_search(client, host, query):
    """Wikipedia's own search, trusting a hit only if it covers everything that was typed."""
    # (a hit that is a disambiguation page comes back as VAGUE from _by_title and is skipped)
    data = await _api(client, host, action="query", list="search", srsearch=query, srlimit=4,
                      srprop="snippet|redirecttitle", srenablerewrites=1)
    for hit in (data.get("query") or {}).get("search", []):
        if covers(query, hit.get("title", ""), hit.get("redirecttitle", "")):
            page = await _by_title(client, host, [hit["title"]])
            if page and page is not VAGUE:
                return page
    return None


async def claims(client, entity, prop):
    """Wikidata statements still true today (no end date), best first. [] if none."""
    r = await client.get("https://www.wikidata.org/w/api.php", headers=headers(), params={
        "action": "wbgetclaims", "entity": entity, "property": prop, "format": "json"})
    r.raise_for_status()
    found = (r.json().get("claims") or {}).get(prop, [])
    live = [c for c in found if c.get("rank") != "deprecated" and "P582" not in (c.get("qualifiers") or {})]
    live.sort(key=lambda c: c.get("rank") != "preferred")
    return [c["mainsnak"]["datavalue"]["value"] for c in live if (c.get("mainsnak") or {}).get("datavalue")]


def flag_url(filename):
    return "https://commons.wikimedia.org/wiki/Special:FilePath/" + quote(filename.replace(" ", "_")) + "?width=160"


async def flag(client, qid, is_place):
    """The flag of the thing itself, or of the country it is in."""
    try:
        own = await claims(client, qid, "P41")
        if own:
            return flag_url(own[0])
        if is_place:
            country = await claims(client, qid, "P17")
            if country:
                theirs = await claims(client, country[0]["id"], "P41")
                if theirs:
                    return flag_url(theirs[0])
    except Exception:
        pass
    return ""


def parse_media(raw):
    """A few photographs from an article (no flags, maps, logos or icons)."""
    out = []
    for item in (raw or {}).get("items", []):
        title = item.get("title", "")
        if item.get("type") != "image" or not item.get("showInGallery") or item.get("leadImage"):
            continue
        if not re.search(r"\.(jpe?g|png|webp)$", title, re.I) or SKIP_PICTURE.search(title):
            continue
        srcset = item.get("srcset") or []
        if not srcset:
            continue
        src = srcset[0].get("src", "")
        src = "https:" + src if src.startswith("//") else src
        if src.startswith("https://"):
            out.append({"src": src, "caption": ((item.get("caption") or {}).get("text") or "")[:120],
                        "title": title})
        if len(out) == 4:
            break
    return out


async def pictures(client, host, title):
    try:
        r = await client.get(f"https://{host}/api/rest_v1/page/media-list/{quote(title.replace(' ', '_'), safe='')}",
                            headers=headers())
        r.raise_for_status()
        shots = parse_media(r.json())
        for shot in shots:
            shot["page"] = f"https://{host}/wiki/" + quote(shot["title"].replace(" ", "_"), safe=":")
        return shots
    except Exception:
        return []


async def _simple_page(client, query, title):
    host = "simple.wikipedia.org"
    page = await _by_title(client, host, _variants(query) + ([title] if title else []))
    if page is VAGUE:
        return None
    return page or await _by_search(client, host, query)


async def simple_version(client, query, title):
    """The same subject in Simple English, if there is a page for it."""
    try:
        page = await _simple_page(client, query, title)
    except Exception:
        return None
    if not page:
        return None
    return {"title": page["title"], "text": _paragraphs(page.get("extract"), 420),
            "url": page.get("fullurl") or f"https://simple.wikipedia.org/wiki/{quote(page['title'].replace(' ', '_'))}"}


def build(page, host):
    coords = (page.get("coordinates") or [None])[0]
    about = (page.get("description") or "").strip()
    return {
        "kind": "wiki", "title": page["title"], "about": about[:90], "text": _paragraphs(page.get("extract")),
        "url": page.get("fullurl") or f"https://{host}/wiki/{quote(page['title'].replace(' ', '_'))}",
        "source": host.split(".")[0] + ".wikipedia.org" if not host.startswith("en.") else "Wikipedia",
        "image": ((page.get("thumbnail") or {}).get("source") or ""),
        "pictures": [], "simple": None, "flag": "", "life": None,
        "map": {"lat": coords["lat"], "lon": coords["lon"], "zoom": zoom_for(coords), "label": page["title"]}
               if coords and "lat" in coords and "lon" in coords else None,
        "qid": (page.get("pageprops") or {}).get("wikibase_item", ""),
    }


async def find(client, query, lang="en"):
    host = f"{lang}.wikipedia.org"
    page = await _by_title(client, host, _variants(query))
    if page is VAGUE:
        return None
    page = page or await _by_search(client, host, query)
    if page is None and lang == "en":
        # not in English Wikipedia at all: Simple English may still have it
        page = await _simple_page(client, query, None)
        host = "simple.wikipedia.org" if page else host
    if not page:
        return None
    card = build(page, host)
    if len(card["text"]) < 40:
        return None
    jobs = [pictures(client, host, page["title"])]
    if card["qid"]:
        jobs.append(flag(client, card["qid"], bool(card["map"])))
        if not card["map"]:
            jobs.append(life(client, card["qid"]))
    if lang == "en" and host.startswith("en."):
        jobs.append(simple_version(client, query, page["title"]))
    tasks = [asyncio.ensure_future(j) for j in jobs]
    await asyncio.wait(tasks, timeout=3.5)  # the extras are nice to have, so never wait long for them
    extras = []
    for t in tasks:
        if not t.done():
            t.cancel()
        extras.append(t.result() if t.done() and not t.cancelled() and not t.exception() else None)
    card["pictures"] = (extras[0] or [])
    rest = extras[1:]
    if card["qid"]:
        card["flag"] = rest.pop(0) or ""
        if not card["map"]:
            card["life"] = rest.pop(0)
    if card["flag"] and re.search(r"flag|flagge|drapeau|bandera|bandiera", card["image"], re.I):
        card["image"] = ""  # the article's own picture is the flag, and the flag is already shown
    if rest:
        simple = rest.pop(0)
        if simple and simple["text"] and _words(simple["text"]) != _words(card["text"]):
            card["simple"] = simple
    return card


async def suggestion(client, query, lang="en"):
    """Wikipedia's own "did you mean" for a query, or None. Remembered for an hour."""
    key = ("did-you-mean", lang, query.strip().lower())
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < TTL:
        return hit[1]
    try:
        data = await _api(client, f"{lang}.wikipedia.org", action="query", list="search", srsearch=query,
                          srlimit=1, srinfo="suggestion|totalhits", srprop="")
    except Exception:
        return None
    info = (data.get("query") or {}).get("searchinfo") or {}
    said = info.get("suggestion") or None
    # Wikipedia suggests things for almost anything; only trust it when the words as typed hardly exist
    if said and (said.lower() == query.strip().lower() or int(info.get("totalhits", 0)) > 8):
        said = None
    _cache[key] = (time.monotonic(), said)
    return said


def _when(snak):
    """A Wikidata time value -> (year, month, day), months and days 0 when only the year is known."""
    try:
        value = snak["datavalue"]["value"]
        m = re.match(r"([+-])(\d+)-(\d\d)-(\d\d)", value["time"])
        year = int(m.group(2)) * (-1 if m.group(1) == "-" else 1)
        precision = int(value.get("precision", 9))
        return year, int(m.group(3)) if precision >= 10 else 0, int(m.group(4)) if precision >= 11 else 0
    except (KeyError, TypeError, ValueError, AttributeError):
        return None


MONTH_NAMES = ["", "january", "february", "march", "april", "may", "june", "july", "august", "september",
               "october", "november", "december"]


def _say(when):
    year, month, day = when
    text = str(abs(year)) + (" BC" if year < 0 else "")
    if month:
        text = f"{MONTH_NAMES[month]} {text}"
        if day:
            text = f"{day} {text}"
    return text


def life_line(born, died, today=None):
    """{'born': '23 june 1912', 'died': ..., 'age': 41, 'from': 1912, 'to': 1954} for a person's timeline."""
    from datetime import date
    if not born:
        return None
    today = today or date.today()
    end = died or (today.year, today.month, today.day)
    age = end[0] - born[0] - (1 if (end[1], end[2]) < (born[1], born[2]) and born[1] and end[1] else 0)
    if not (0 <= age <= 130):
        return None
    return {"born": _say(born), "died": _say(died) if died else "", "age": age, "from": born[0],
            "to": died[0] if died else today.year}


async def life(client, qid):
    """When a person was born and died, from Wikidata. None for anything that is not a person."""
    try:
        r = await client.get("https://www.wikidata.org/w/api.php", headers=headers(), params={
            "action": "wbgetclaims", "entity": qid, "property": "P569", "format": "json"})
        r.raise_for_status()
        claims = (r.json().get("claims") or {}).get("P569") or []
        born = _when(claims[0]["mainsnak"]) if claims else None
        if not born:
            return None
        r = await client.get("https://www.wikidata.org/w/api.php", headers=headers(), params={
            "action": "wbgetclaims", "entity": qid, "property": "P570", "format": "json"})
        r.raise_for_status()
        gone = (r.json().get("claims") or {}).get("P570") or []
        return life_line(born, _when(gone[0]["mainsnak"]) if gone else None)
    except Exception:
        return None


async def lookup(client, query, lang="en"):
    """The card for a short query, remembered for an hour. None when Wikipedia has nothing fitting."""
    key = (lang, re.sub(r"\s+", " ", query.strip().lower()))
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < TTL:
        return hit[1]
    try:
        card = await asyncio.wait_for(find(client, query, lang), 6)
    except Exception:
        return None  # not remembered: try again next time
    if len(_cache) > 300:
        _cache.clear()
    _cache[key] = (time.monotonic(), card)
    return card
