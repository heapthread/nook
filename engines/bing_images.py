import json

from selectolax.lexbor import LexborHTMLParser

from . import Image

NAME = "bing images"
SUPPORTS_SAFE = True
SUPPORTS_FILTERS = True
SAFE = {"strict": "strict", "off": "off"}


def parse(text):
    out = []
    for a in LexborHTMLParser(text).css("a.iusc"):
        try:
            m = json.loads(a.attributes.get("m", ""))
        except ValueError:
            continue
        if not (m.get("murl") and m.get("turl")):
            continue
        out.append(Image(
            title=m.get("t", "").replace("\ue000", "").replace("\ue001", ""),
            thumb=m["turl"],
            full=m["murl"],
            page=m.get("purl", m["murl"]),
        ))
    return out


SIZES = {"small": "small", "medium": "medium", "large": "large", "huge": "wallpaper"}
KINDS = {"photo": "photo-photo", "clipart": "photo-clipart", "drawing": "photo-linedrawing", "animated": "photo-animatedgif"}
COLOURS = {"red": "FGcls_RED", "orange": "FGcls_ORANGE", "yellow": "FGcls_YELLOW", "green": "FGcls_GREEN",
           "teal": "FGcls_TEAL", "blue": "FGcls_BLUE", "purple": "FGcls_PURPLE", "pink": "FGcls_PINK",
           "brown": "FGcls_BROWN", "black": "FGcls_BLACK", "grey": "FGcls_GRAY", "white": "FGcls_WHITE",
           "black and white": "bw"}


def filters(size=None, kind=None, colour=None):
    """Bing's `qft` value for the filters chosen: "+filterui:imagesize-large+filterui:photo-photo"."""
    parts = []
    if size in SIZES:
        parts.append(f"imagesize-{SIZES[size]}")
    if kind in KINDS:
        parts.append(KINDS[kind])
    if colour in COLOURS:
        parts.append("color2-" + COLOURS[colour])
    return "".join(f"+filterui:{p}" for p in parts)


async def search(client, query, page=1, safe=None, size=None, kind=None, colour=None, **_):
    params = {"q": query}
    qft = filters(size, kind, colour)
    if qft:
        params["qft"] = qft
    if safe in SAFE:
        params["adlt"] = SAFE[safe]
    if page > 1:
        params["first"] = (page - 1) * 35 + 1
    r = await client.get("https://www.bing.com/images/search", params=params)
    r.raise_for_status()
    return parse(r.text)
