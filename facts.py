"""Facts cards: `capital of peru`, `population of japan`, `germany facts`, and prices:
`aapl stock`, `apple stock`, `bitcoin price`.

Facts about places come from Wikidata (the data behind Wikipedia). Prices come from Yahoo
Finance's public chart service. Both are fetched by nook; only the name asked about is sent."""
import asyncio
import math
import re
import time

import wiki

PROPS = {"former capital": "P36", "former currency": "P38", "capital": "P36", "population": "P1082", "area": "P2046", "currency": "P38",
         "languages": "P37", "calling code": "P474"}
ASKED = {"population": "population", "capital": "capital", "area": "area", "size": "area",
         "currency": "currency", "language": "languages", "languages": "languages",
         "official language": "languages", "calling code": "calling code", "phone code": "calling code",
         "dialing code": "calling code", "dialling code": "calling code"}
FORMER = {"capital": "former capital", "capitals": "former capital", "currency": "former currency", "currencies": "former currency"}
_WHAT = "|".join(sorted(ASKED, key=len, reverse=True))
KEEP_FACTS, KEEP_PRICE = 6 * 3600, 120
_cache = {}


# --- what is being asked? ---------------------------------------------------

def _topic(text):
    t = re.sub(r"^(?:the )", "", re.sub(r"\s+", " ", text.strip()))
    return t if 1 <= len(t) <= 40 and len(t.split()) <= 4 and re.fullmatch(r"[^\W\d_][\w .'\-]*", t) else None


def parse_place(query):
    """-> (topic, what or None for 'everything') or None."""
    q = re.sub(r"\s+", " ", query.strip().lower()).rstrip("?")
    q = re.sub(r"^(?:what(?:'s| is| are| was| were) )?(?:the )?", "", q)
    old = r"(?:old|former|previous|historical|historic|past|earlier|first|original)"
    m = re.match(rf"^{old} (capitals?|currenc(?:y|ies)) (?:of|in|for) (.+)$", q) or         re.match(rf"^(capitals?|currenc(?:y|ies)) (?:of|in|for) (.+?) (?:in history|historically|in the past|through history)$", q)
    if m and _topic(m.group(2)):
        return _topic(m.group(2)), FORMER[m.group(1)]
    m = re.match(rf"^(.+?) {old} (capitals?|currenc(?:y|ies))$", q)
    if m and _topic(m.group(1)):
        return _topic(m.group(1)), FORMER[m.group(2)]
    m = re.match(rf"^({_WHAT}) (?:of|in|for) (.+)$", q)
    if m and _topic(m.group(2)):
        return _topic(m.group(2)), ASKED[m.group(1)]
    m = re.match(rf"^(.+?) ({_WHAT})$", q)
    if m and _topic(m.group(1)):
        return _topic(m.group(1)), ASKED[m.group(2)]
    m = re.match(r"^what languages? (?:is|are|do they|do people) (?:spoken|speak) in (.+)$", q)
    if m and _topic(m.group(1)):
        return _topic(m.group(1)), "languages"
    m = re.match(r"^(?:facts|info|information|stats) (?:about|on|for) (.+)$", q) or re.match(r"^(.+?) (?:facts|country facts|stats)$", q)
    if m and _topic(m.group(1)):
        return _topic(m.group(1)), None
    return None


def parse_price(query):
    """-> (name or ticker, needs a crypto result) or None."""
    q = re.sub(r"\s+", " ", query.strip().lower()).rstrip("?")
    m = re.match(r"^(?:stock|stocks|share|shares)(?: price)? (?:of |for )?(.+)$", q) or \
        re.match(r"^(.+?) (?:stock price|share price|stock|stocks|shares|ticker)$", q)
    if m and re.fullmatch(r"[a-z0-9][a-z0-9 .&'\-^=]{0,28}", m.group(1)):
        return m.group(1), False
    m = re.match(r"^(?:price of |current price of )?(.+?)(?: price)?$", q)
    if m and (q.startswith("price of ") or q.endswith(" price")) and re.fullmatch(r"[a-z][a-z0-9 .\-]{1,28}", m.group(1)):
        return m.group(1), True
    return None


def parse(query):
    return parse_place(query) or parse_price(query)


# --- numbers, said the way people say them -----------------------------------

def human(n):
    n = float(n)
    for size, word in ((1e12, "trillion"), (1e9, "billion"), (1e6, "million")):
        if abs(n) >= size:
            v = n / size
            return f"{v:.1f}".rstrip("0").rstrip(".") + f" {word}" if v < 100 else f"{v:.0f} {word}"
    return f"{n:,.0f}"


