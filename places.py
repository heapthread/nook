"""Places and their time zones: "time in germany", "ethiopia time to germany time",
"3pm in tokyo to new york", "10am est to cet", "time difference between lagos and berlin".

Countries, big cities and zone names come from tables that ship with the time zone database.
A place those don't know (Bonn, Hallstatt...) is looked up once on Open-Meteo's place search,
by nook, and remembered."""
import importlib.resources
import os
import re
import time
import zoneinfo
from datetime import datetime, timezone
from typing import NamedTuple
from zoneinfo import ZoneInfo, available_timezones

# What people type for a zone, when it isn't a place.
ABBREVIATIONS = {
    "utc": "UTC", "gmt": "UTC", "z": "UTC",
    "est": "America/New_York", "edt": "America/New_York", "et": "America/New_York",
    "cst": "America/Chicago", "cdt": "America/Chicago", "ct": "America/Chicago",
    "mst": "America/Denver", "mdt": "America/Denver", "mt": "America/Denver",
    "pst": "America/Los_Angeles", "pdt": "America/Los_Angeles", "pt": "America/Los_Angeles",
    "akst": "America/Anchorage", "hst": "Pacific/Honolulu",
    "cet": "Europe/Berlin", "cest": "Europe/Berlin", "eet": "Europe/Helsinki", "eest": "Europe/Helsinki",
    "wet": "Europe/Lisbon", "bst": "Europe/London", "msk": "Europe/Moscow",
    "ist": "Asia/Kolkata", "jst": "Asia/Tokyo", "kst": "Asia/Seoul", "hkt": "Asia/Hong_Kong",
    "sgt": "Asia/Singapore", "pkt": "Asia/Karachi", "aest": "Australia/Sydney", "aedt": "Australia/Sydney",
    "acst": "Australia/Adelaide", "awst": "Australia/Perth", "nzst": "Pacific/Auckland",
    "nzdt": "Pacific/Auckland", "sast": "Africa/Johannesburg", "eat": "Africa/Nairobi",
    "wat": "Africa/Lagos", "cat": "Africa/Maputo",
}

# Big places that have no zone of their own (or that people name differently).
CITIES = {
    "beijing": "Asia/Shanghai", "mumbai": "Asia/Kolkata", "bombay": "Asia/Kolkata", "delhi": "Asia/Kolkata",
    "new delhi": "Asia/Kolkata", "bangalore": "Asia/Kolkata", "bengaluru": "Asia/Kolkata",
    "osaka": "Asia/Tokyo", "kyoto": "Asia/Tokyo", "san francisco": "America/Los_Angeles",
    "seattle": "America/Los_Angeles", "las vegas": "America/Los_Angeles", "portland": "America/Los_Angeles",
    "boston": "America/New_York", "washington": "America/New_York", "washington dc": "America/New_York",
    "miami": "America/New_York", "atlanta": "America/New_York", "philadelphia": "America/New_York",
    "dallas": "America/Chicago", "houston": "America/Chicago", "austin": "America/Chicago",
    "munich": "Europe/Berlin", "frankfurt": "Europe/Berlin", "hamburg": "Europe/Berlin",
    "cologne": "Europe/Berlin", "barcelona": "Europe/Madrid", "milan": "Europe/Rome",
    "lyon": "Europe/Paris", "geneva": "Europe/Zurich", "cape town": "Africa/Johannesburg",
    "abu dhabi": "Asia/Dubai", "saigon": "Asia/Ho_Chi_Minh", "hanoi": "Asia/Ho_Chi_Minh",
    "kiev": "Europe/Kyiv", "st petersburg": "Europe/Moscow", "saint petersburg": "Europe/Moscow",
    "new york city": "America/New_York", "nyc": "America/New_York", "la": "America/Los_Angeles",
}
COUNTRY_ALIASES = {
    "usa": "US", "us": "US", "america": "US", "the us": "US", "united states of america": "US",
    "uk": "GB", "britain": "GB", "great britain": "GB", "england": "GB", "scotland": "GB", "wales": "GB",
    "northern ireland": "GB", "uae": "AE", "emirates": "AE", "holland": "NL", "ivory coast": "CI",
    "south korea": "KR", "north korea": "KP", "czechia": "CZ", "burma": "MM", "dr congo": "CD", "drc": "CD",
    "congo": "CG",
}
# Countries with several zones: the one most people mean.
MAIN_ZONE = {"US": "America/New_York", "BR": "America/Sao_Paulo", "CA": "America/Toronto",
             "AU": "Australia/Sydney", "RU": "Europe/Moscow", "MN": "Asia/Ulaanbaatar"}

