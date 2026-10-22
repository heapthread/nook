"""Places near you or near somewhere: `ice cream near me`, `pharmacy in bonn`, `cafes nearby`.

The places come from OpenStreetMap (through its Nominatim search), so what a place has is what
volunteers entered: name, address and often opening hours, phone and website. OpenStreetMap is a
map, not a review site, so there are no star ratings or reviews here and nook does not make any up;
each place links to a web search for reviews instead.

Your position is only used if you press "use my location" (the browser asks you first), and only
for that one search."""
import contextvars
import math
import re
from urllib.parse import quote

import maps

# what you can ask for: words people use -> (Nominatim's phrase, how nook says it, a plain-text fallback)
CATEGORIES = {
    "ice cream": ("ice cream", "ice cream", "ice cream"), "gelato": ("ice cream", "ice cream", "gelato"),
    "gelateria": ("ice cream", "ice cream", "gelateria"), "cafe": ("cafe", "cafes", "cafe"), "coffee": ("cafe", "cafes", "coffee"),
    "coffee shop": ("cafe", "cafes", "coffee"), "restaurant": ("restaurant", "restaurants", "restaurant"),
    "pizza": ("pizza restaurant", "pizza", "pizza"), "pizzeria": ("pizza restaurant", "pizza", "pizza"),
    "sushi": ("sushi", "sushi", "sushi"), "burger": ("burger", "burgers", "burger"), "kebab": ("kebab", "kebab", "kebab"),
    "bakery": ("bakery", "bakeries", "bakery"), "bar": ("bar", "bars", "bar"), "pub": ("pub", "pubs", "pub"),
    "supermarket": ("supermarket", "supermarkets", "supermarket"), "grocery": ("supermarket", "supermarkets", "grocery"),
    "pharmacy": ("pharmacy", "pharmacies", "pharmacy"), "chemist": ("pharmacy", "pharmacies", "pharmacy"),
    "doctor": ("doctor", "doctors", "doctor"), "dentist": ("dentist", "dentists", "dentist"), "hospital": ("hospital", "hospitals", "hospital"),
    "atm": ("atm", "cash machines", "atm"), "bank": ("bank", "banks", "bank"), "post office": ("post office", "post offices", "post office"),
    "hotel": ("hotel", "hotels", "hotel"), "hostel": ("hostel", "hostels", "hostel"), "gas station": ("fuel", "petrol stations", "fuel station"),
    "petrol station": ("fuel", "petrol stations", "fuel station"), "fuel": ("fuel", "petrol stations", "fuel station"),
    "charging station": ("charging station", "charging stations", "charging station"), "parking": ("parking", "parking", "parking"),
    "toilet": ("toilets", "toilets", "toilets"), "toilets": ("toilets", "toilets", "toilets"), "library": ("library", "libraries", "library"),
    "museum": ("museum", "museums", "museum"), "cinema": ("cinema", "cinemas", "cinema"), "theatre": ("theatre", "theatres", "theatre"),
    "park": ("park", "parks", "park"), "playground": ("playground", "playgrounds", "playground"), "gym": ("gym", "gyms", "fitness centre"),
    "hairdresser": ("hairdresser", "hairdressers", "hairdresser"), "barber": ("hairdresser", "hairdressers", "barber"),
    "bookshop": ("bookshop", "bookshops", "books"), "bookstore": ("bookshop", "bookshops", "books"), "bike shop": ("bicycle", "bike shops", "bicycle shop"),
    "train station": ("railway station", "train stations", "railway station"), "bus stop": ("bus stop", "bus stops", "bus stop"),
    "school": ("school", "schools", "school"), "church": ("place of worship", "places of worship", "church"),
    "laundry": ("laundry", "laundries", "laundry"), "florist": ("florist", "florists", "florist"), "vet": ("veterinary", "vets", "veterinary"),
}
_WORDS = sorted(CATEGORIES, key=len, reverse=True)
_CAT = "|".join(re.escape(w) + r"(?:s|es)?" for w in _WORDS)
_FILLER = r"(?:the |a |some |good |best |nice |cheap |cheapest |nearest |closest |open now |open |late night |24 hour )*"
_SHOP = r"(?: (?:shops?|stores?|places?|spots?|joints?|near by))?"

here = contextvars.ContextVar("nook_here", default=None)    # (lat, lon) of this visitor, if they shared it for this search
THE_WORLD = (-85, 85)


def _category(text):
    word = text.strip().lower()
    for w in _WORDS:
        if word in (w, w + "s", w + "es"):
            return w
    return None


def parse(query):
    """-> (category word, place or None for "near me") or None."""
    q = re.sub(r"\s+", " ", query.strip().lower()).rstrip("?")
    m = re.fullmatch(rf"{_FILLER}({_CAT}){_SHOP} (?:near me|nearby|near by|around me|close to me|close by|around here|near here|open now|open nearby)", q)
    if m and _category(m.group(1)):
        return _category(m.group(1)), None
    m = re.fullmatch(rf"(?:where (?:is|are) )?{_FILLER}({_CAT}){_SHOP} (?:in|near|around|at|close to|within) (?!me\b)(.{{2,40}})", q)
    if m and _category(m.group(1)) and re.fullmatch(r"[^\W\d_][\w .,'\-]*", m.group(2)):
        return _category(m.group(1)), m.group(2).strip(" .,")
    return None