# --- places, from Wikidata ---------------------------------------------------

async def _raw(client, entity, prop, ended=False):
    """Wikidata statements for a property: the ones still true, or (ended) the ones that stopped being true."""
    r = await client.get("https://www.wikidata.org/w/api.php", headers=wiki.headers(), params={
        "action": "wbgetclaims", "entity": entity, "property": prop, "format": "json"})
    r.raise_for_status()
    found = (r.json().get("claims") or {}).get(prop, [])
    return [c for c in found if c.get("rank") != "deprecated" and ("P582" in (c.get("qualifiers") or {})) == ended]


def _year(statement, prop):
    try:
        return int(re.match(r"[+-]?(\d+)", statement["qualifiers"][prop][0]["datavalue"]["value"]["time"]).group(1))
    except (KeyError, IndexError, TypeError, ValueError):
        return None


def former_line(statements, labels):
    """'Bonn 1949-1999; Kyoto 794-1868': what used to be true, most recent first. A name that
    comes up twice (a capital and a seat of government) is merged into its widest span."""
    spans = {}
    for c in statements:
        try:
            name = labels.get(c["mainsnak"]["datavalue"]["value"]["id"], "")
        except (KeyError, TypeError):
            continue
        if not name:
            continue
        start, end = _year(c, "P580"), _year(c, "P582")
        old = spans.get(name)
        if old:
            start = min(x for x in (start, old[0]) if x) if (start or old[0]) else None
            end = max(x for x in (end, old[1]) if x) if (end or old[1]) else None
        spans[name] = (start, end)
    lines = sorted(spans.items(), key=lambda kv: -(kv[1][1] or 0))
    return "; ".join(f"{n} {s or '?'}-{e}" if (s or e) else n for n, (s, e) in lines[:6])


def _latest(statements):
    """The statement with the most recent 'point in time', else the preferred / last one."""
    def when(c):
        q = (c.get("qualifiers") or {}).get("P585") or []
        try:
            return q[0]["datavalue"]["value"]["time"]
        except (IndexError, KeyError, TypeError):
            return ""
    return max(statements, key=lambda c: (c.get("rank") == "preferred", when(c))) if statements else None


def _amount(statement):
    try:
        return float(statement["mainsnak"]["datavalue"]["value"]["amount"])
    except (KeyError, TypeError, ValueError):
        return None


async def _labels(client, ids):
    if not ids:
        return {}
    r = await client.get("https://www.wikidata.org/w/api.php", headers=wiki.headers(), params={
        "action": "wbgetentities", "ids": "|".join(ids[:20]), "props": "labels", "languages": "en", "languagefallback": 1, "format": "json"})
    r.raise_for_status()
    return {k: next((l.get("value", "") for l in (v.get("labels") or {}).values()), "")
            for k, v in (r.json().get("entities") or {}).items()}


def rows_from(raw, labels):
    """Turn Wikidata statements into the lines of the card."""
    rows = {}
    pop = _amount(_latest(raw.get("population") or []) or {})
    if pop:
        rows["population"] = human(pop)
    area = _latest(raw.get("area") or [])
    if area and "Q712226" in str(area["mainsnak"]["datavalue"]["value"].get("unit", "")) and _amount(area):
        rows["area"] = f"{_amount(area):,.0f} km²"
    for key in ("capital", "currency", "languages"):
        names = []
        for c in raw.get(key) or []:
            try:
                label = labels.get(c["mainsnak"]["datavalue"]["value"]["id"], "")
            except (KeyError, TypeError):
                continue
            if label and label not in names:
                names.append(label)
        if names:
            rows[key] = ", ".join(names[:4])
    codes = [c["mainsnak"]["datavalue"]["value"] for c in raw.get("calling code") or [] if (c.get("mainsnak") or {}).get("datavalue")]
    if codes:
        rows["calling code"] = ", ".join(codes[:2])
    return rows


