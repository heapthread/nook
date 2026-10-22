"""The boxes above the results: a definition, a short summary of a topic, a currency conversion,
the time somewhere, dice, a coin, a timer. Anything that needs the outside world is fetched by
nook (never by the visitor's browser) and remembered for a while."""
import asyncio
import random
import re
import time
from datetime import datetime, timezone
from urllib.parse import quote

from selectolax.lexbor import LexborHTMLParser

import dates
import devtools
import earth
import facts
import figures
import history
import places
import nearby
import netinfo
import packages
import plot
import routes
import texttools
import translate
import weather
import wiki
import wordtools

AHD = "https://www.ahdictionary.com"
CAMBRIDGE = "https://dictionary.cambridge.org"
TTL = 3600
_cache = {}  # (kind, key) -> (when, card or None)

POS = {"n.": "noun", "v.": "verb", "adj.": "adjective", "adv.": "adverb", "pron.": "pronoun",
       "prep.": "preposition", "conj.": "conjunction", "interj.": "interjection",
       "tr.v.": "transitive verb", "intr.v.": "intransitive verb", "abbr.": "abbreviation",
       "pref.": "prefix", "suff.": "suffix", "aux.v.": "auxiliary verb", "pl.n.": "plural noun",
       "art.": "article", "det.": "determiner"}


# --- what is this query asking for? ----------------------------------------

_WORD = r"([a-zA-Z][a-zA-Z'\-]{1,29})"
_DEFINE = [
    rf"^(?:define|definition of|meaning of|the meaning of|what(?:'s| is) the meaning of|what(?:'s| is) the definition of)\s+{_WORD}\??$",
    rf"^{_WORD}\s+(?:meaning|definition|definitions|define|means|synonym|synonyms)\??$",
    rf"^what (?:does|is) {_WORD} mean\??$",
    rf"^what does the word {_WORD} mean\??$",
]
_UNITS = {"s": 1, "sec": 1, "secs": 1, "second": 1, "seconds": 1, "m": 60, "min": 60, "mins": 60,
          "minute": 60, "minutes": 60, "h": 3600, "hr": 3600, "hrs": 3600, "hour": 3600, "hours": 3600}
_AMOUNT = r"(\d+(?:\.\d+)?)\s*(s|secs?|seconds?|m|mins?|minutes?|h|hrs?|hours?)"
CURRENCIES = set("AUD BGN BRL CAD CHF CNY CZK DKK EUR GBP HKD HUF IDR ILS INR ISK JPY KRW MXN MYR NOK "
                 "NZD PHP PLN RON SEK SGD THB TRY USD ZAR".split())


def define_word(query):
    q = query.strip().lower()
    for pattern in _DEFINE:
        m = re.match(pattern, q)
        if m:
            return m.group(1)
    return None


def _timer_seconds(q):
    m = re.match(rf"^(?:set (?:a |an )?)?(?:timer|countdown)(?: for| of)?\s+{_AMOUNT}$", q) \
        or re.match(rf"^{_AMOUNT}\s+(?:timer|countdown)$", q)
    if not m:
        return None
    seconds = int(float(m.group(1)) * _UNITS[m.group(2)])
    return seconds if 1 <= seconds <= 86400 else None


def _currency(q):
    m = re.match(r"^\$?\s*([\d,]*\.?\d+)?\s*([a-z]{3})\s+(?:in|to|into|as)\s+([a-z]{3})$", q)
    if not m:
        return None
    amount = float((m.group(1) or "1").replace(",", ""))
    a, b = m.group(2).upper(), m.group(3).upper()
    return (amount, a, b) if a in CURRENCIES and b in CURRENCIES and a != b else None


def topic_of(query):
    """A short, plain query that might be a person, place or thing worth a summary."""
    q = re.sub(r"\s+", " ", query.strip().lower()).rstrip("?")
    q = re.sub(r"^(?:who|what) (?:is|was|are|were) (?:an? |the )?", "", q)
    if not (2 < len(q) <= 40) or not re.fullmatch(r"[a-z0-9][a-z0-9 .'\-]*", q) or len(q.split()) > 4:
        return None
    return q


# --- cards that need no outside help ---------------------------------------

