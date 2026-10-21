"""Small tools worked out right here: uuid, passwords, hashes, base64, url encoding, colours,
unix time, lorem ipsum. Nothing leaves the machine."""
import base64
import colorsys
import hashlib
import random
import re
import secrets
import string
import uuid
from datetime import datetime, timezone
from urllib.parse import quote, unquote

HASHES = ("md5", "sha1", "sha224", "sha256", "sha384", "sha512")
LOREM = ("lorem ipsum dolor sit amet consectetur adipiscing elit sed do eiusmod tempor incididunt ut labore et "
         "dolore magna aliqua enim ad minim veniam quis nostrud exercitation ullamco laboris nisi aliquip ex ea "
         "commodo consequat duis aute irure in reprehenderit voluptate velit esse cillum fugiat nulla pariatur "
         "excepteur sint occaecat cupidatat non proident sunt culpa qui officia deserunt mollit anim id est laborum").split()
MAX_TEXT = 2000


def tool(label, value, again=False, note=""):
    return {"kind": "tool", "label": label, "value": value, "again": again, "note": note}


def _clip(text):
    return text if len(text) <= 60 else text[:57] + "..."


def password(length):
    pool = string.ascii_letters + string.digits + "!@#$%^&*-_+=?"
    while True:
        text = "".join(secrets.choice(pool) for _ in range(length))
        if any(c.islower() for c in text) and any(c.isupper() for c in text) and any(c.isdigit() for c in text) \
                and any(c in "!@#$%^&*-_+=?" for c in text):
            return text


def lorem(count, unit):
    rng = random.Random()
    def sentence():
        words = [rng.choice(LOREM) for _ in range(rng.randint(8, 16))]
        return " ".join(words).capitalize() + "."
    if unit.startswith("word"):
        words = LOREM[:]
        out = [words[i % len(words)] for i in range(count)]
        return " ".join(out).capitalize() + "."
    if unit.startswith("sentence"):
        return " ".join(sentence() for _ in range(count))
    return "\n\n".join(" ".join(sentence() for _ in range(rng.randint(3, 5))) for _ in range(count))


# --- colours ---------------------------------------------------------------------

def _colour(r, g, b):
    h, l, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
    return {"kind": "colour", "hex": f"#{r:02x}{g:02x}{b:02x}", "rgb": f"rgb({r}, {g}, {b})",
            "hsl": f"hsl({round(h * 360)}, {round(s * 100)}%, {round(l * 100)}%)"}