_cities, _countries = {}, {}
LEARNED = {}  # name -> (when, (zone, "bonn, germany")) or (when, None): looked up on Open-Meteo
LEARNED_KEEP, UNKNOWN_KEEP, LEARNED_MAX = 30 * 86400, 86400, 2000
GEOCODER = "https://geocoding-api.open-meteo.com/v1/search"


class Place(NamedTuple):
    zone: str
    name: str          # what to call it: what the visitor typed
    city: str = ""     # the city behind a country or a looked-up place
    learned: bool = False


def _tab(name):
    """One of the .tab files that ship with the time zone database."""
    try:
        return importlib.resources.files("tzdata.zoneinfo").joinpath(name).read_text(encoding="utf-8")
    except (ModuleNotFoundError, FileNotFoundError, OSError):
        pass
    for folder in zoneinfo.TZPATH:
        try:
            with open(os.path.join(folder, name), encoding="utf-8") as f:
                return f.read()
        except OSError:
            continue
    return ""


def _norm(text):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", text.lower().replace("'", ""))).strip()


def _build():
    for zone in sorted(available_timezones()):
        _cities.setdefault(_norm(zone.rsplit("/", 1)[-1].replace("_", " ")), zone)
    zones = {}
    for line in _tab("zone.tab").splitlines():
        if line and not line.startswith("#"):
            parts = line.split("\t")
            if len(parts) >= 3:
                zones.setdefault(parts[0], []).append(parts[2])
    for line in _tab("iso3166.tab").splitlines():
        if not line or line.startswith("#") or "\t" not in line:
            continue
        code, name = line.split("\t")[:2]
        zone = MAIN_ZONE.get(code) or (zones.get(code) or [None])[0]
        if not zone:
            continue
        _countries[_norm(name)] = (code, zone)
        m = re.match(r"^(.*?) \((.*?)\)$", name)  # "Korea (South)" is also "south korea"
        if m:
            _countries[_norm(f"{m.group(2)} {m.group(1)}")] = (code, zone)
            _countries.setdefault(_norm(m.group(1)), (code, zone))
    for alias, code in COUNTRY_ALIASES.items():
        zone = MAIN_ZONE.get(code) or (zones.get(code) or [None])[0]
        if zone:
            _countries[_norm(alias)] = (code, zone)


def _name(text):
    """What is left of a place as typed, once 'time', 'time zone' and 'the' are taken away."""
    name = _norm(text)
    name = re.sub(r"\b(?:local )?time ?zone\b|\btime\b|\bcurrent\b", " ", name)
    return re.sub(r"^the ", "", re.sub(r"\s+", " ", name).strip())


def resolve(text):
    """A place, country or zone name -> Place, or None."""
    if not _cities:
        _build()
    name = _name(text)
    if not name:
        return None
    if name in ABBREVIATIONS:
        return Place(ABBREVIATIONS[name], name.upper())
    zone = CITIES.get(name) or _cities.get(name)
    if zone:
        return Place(zone, name)
    if name in _countries:
        zone = _countries[name][1]
        return Place(zone, name, _norm(zone.rsplit("/", 1)[-1].replace("_", " ")))
    hit = LEARNED.get(name)
    if hit and hit[1] and time.monotonic() - hit[0] < LEARNED_KEEP:
        return Place(hit[1][0], name, hit[1][1], learned=True)
    return None


# --- places we have to look up ---------------------------------------------------