def local(query, now=None):
    """Cards worked out here and now, so they are never remembered: time, dice, coin, timer."""
    q = re.sub(r"\s+", " ", query.strip().lower()).rstrip("?")
    seconds = _timer_seconds(q)
    if seconds:
        return {"kind": "timer", "seconds": seconds}
    site = re.fullmatch(r"(?:https?://)?(?:www\.)?((?:[a-z0-9][a-z0-9-]*\.)+(?:com|org|net|io|dev|app|ai|co|uk|de|fr|nl|eu|info|me|tv|gg|xyz|edu|gov|ch|at|se|no|dk|fi|es|it|ru|jp|cn|in|br|ca|au|nz|wiki|news|blog|tech|cloud))(/\S*)?", q)
    if site:
        return {"kind": "jump", "host": site.group(1), "url": f"https://{site.group(1)}{site.group(2) or ''}"}
    if q in ("pomodoro", "pomodoro timer", "start pomodoro"):
        return {"kind": "timer", "seconds": 25 * 60}
    if q in ("stopwatch", "online stopwatch", "start stopwatch", "stop watch"):
        return {"kind": "stopwatch"}
    if re.match(r"^(?:flip|toss) a coin$|^coin (?:flip|toss)$|^heads or tails$", q):
        return {"kind": "dice", "big": random.choice(["heads", "tails"]), "small": "a coin flip"}
    m = re.match(r"^(?:roll|throw) (?:a |an )?(?:(\d{0,2})d(\d{1,4})|di[ce]e?)$", q)
    if m:
        count, sides = (int(m.group(1) or 1), int(m.group(2))) if m.group(2) else (1, 6)
        if count >= 1 and sides >= 2:
            rolls = [random.randint(1, sides) for _ in range(count)]
            small = f"{count}d{sides}" + (f"  ({' + '.join(map(str, rolls))})" if count > 1 else "")
            return {"kind": "dice", "big": str(sum(rolls)), "small": small}
    m = re.match(r"^random(?: number)?(?: between| from)? (-?\d+)\s*(?:-|to|and)\s*(-?\d+)$", q)
    if m:
        lo, hi = sorted((int(m.group(1)), int(m.group(2))))
        if hi - lo < 10 ** 12:
            return {"kind": "dice", "big": str(random.randint(lo, hi)), "small": f"a number from {lo} to {hi}"}
    return (plot.answer(query) or figures.answer(query) or netinfo.local(query) or texttools.answer(query) or dates.answer(query, now=now)
            or devtools.answer(query, now) or places.answer(query, now))


# --- dictionary pages ------------------------------------------------------

def _clean(text):
    return re.sub(r"\s+", " ", text or "").strip()


def _quoted(text):
    """An example sentence in curly quotes (quotations that already have quotes keep theirs)."""
    text = _clean(text)
    if not text:
        return ""
    if '"' in text:
        return re.sub(r'"([^"]*)"', r"“\1”", text)
    return f"“{text}”"


def _ahd_sense(node):
    """One numbered definition: its wording and its example. Sub-senses are read separately."""
    words, examples = [], []
    for child in node.iter(include_text=True):
        tag = child.tag
        if tag == "-text":
            words.append(child.text_content or "")
        elif tag == "span" or tag == "i":
            words.append(child.text(deep=True))
        elif tag == "font" and child.css_first("i"):
            examples.append(_clean(child.text(deep=True)))  # a quotation, then maybe who said it
    return {"text": _clean("".join(words)).rstrip(":").strip(),
            "example": _quoted(" ".join(examples)), "subs": []}


def parse_ahd(html):
    """American Heritage Dictionary: headword, respelled pronunciation, senses, origin."""
    out = {"respelling": "", "audio": "", "entries": [], "origin": ""}
    for td in LexborHTMLParser(html).css("div#results td"):
        head = td.css_first("div.rtseg")
        if head is None:
            continue
        if not out["respelling"]:
            raw = _clean(re.sub(r"Share:.*", "", head.text(deep=True)))
            m = re.search(r"\(([^)]+)\)", raw)
            out["respelling"] = m.group(1) if m else ""
            wav = head.css_first("a[href$='.wav']")
            out["audio"] = AHD + wav.attributes["href"] if wav is not None else ""
        for pseg in td.css("div.pseg"):
            pos_node = pseg.css_first("i")
            pos = _clean(pos_node.text()) if pos_node is not None else ""
            senses = []
            for ds in pseg.iter():
                if ds.tag != "div" or "ds-list" not in (ds.attributes.get("class") or "").split():
                    continue
                subs = [_ahd_sense(s) for s in ds.css("div.sds-list")]
                sense = _ahd_sense(ds)
                sense["subs"] = subs
                if sense["text"] or subs:
                    senses.append(sense)
            if senses:
                out["entries"].append({"pos": POS.get(pos, pos.rstrip(".")), "senses": senses})
        if not out["origin"]:
            ety = td.css_first("div.etyseg")
            if ety is not None:
                text = _clean(ety.text(deep=True)).strip("[]")
                out["origin"] = re.split(r";\s*see\b", text)[0].rstrip(".") + "."
    return out