def metres(a, b):
    (la1, lo1), (la2, lo2) = (math.radians(a[0]), math.radians(a[1])), (math.radians(b[0]), math.radians(b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371008.8 * math.asin(math.sqrt(h))


def far(m):
    return f"{round(m / 10) * 10:g} m" if m < 1000 else f"{m / 1000:.1f} km"


def _first(*values):
    return next((v for v in values if v), "")


def _web(url):
    url = (url or "").strip()
    if re.match(r"^[a-z][a-z0-9+.\-]*:", url, re.I) and not re.match(r"^https?://", url, re.I):
        return ""                      # javascript:, mailto:, data: ... are not websites
    if url and not re.match(r"^https?://", url):
        url = "https://" + url
    return url if re.match(r"^https?://[^\s]+$", url) else ""


def place_from(item, centre=None):
    """One Nominatim result -> the little dictionary the cards and the place page use. None if it has no name."""
    tags = item.get("extratags") or {}
    addr = item.get("address") or {}
    name = (item.get("name") or (item.get("namedetails") or {}).get("name") or "").strip()
    if not name:
        return None
    try:
        lat, lon = float(item["lat"]), float(item["lon"])
    except (KeyError, TypeError, ValueError):
        return None
    road = " ".join(x for x in (addr.get("road") or addr.get("pedestrian") or addr.get("footway"), addr.get("house_number")) if x)
    town = " ".join(x for x in (addr.get("postcode"), _first(addr.get("city"), addr.get("town"), addr.get("village"), addr.get("suburb"))) if x)
    commons = tags.get("wikimedia_commons") or ""
    image = _web(tags.get("image")) if tags.get("image") else ""
    if not image and commons.startswith("File:"):
        image = "https://commons.wikimedia.org/wiki/Special:FilePath/" + quote(commons[5:].replace(" ", "_")) + "?width=640"
    cuisine = ", ".join(c.replace("_", " ") for c in tags.get("cuisine", "").split(";") if c)[:80]
    place = {
        "id": f"{item.get('osm_type', 'node')[0].upper()}{item.get('osm_id', 0)}",
        "name": name, "kind": (item.get("type") or "").replace("_", " "), "lat": lat, "lon": lon,
        "address": ", ".join(x for x in (road, town) if x), "town": _first(addr.get("city"), addr.get("town"), addr.get("village")),
        "hours": re.sub(r"\s+", " ", tags.get("opening_hours", ""))[:160],
        "phone": _first(tags.get("phone"), tags.get("contact:phone"))[:40],
        "website": _web(_first(tags.get("website"), tags.get("contact:website"))),
        "wheelchair": tags.get("wheelchair", ""), "cuisine": cuisine, "image": image,
        "distance": None, "far": "",
    }
    if centre:
        d = metres(centre, (lat, lon))
        place["distance"], place["far"] = d, far(d)
    return place


def parse_results(data, centre=None, limit=8):
    places, seen = [], set()
    for item in data if isinstance(data, list) else []:
        p = place_from(item, centre)
        if p and p["id"] not in seen:
            seen.add(p["id"])
            places.append(p)
    if centre:
        places.sort(key=lambda p: p["distance"])
    return places[:limit]


def card(places, category, where, centre, query):
    if not places:
        return None
    lats, lons = [p["lat"] for p in places], [p["lon"] for p in places]
    zoom = maps.zoom_from_box([str(min(lats)), str(max(lats)), str(min(lons)), str(max(lons))]) - 1
    return {"kind": "places", "title": f"{CATEGORIES[category][1]} {'near ' + where if where else 'near you'}", "items": places,
            "markers": [{"lat": p["lat"], "lon": p["lon"], "label": p["name"], "href": f"/place/{p['id']}?q={quote(query)}"} for p in places],
            "lat": (min(lats) + max(lats)) / 2, "lon": (min(lons) + max(lons)) / 2, "zoom": max(11, min(zoom, 17)), "query": query}


def _search(phrase, centre, span):
    lat, lon = centre
    box = f"{lon - span * 1.5:.5f},{lat + span:.5f},{lon + span * 1.5:.5f},{lat - span:.5f}"
    return maps.nominatim("search", {"q": phrase, "viewbox": box, "bounded": 1, "limit": 20, "addressdetails": 1, "extratags": 1})


def find(category, where=None, ll=None):
    """-> (places, centre, where label). Raises httpx errors when OpenStreetMap is unreachable."""
    phrase, _, fallback = CATEGORIES[category]
    if ll:
        centre, label = ll, None
    else:
        found = maps.search(where)
        if not found:
            return [], None, where
        centre, label = (found[0]["lat"], found[0]["lon"]), found[0]["name"]
    for span in (0.03, 0.09):
        data = _search(phrase, centre, span)
        if len(data) < 3 and fallback != phrase:
            data = data + _search(fallback, centre, span)
        if len(data) >= 3:
            break
    return parse_results(data, centre), centre, label


async def lookup(client, query):
    parsed = parse(query)
    if not parsed:
        return None
    import asyncio
    category, where = parsed
    spot = here.get()
    if where is None and spot is None:
        return {"kind": "locate", "category": CATEGORIES[category][1], "query": query}
    try:
        places, centre, label = await asyncio.to_thread(find, category, where, spot if where is None else None)
    except Exception:
        return None
    return card(places, category, label if where else None, centre, query)


def get(osm_id):
    """One place by its id (N123, W456, R789), for the place page. None if OpenStreetMap does not know it."""
    if not re.fullmatch(r"[NWR]\d{1,12}", osm_id or ""):
        return None
    data = maps.nominatim("lookup", {"osm_ids": osm_id, "addressdetails": 1, "extratags": 1, "namedetails": 1})
    return place_from(data[0]) if data else None