def parse_geocode(data, name):
    """The zone of the place called exactly `name` (the biggest, if several)."""
    best = None
    for item in (data or {}).get("results") or []:
        if _norm(item.get("name", "")) != name or not str(item.get("feature_code", "")).startswith("PPL"):
            continue
        if item.get("timezone") and (best is None or (item.get("population") or 0) > (best.get("population") or 0)):
            best = item
    if not best:
        return None
    where = f"{name}, {_norm(best.get('country', ''))}" if best.get("country") else name
    return best["timezone"], where


async def learn(client, names):
    """Look up places nook doesn't know. Fills LEARNED; asks about each name only once a day."""
    for name in names[:2]:
        hit = LEARNED.get(name)
        if hit and time.monotonic() - hit[0] < (LEARNED_KEEP if hit[1] else UNKNOWN_KEEP):
            continue
        try:
            r = await client.get(GEOCODER, params={"name": name, "count": 10, "language": "en", "format": "json"})
            r.raise_for_status()
            found = parse_geocode(r.json(), name)
        except Exception:
            continue  # the service is down: try again next time, remember nothing
        if len(LEARNED) >= LEARNED_MAX:
            LEARNED.clear()
        LEARNED[name] = (time.monotonic(), found)


# --- clocks -------------------------------------------------------------------

_CLOCK = re.compile(r"^(?:(noon|midnight)|(\d{1,2})(?::(\d{2}))?\s*(a\.?m\.?|p\.?m\.?)?)(?=\s|$)")


def parse_clock(text):
    """'3pm', '3:30 pm', '15:00', 'noon' -> (hour, minute, typed_with_am_pm, rest of the text)."""
    m = _CLOCK.match(text)
    if not m:
        return None
    rest = text[m.end():].strip()
    if m.group(1):
        return (12 if m.group(1) == "noon" else 0), 0, True, rest
    hour, minute, ampm = int(m.group(2)), int(m.group(3) or 0), m.group(4)
    if not ampm and m.group(3) is None:
        return None  # a bare number is not a time
    if ampm:
        if not 1 <= hour <= 12:
            return None
        hour = hour % 12 + (12 if ampm.startswith("p") else 0)
    if hour > 23 or minute > 59:
        return None
    return hour, minute, bool(ampm), rest