def colour(q):
    m = re.fullmatch(r"(?:colou?r )?#([0-9a-f]{6}|[0-9a-f]{3})(?: (?:to|in|as) (?:rgb|hsl|hex))?", q)
    if m:
        h = m.group(1)
        h = "".join(c * 2 for c in h) if len(h) == 3 else h
        return _colour(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    m = re.fullmatch(r"(?:colou?r )?rgb\(?\s*(\d{1,3})[ ,]+(\d{1,3})[ ,]+(\d{1,3})\s*\)?(?: (?:to|in|as) (?:hex|hsl))?", q)
    if m and all(int(x) <= 255 for x in m.groups()):
        return _colour(*map(int, m.groups()))
    m = re.fullmatch(r"(?:colou?r )?hsl\(?\s*(\d{1,3})[ ,]+(\d{1,3})%?[ ,]+(\d{1,3})%?\s*\)?(?: (?:to|in|as) (?:hex|rgb))?", q)
    if m and int(m.group(1)) <= 360 and int(m.group(2)) <= 100 and int(m.group(3)) <= 100:
        r, g, b = colorsys.hls_to_rgb(int(m.group(1)) / 360, int(m.group(3)) / 100, int(m.group(2)) / 100)
        return _colour(round(r * 255), round(g * 255), round(b * 255))
    return None


# --- the questions -----------------------------------------------------------------

def answer(query, now=None):
    original = re.sub(r"\s+", " ", query.strip())
    q = original.lower().rstrip("?")
    if re.fullmatch(r"(?:(?:generate|new|random|make) )?(?:a )?uuid(?:4| v4)?(?: generator)?", q):
        return tool("a random uuid", str(uuid.uuid4()), again=True)
    m = re.fullmatch(r"(?:(?:generate|new|random|make|strong) )*(?:a )?password(?: generator)?(?: (?:of )?(\d{1,2})(?: characters| chars)?)?", q) \
        or re.fullmatch(r"(?:(?:generate|new|random|make) )?(\d{1,2})(?: character| char)? password", q)
    if m:
        length = int(m.group(1) or 20)
        if 8 <= length <= 64:
            return tool(f"a random password, {length} characters", password(length), again=True)
    names = "|".join(HASHES)
    m = re.fullmatch(rf"({names})(?: hash)? (?:of|for) (.+)", original, re.I)         or re.fullmatch(rf"hash ({names}) (.+)", original, re.I)         or re.fullmatch(rf'({names}) "(.+)"', original, re.I)   # a bare "sha256 hashing" is a topic, not a request
    if m and len(m.group(2)) <= MAX_TEXT:
        text = m.group(2)
        return tool(f"{m.group(1).lower()} of “{_clip(text)}”", hashlib.new(m.group(1).lower(), text.encode()).hexdigest())
    m = re.fullmatch(r"(?:base64|b64) (encode|decode) (.+)", original, re.I)
    if m and len(m.group(2)) <= MAX_TEXT:
        text, action = m.group(2), m.group(1).lower()
        if action == "encode":
            return tool(f"base64 of “{_clip(text)}”", base64.b64encode(text.encode()).decode())
        try:
            decoded = base64.b64decode(text + "=" * (-len(text) % 4), validate=True).decode("utf-8")
        except Exception:
            return None
        return tool(f"base64 decoded from “{_clip(text)}”", decoded)
    m = re.fullmatch(r"url (encode|decode) (.+)", original, re.I)
    if m and len(m.group(2)) <= MAX_TEXT:
        text = m.group(2)
        if m.group(1).lower() == "encode":
            return tool(f"url encoding of “{_clip(text)}”", quote(text, safe=""))
        return tool(f"url decoding of “{_clip(text)}”", unquote(text))
    found = colour(q)
    if found:
        return found
    m = re.fullmatch(r"(?:epoch|unix(?: time| timestamp)?|timestamp)(?: to (?:date|time))?(?: to)? (\d{9,13})", q) \
        or re.fullmatch(r"(?:epoch|unix(?: time| timestamp)?)(?: to date)? (\d{9,13})", q)
    if m:
        stamp = int(m.group(1))
        seconds = stamp / 1000 if len(m.group(1)) >= 12 else stamp
        try:
            when = datetime.fromtimestamp(seconds, timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
        return tool(f"unix time {stamp}", when.strftime("%A %d %B %Y, %H:%M:%S UTC").lower(),
                    note="in milliseconds" if len(m.group(1)) >= 12 else "")
    if re.fullmatch(r"(?:epoch|unix time|unix timestamp|current epoch|epoch now|current unix time)", q):
        now = now or datetime.now(timezone.utc)
        return tool("unix time now", str(int(now.timestamp())), again=True)
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})(?:[ t](\d{2}):(\d{2})(?::(\d{2}))?)? to (?:epoch|unix(?: time)?|timestamp)", q)
    if m:
        try:
            parts = [int(x) if x else 0 for x in m.groups()]
            when = datetime(*parts, tzinfo=timezone.utc)
        except ValueError:
            return None
        return tool(f"{when.strftime('%Y-%m-%d %H:%M:%S')} utc as unix time", str(int(when.timestamp())))
    m = re.fullmatch(r"lorem(?: ipsum)?(?: (\d{1,3}) (paragraphs?|sentences?|words?))?", q)
    if m:
        count, unit = int(m.group(1) or 1), (m.group(2) or "paragraph")
        limits = {"p": 10, "s": 30, "w": 300}
        if 1 <= count <= limits[unit[0]]:
            return tool(f"lorem ipsum, {count} {unit if count != 1 else unit.rstrip('s')}", lorem(count, unit), again=True)
    return None
