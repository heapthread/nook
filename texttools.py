"""Small things done to text: `word count ...`, `uppercase ...`, `reverse ...`, `slugify ...`, and
`choose between pizza, pasta or soup`. Worked out here; nothing is sent anywhere."""
import random
import re
import unicodedata

import devtools

MAX = 5000


def _slug(text):
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def counts(text, letters=False):
    words, lines = len(text.split()), len(text.splitlines()) or 1
    chars = f"{len(text):,} character{'' if len(text) == 1 else 's'}"
    more = f"{words} word{'' if words == 1 else 's'}"
    return {"kind": "fact", "big": chars if letters else more,
            "small": (f"{more} · " if letters else f"{chars} ({len(text.replace(' ', '')):,} without spaces) · ")
                     + f"{lines} line{'' if lines == 1 else 's'}"}


def choose(options):
    return {"kind": "dice", "big": random.choice(options), "small": "picked from " + ", ".join(options)}


def answer(query):
    q = re.sub(r"\s+", " ", query.strip())
    if not q or len(q) > MAX:
        return None
    m = re.match(r"^(?:word count|count words|how many words)(?: of| in)?:? (.+)$", q, re.I)
    if m:
        return counts(m.group(1).strip("\"'“”"))
    m = re.match(r"^(?:character count|char count|letter count|count characters|how many characters|how many letters)(?: of| in)?:? (.+)$", q, re.I)
    if m:
        return counts(m.group(1).strip("\"'“”"), letters=True)
    m = re.match(r"^(upper ?case|lower ?case|title case|capitali[sz]e|reverse|slugify|slug)(?: of)?:? (.+)$", q, re.I)
    if m:
        how, text = re.sub(r"\s", "", m.group(1).lower()), m.group(2).strip("\"'“”")
        value = {"uppercase": text.upper(), "lowercase": text.lower(), "titlecase": text.title(),
                 "capitalize": text.capitalize(), "capitalise": text.capitalize(), "reverse": text[::-1],
                 "slugify": _slug(text), "slug": _slug(text)}[how]
        return devtools.tool(how.replace("case", " case"), value)
    m = re.match(r"^(?:choose|pick|decide|select)(?: for me)?(?: between| from| one of)? (.+)$", q, re.I) or \
        re.match(r"^should i (.+ or .+)$", q, re.I)
    if m:
        options = [o.strip(" ?.\"'") for o in re.split(r",\s*(?:or\s+)?|\s+or\s+", m.group(1)) if o.strip(" ?.\"'")]
        if 2 <= len(options) <= 12 and all(len(o) <= 60 for o in options):
            return choose(options)
    return None