def _utc(moment):
    minutes = int(moment.utcoffset().total_seconds() // 60)
    sign, minutes = ("+" if minutes >= 0 else "-"), abs(minutes)
    return f"UTC{sign}{minutes // 60}" + (f":{minutes % 60:02d}" if minutes % 60 else "")


def _clock(moment, twelve):
    if twelve:
        return moment.strftime("%I:%M %p").lstrip("0").lower()
    return moment.strftime("%H:%M")


def _side(moment, place, twelve):
    city = f" · {place.city}" if place.city else ""
    return {"place": place.name, "clock": _clock(moment, twelve), "day": moment.strftime("%A %d %B").lower(),
            "zone": f"{moment.tzname()}, {_utc(moment)}{city}"}


def _difference(first, second, a, b):
    delta = int((second.utcoffset() - first.utcoffset()).total_seconds() // 60)
    if delta == 0:
        return f"{b} and {a} are on the same time"
    hours, minutes = divmod(abs(delta), 60)
    amount = " ".join(x for x in (f"{hours} hour{'s' if hours != 1 else ''}" if hours else "",
                                  f"{minutes} minutes" if minutes else "") if x)
    return f"{b} is {amount} {'ahead of' if delta > 0 else 'behind'} {a}"


# --- reading the question -------------------------------------------------------

def _now(now):
    return now or datetime.now(timezone.utc)


def _single(q):
    """'time in germany', 'what time is it in tokyo', 'lagos time' -> the place as typed."""
    m = re.match(r"^(?:what(?:'s| is)? )?(?:the )?(?:current )?time(?: is it)?(?: right now)? in (.+)$", q) \
        or re.match(r"^(.+?) (?:current )?(?:local )?time(?: now)?$", q)
    return m.group(1) if m else None


def _pairs(q):
    """Every way to read the question as 'a place, then another place'.

    Returns (clock, wants_time, [(left, right), ...]); clock is None when no hour was given."""
    m = re.match(r"^(?:what(?:'s| is) )?(?:the )?time (?:difference|diff) (?:between|from) (.+?) (?:and|to|vs|versus) (.+)$", q)
    if m:
        return None, True, [(m.group(1), m.group(2))]
    s = re.sub(r"^(?:what(?:'s| is) |convert |when it(?:'s| is) |if it(?:'s| is) )", "", q).strip()
    clock = None
    got = parse_clock(s)
    if got:
        clock, s = got[:3], got[3]
    s = re.sub(r"^(?:the )?(?:time )?(?:in|at|from)\s+", "", s)
    wants_time = bool(clock) or bool(re.search(r"\b(?:time|zone|o'clock)\b", q))
    pairs = [(s[:x.start()], s[x.end():]) for x in re.finditer(r"\s(?:to|into|in|as|vs|versus|->)\s", s)]
    return clock, wants_time, pairs


def _normal(query):
    return re.sub(r"\s+", " ", query.strip().lower()).rstrip("?").strip()


def unknown_places(query):
    """Places in a time question that nook can't place yet (so they can be looked up).

    A pair question needs one side we do know, and a single place must look like a place name,
    so ordinary searches never cause a lookup."""
    q = _normal(query)
    clock, wants_time, pairs = _pairs(q)
    if wants_time:
        for left, right in pairs:
            known_left, known_right = resolve(left), resolve(right)
            if known_left and not known_right and _plausible(right):
                return [_name(right)]
            if known_right and not known_left and _plausible(left):
                return [_name(left)]
    text = _single(q)
    if text and not pairs_resolve(pairs) and not resolve(text) and _plausible(text):
        return [_name(text)]
    return []


def pairs_resolve(pairs):
    return any(resolve(a) and resolve(b) for a, b in pairs)


def _plausible(text):
    name = _name(text)
    return bool(re.fullmatch(r"[a-z]+(?: [a-z]+){0,2}", name)) and len(name) >= 3 and name not in ("time", "now")


# --- answering --------------------------------------------------------------------

def _credit(*places):
    return "place lookup: open-meteo.com" if any(p.learned for p in places) else ""


def time_in(q, now=None):
    text = _single(q)
    place = resolve(text) if text else None
    if not place:
        return None
    side = _side(_now(now).astimezone(ZoneInfo(place.zone)), place, False)
    return {"kind": "time", "place": side["place"], "clock": side["clock"], "day": side["day"],
            "zone": side["zone"], "credit": _credit(place)}


def convert(q, now=None):
    """Two places: now, or at a given clock time in the first one."""
    clock, wants_time, pairs = _pairs(q)
    pair = None
    for left, right in pairs:
        a, b = resolve(left), resolve(right)
        if a and b and (wants_time or (a.name == a.name.upper() and b.name == b.name.upper())):
            pair = (a, b)
            break
    if not pair:
        return None
    a, b = pair
    za, zb = ZoneInfo(a.zone), ZoneInfo(b.zone)
    moment = _now(now).astimezone(za)
    if clock:
        moment = datetime.combine(moment.date(), datetime.min.time(), tzinfo=za).replace(hour=clock[0], minute=clock[1])
    there = moment.astimezone(zb)
    twelve = bool(clock and clock[2])
    first, second = _side(moment, a, twelve), _side(there, b, twelve)
    note = _difference(moment, there, a.name, b.name)
    shift = (there.date() - moment.date()).days
    if shift:
        note += " · " + ("the next day" if shift > 0 else "the day before") + f", {second['day']}"
    else:
        note += f" · {first['day']}"
    return {"kind": "zones", "first": first, "second": second, "note": note, "credit": _credit(a, b)}


def answer(query, now=None):
    q = _normal(query)
    return convert(q, now) or time_in(q, now)
