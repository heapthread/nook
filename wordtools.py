"""Word questions answered from Datamuse (free, no key): rhymes, synonyms, antonyms, words that
start or end a certain way. Fetched by nook, remembered for an hour."""
import re
import time

API = "https://api.datamuse.com/words"
KEEP = 3600
_cache = {}  # (kind, word) -> (when, card)

_W = r"([a-z][a-z'\-]{1,24})"
RULES = [  # (pattern, Datamuse parameter, title)
    (rf"^(?:what )?(?:words? that )?rhymes? with {_W}$", "rel_rhy", "rhymes with {w}"),
    (rf"^{_W} rhymes$", "rel_rhy", "rhymes with {w}"),
    (rf"^(?:synonyms?|another word|other words|words?) (?:for|meaning|like) {_W}$", "rel_syn", "words like {w}"),
    (rf"^antonyms? (?:for|of) {_W}$", "rel_ant", "opposites of {w}"),
    (rf"^(?:opposite of|opposites? of|opposite) {_W}$", "rel_ant", "opposites of {w}"),
    (rf"^(?:adjectives?|words?) (?:to describe|for describing) {_W}$", "rel_jjb", "words to describe {w}"),
    (rf"^words? (?:that |which )?(?:related to|associated with) {_W}$", "ml", "words related to {w}"),
    (rf"^words? (?:that |which )?(?:start|begin)(?:s|ing|ning)? with {_W}$", "sp_prefix", "words starting with {w}"),
    (rf"^words? (?:that |which )?end(?:s|ing)? (?:in|with) {_W}$", "sp_suffix", "words ending in {w}"),
    (rf"^words? (?:that |which )?contain(?:s|ing)? {_W}$", "sp_inside", "words containing {w}"),
]


def parse(query):
    """-> (datamuse parameter, the word, a title) or None."""
    q = re.sub(r"\s+", " ", query.strip().lower()).rstrip("?")
    for pattern, param, title in RULES:
        m = re.match(pattern, q)
        if m:
            return param, m.group(1), title.format(w=m.group(1))
    return None


def params_for(param, word):
    if param == "sp_prefix":
        return {"sp": f"{word}*"}
    if param == "sp_suffix":
        return {"sp": f"*{word}"}
    if param == "sp_inside":
        return {"sp": f"*{word}*"}
    return {param: word}


def parse_words(raw, word, limit=40):
    import json
    try:
        data = json.loads(raw)
    except ValueError:
        return []
    seen, out = set(), []
    for item in data:
        w = item.get("word", "")
        if w and w.lower() != word and w not in seen and re.fullmatch(r"[A-Za-z][A-Za-z'\- ]*", w):
            seen.add(w)
            out.append(w)
    return out[:limit]


async def lookup(client, query):
    found = parse(query)
    if not found:
        return None
    param, word, title = found
    hit = _cache.get((param, word))
    if hit and time.monotonic() - hit[0] < KEEP:
        return hit[1]
    try:
        r = await client.get(API, params={**params_for(param, word), "max": 60})
        r.raise_for_status()
        words = parse_words(r.text, word)
    except Exception:
        return None
    card = {"kind": "words", "title": title, "words": words, "credit": "words: datamuse.com"} if words else None
    if len(_cache) > 300:
        _cache.clear()
    _cache[(param, word)] = (time.monotonic(), card)
    return card