async def place_facts(client, topic, what, lang="en"):
    card = await wiki.lookup(client, topic, lang)
    if not card or not card.get("qid"):
        return None
    if what in FORMER.values():
        ended = await _raw(client, card["qid"], PROPS[what], ended=True)
        ids = [c["mainsnak"]["datavalue"]["value"]["id"] for c in ended if (c.get("mainsnak") or {}).get("datavalue")]
        labels = await _labels(client, list(dict.fromkeys(ids)))
        line = former_line(ended, labels)
        if not line:
            return None
        return {"kind": "facts", "title": card["title"], "about": card["about"], "flag": card["flag"],
                "big": ("former currencies" if what.endswith("currency") else "former capitals", line),
                "rows": [], "url": card["url"], "source": "Wikidata"}
    wanted = [what] if what else [k for k in PROPS if not k.startswith("former")]
    statements = await asyncio.gather(*(_raw(client, card["qid"], PROPS[w]) for w in wanted), return_exceptions=True)
    raw = {w: s for w, s in zip(wanted, statements) if not isinstance(s, BaseException)}
    ids = []
    for key in ("capital", "currency", "languages"):
        for c in raw.get(key) or []:
            try:
                ids.append(c["mainsnak"]["datavalue"]["value"]["id"])
            except (KeyError, TypeError):
                pass
    try:
        labels = await _labels(client, list(dict.fromkeys(ids)))
    except Exception:
        labels = {}
    rows = rows_from(raw, labels)
    if not rows or (what and what not in rows):
        return None
    big = None
    if what:
        big = (what, rows.pop(what))
    return {"kind": "facts", "title": card["title"], "about": card["about"], "flag": card["flag"], "big": big,
            "rows": [(k, v) for k, v in rows.items()], "url": card["url"], "source": "Wikidata"}


# --- prices, from Yahoo Finance ------------------------------------------------

KINDS = {"EQUITY", "ETF", "INDEX", "CRYPTOCURRENCY", "MUTUALFUND"}


def pick_quote(data, term, crypto_only):
    for q in (data or {}).get("quotes", []):
        if q.get("quoteType") not in KINDS or (crypto_only and q.get("quoteType") != "CRYPTOCURRENCY"):
            continue
        name = f"{q.get('longname', '')} {q.get('shortname', '')} {q.get('symbol', '')}"
        if q.get("symbol", "").lower() == term.lower() or wiki.covers(term, name):
            return q
    return None


def spark(closes, w=300, h=56):
    lo, hi = min(closes), max(closes)
    span = (hi - lo) or 1
    step = w / max(len(closes) - 1, 1)
    return " ".join(f"{'L' if i else 'M'}{i * step:.1f} {h - (c - lo) / span * (h - 4) - 2:.1f}" for i, c in enumerate(closes))


def parse_chart(data, quote):
    try:
        result = data["chart"]["result"][0]
        meta = result["meta"]
        closes = [c for c in result["indicators"]["quote"][0]["close"] if c is not None]
        price = float(meta["regularMarketPrice"])
    except (KeyError, IndexError, TypeError, ValueError):
        return None
    if len(closes) < 5:
        return None
    before = closes[-2] if len(closes) >= 2 and abs(closes[-1] - price) <= max(0.01, price * 1e-4) else closes[-1]
    diff = price - before
    pct = diff / before * 100 if before else 0
    return {"kind": "stock", "name": quote.get("longname") or quote.get("shortname") or meta.get("symbol", ""),
            "symbol": meta.get("symbol", ""), "price": f"{price:,.2f}", "currency": meta.get("currency", ""),
            "change": f"{diff:+,.2f} ({pct:+.2f}%)", "up": diff >= 0, "spark": spark(closes + ([price] if closes[-1] != price else [])),
            "note": "last three months · from Yahoo Finance, can be a little late · not advice"}


async def price(client, term, crypto_only):
    key = ("price", term, crypto_only)
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < KEEP_PRICE:
        return hit[1]
    try:
        r = await client.get("https://query1.finance.yahoo.com/v1/finance/search",
                             params={"q": term, "quotesCount": 6, "newsCount": 0})
        r.raise_for_status()
        quote = pick_quote(r.json(), term, crypto_only)
        if not quote:
            card = None
        else:
            c = await client.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{quote['symbol']}",
                                 params={"range": "3mo", "interval": "1d"})
            c.raise_for_status()
            card = parse_chart(c.json(), quote)
    except Exception:
        return None
    if len(_cache) > 300:
        _cache.clear()
    _cache[key] = (time.monotonic(), card)
    return card


async def lookup(client, query, lang="en"):
    place = parse_place(query)
    if place:
        key = ("place", place, lang)
        hit = _cache.get(key)
        if hit and time.monotonic() - hit[0] < KEEP_FACTS:
            return hit[1]
        try:
            card = await place_facts(client, *place, lang=lang)
        except Exception:
            return None
        if len(_cache) > 300:
            _cache.clear()
        _cache[key] = (time.monotonic(), card)
        if card:
            return card
    quote = parse_price(query)
    if quote:
        return await price(client, *quote)
    return None