def parse_cambridge(html):
    """Cambridge Dictionary: IPA, audio and senses."""
    out = {"ipa": "", "audio": "", "entries": []}
    tree = LexborHTMLParser(html)
    best = None
    for pron in tree.css("span.dpron-i"):
        region = pron.css_first("span.region")
        ipa = pron.css_first("span.ipa")
        src = pron.css_first("source[type='audio/mpeg']")
        if ipa is None:
            continue
        found = (_clean(ipa.text(deep=True)).replace(".", ""),
                 CAMBRIDGE + src.attributes["src"] if src is not None else "")
        if best is None or (region is not None and region.text(strip=True) == "us"):
            best = found
    if best:
        out["ipa"], out["audio"] = best
    for body in tree.css("div.entry-body__el"):
        pos = body.css_first("span.pos")
        senses = []
        for block in body.css("div.def-block"):
            d = block.css_first("div.def")
            if d is None:
                continue
            eg = block.css_first("div.examp span.eg")
            senses.append({"text": _clean(d.text(deep=True)).rstrip(":").strip(),
                           "example": _quoted(eg.text(deep=True)) if eg is not None else "", "subs": []})
        if senses:
            out["entries"].append({"pos": pos.text(strip=True) if pos is not None else "", "senses": senses})
    return out


def parse_datamuse(words_json, word):
    """Similar words: single words only, never the word itself."""
    import json
    try:
        data = json.loads(words_json)
    except ValueError:
        return []
    return [d["word"] for d in data if " " not in d["word"] and d["word"].lower() != word][:6]


def parse_datamuse_defs(words_json):
    import json
    try:
        data = json.loads(words_json)
    except ValueError:
        return []
    groups = {}
    for item in data[:1]:
        for d in item.get("defs", []):
            pos, _, text = d.partition("\t")
            groups.setdefault({"n": "noun", "v": "verb", "adj": "adjective", "adv": "adverb"}.get(pos, pos), []).append(
                {"text": _clean(text), "example": "", "subs": []})
    return [{"pos": p, "senses": s} for p, s in groups.items()]


def build_definition(word, ahd=None, cambridge=None, similar=(), fallback=()):
    entries = (ahd or {}).get("entries") or (cambridge or {}).get("entries") or list(fallback)
    if not entries:
        return None
    sources = []
    if (ahd or {}).get("entries"):
        sources.append(("American Heritage Dictionary", f"{AHD}/word/search.html?q={quote(word)}"))
    elif (cambridge or {}).get("entries"):
        sources.append(("Cambridge Dictionary", f"{CAMBRIDGE}/dictionary/english/{quote(word)}"))
    else:
        sources.append(("WordNet, via Datamuse", f"https://www.onelook.com/?w={quote(word)}"))
    cam, a = cambridge or {}, ahd or {}
    return {
        "kind": "define", "word": word,
        "phonetic": f"/{cam['ipa']}/" if cam.get("ipa") else (f"({a['respelling']})" if a.get("respelling") else ""),
        "audio": cam.get("audio") or a.get("audio") or "",
        "entries": entries[:3], "origin": a.get("origin", ""), "similar": list(similar),
        "source": {"name": sources[0][0], "url": sources[0][1]},
    }


# --- fetching --------------------------------------------------------------

def _remembered(kind, key):
    hit = _cache.get((kind, key))
    return hit if hit and time.monotonic() - hit[0] < TTL else None


def _remember(kind, key, card):
    if len(_cache) > 300:
        _cache.clear()
    _cache[(kind, key)] = (time.monotonic(), card)
    return card


async def _get(client, url, **kw):
    r = await client.get(url, **kw)
    r.raise_for_status()
    return r


