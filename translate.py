"""`hello in german`, `translate good night to japanese`, `how do you say thank you in spanish`.

The phrase goes to MyMemory's free translation service (no key, no account), fetched by nook.
Only the phrase is sent, and only when the query really asks for a translation."""
import html
import re
import time
from urllib.parse import quote

LANGS = {
    "english": "en", "german": "de", "french": "fr", "spanish": "es", "italian": "it", "portuguese": "pt",
    "dutch": "nl", "polish": "pl", "russian": "ru", "ukrainian": "uk", "czech": "cs", "slovak": "sk",
    "swedish": "sv", "norwegian": "no", "danish": "da", "finnish": "fi", "greek": "el", "turkish": "tr",
    "arabic": "ar", "hebrew": "he", "hindi": "hi", "bengali": "bn", "urdu": "ur", "persian": "fa",
    "chinese": "zh-CN", "japanese": "ja", "korean": "ko", "vietnamese": "vi", "thai": "th",
    "indonesian": "id", "malay": "ms", "hungarian": "hu", "romanian": "ro", "bulgarian": "bg",
    "croatian": "hr", "serbian": "sr", "slovenian": "sl", "latvian": "lv", "lithuanian": "lt",
    "estonian": "et", "icelandic": "is", "irish": "ga", "welsh": "cy", "latin": "la", "swahili": "sw",
    "afrikaans": "af", "catalan": "ca", "esperanto": "eo", "amharic": "am", "tagalog": "tl",
}
NAMES = {v.lower(): k for k, v in LANGS.items()}
URL = "https://api.mymemory.translated.net/get"
KEEP = 3600
_cache = {}

NOT_A_PHRASE = re.compile(r"^(?:\d|time\b|weather\b|sunrise\b|sunset\b|moon\b|date\b|day\b|days\b|timer\b|what time\b)", re.I)


def _lang(word):
    return LANGS.get(word.strip().lower())


def parse(query):
    """-> (phrase, source code or None, target code) or None."""
    q = re.sub(r"\s+", " ", query.strip()).rstrip("?.!")
    m = re.match(r"^translate (.+?)(?: from (\w+))? (?:to|into|in) (\w+)$", q, re.I)
    if m and _lang(m.group(3)) and (not m.group(2) or _lang(m.group(2))):
        return _clean(m.group(1)), _lang(m.group(2)) if m.group(2) else None, _lang(m.group(3))
    m = re.match(r"^(?:how (?:do you|to|would you|can i|do i) say|what(?:'s| is)(?: the word for)?) (.+?) in (\w+)$", q, re.I)
    if m and _lang(m.group(2)):
        return _clean(m.group(1)), None, _lang(m.group(2))
    m = re.match(r"^(.+?) (?:in|to) (\w+)(?: translation)?$", q, re.I)
    if m and _lang(m.group(2)) and not NOT_A_PHRASE.match(m.group(1)) and len(m.group(1).split()) <= 30 and len(m.group(1)) <= 200:
        return _clean(m.group(1)), None, _lang(m.group(2))
    return None


def _clean(text):
    text = text.strip()
    if len(text) > 2 and text[0] in "\"'“" and text[-1] in "\"'”":
        text = text[1:-1]
    return text.strip()[:200]


def parse_answer(data, phrase, target):
    try:
        status = int(data.get("responseStatus", 0))
        text = html.unescape(data["responseData"]["translatedText"]).strip()
    except (KeyError, TypeError, ValueError, AttributeError):
        return None
    if status != 200 or not text or "MYMEMORY WARNING" in text.upper():
        return None
    seen = str((data.get("responseData") or {}).get("detectedLanguage") or "").lower()
    if seen and seen.split("-")[0] == target.lower().split("-")[0]:
        return None   # it was already in that language, so there is nothing to translate
    return {"kind": "translate", "original": phrase, "result": text,
            "from": NAMES.get(seen.split("-")[0], NAMES.get(seen, "")),
            "to": NAMES.get(target.lower(), target)}


async def lookup(client, query):
    parsed = parse(query)
    if not parsed:
        return None
    phrase, source, target = parsed
    key = (phrase.lower(), source, target)
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < KEEP:
        return hit[1]
    try:
        r = await client.get(URL, params={"q": phrase, "langpair": f"{source or 'autodetect'}|{target}"})
        r.raise_for_status()
        card = parse_answer(r.json(), phrase, target)
    except Exception:
        return None
    if card and source:
        card["from"] = NAMES.get(source.lower(), source)
    if len(_cache) > 300:
        _cache.clear()
    _cache[key] = (time.monotonic(), card)
    return card