async def define(client, word):
    hit = _remembered("define", word)
    if hit:
        return hit[1]
    jobs = await asyncio.gather(
        _get(client, f"{AHD}/word/search.html", params={"q": word}),
        _get(client, f"{CAMBRIDGE}/dictionary/english/{quote(word)}"),
        _get(client, "https://api.datamuse.com/words", params={"rel_syn": word, "max": 10}),
        _get(client, "https://api.datamuse.com/words", params={"sp": word, "md": "d", "max": 1}),
        return_exceptions=True)
    ok = [None if isinstance(j, BaseException) else j for j in jobs]
    ahd = parse_ahd(ok[0].text) if ok[0] is not None else None
    cam = parse_cambridge(ok[1].text) if ok[1] is not None else None
    similar = parse_datamuse(ok[2].text, word) if ok[2] is not None else []
    fallback = parse_datamuse_defs(ok[3].text) if ok[3] is not None else []
    return _remember("define", word, build_definition(word, ahd, cam, similar, fallback))


def parse_knowledge(raw, query):
    """DuckDuckGo's instant answer: a short summary (it comes from Wikipedia) and a picture."""
    import json
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    heading, text = (data.get("Heading") or "").strip(), (data.get("AbstractText") or "").strip()
    if data.get("Type") != "A" or not heading or len(text) < 60:
        return None
    wanted = set(re.findall(r"[a-z0-9]+", query.lower()))
    if not wanted <= set(re.findall(r"[a-z0-9]+", heading.lower())):
        return None  # it found something, but not what was asked about
    if len(text) > 520:  # end on a whole sentence
        cut = text[:520]
        text = cut[:cut.rfind(". ") + 1] if ". " in cut else cut.rstrip() + "..."
    image = data.get("Image") or ""
    return {"kind": "knowledge", "title": heading, "text": text,
            "image": ("https://duckduckgo.com" + image) if image.startswith("/") else image,
            "source": {"name": data.get("AbstractSource") or "Wikipedia", "url": data.get("AbstractURL") or ""},
            "about": data.get("Entity") or ""}


async def knowledge(client, topic):
    hit = _remembered("knowledge", topic)
    if hit:
        return hit[1]
    try:
        r = await _get(client, "https://api.duckduckgo.com/", params={
            "q": topic, "format": "json", "no_html": 1, "skip_disambig": 1})
        card = parse_knowledge(r.text, topic)
    except Exception:
        return None  # not remembered: try again next time
    return _remember("knowledge", topic, card)


def parse_currency(raw, amount, a, b):
    import json
    try:
        data = json.loads(raw)
        value = data["rates"][b]
        return {"kind": "currency", "line": f"{amount:,.2f} {a} = {value:,.2f} {b}".replace(".00 ", " "),
                "note": f"rates from the European Central Bank, {data['date']}"}
    except (ValueError, KeyError, TypeError):
        return None


async def currency(client, amount, a, b):
    key = (amount, a, b)
    hit = _remembered("currency", key)
    if hit:
        return hit[1]
    try:
        r = await _get(client, "https://api.frankfurter.dev/v1/latest", params={"amount": amount, "from": a, "to": b})
        card = parse_currency(r.text, amount, a, b)
    except Exception:
        return None
    return _remember("currency", key, card)


async def lookup(client, query, with_knowledge=True, lang="en"):
    """The card (if any) that needs the outside world. Returns None quickly for most queries.

    A short plain query is looked up in Wikipedia first (in `lang`); DuckDuckGo's instant answer
    is the fallback, and only while that engine is on (`with_knowledge`)."""
    names = places.unknown_places(query)
    if names:  # a time question about a place nook doesn't know yet: find out, then local() can answer
        await places.learn(client, names)
        return None
    word = define_word(query)
    if word:
        return await define(client, word)
    spot = weather.place_in(query)
    if spot:
        return await weather.lookup(client, spot)
    if wordtools.parse(query):
        return await wordtools.lookup(client, query)
    q = re.sub(r"\s+", " ", query.strip().lower())
    swap = _currency(q)
    if swap:
        return await currency(client, *swap)
    said = await translate.lookup(client, query)
    if said:
        return said
    for module in (routes, earth, history, packages, netinfo, nearby):
        card = await module.lookup(client, query)
        if card:
            return card
    if facts.parse(query):
        card = await facts.lookup(client, query, lang)
        if card:
            return card
    topic = topic_of(query)
    if topic:
        card = await wiki.lookup(client, topic, lang)
        if card:
            return card
        if with_knowledge:
            return await knowledge(client, topic)
    return None
