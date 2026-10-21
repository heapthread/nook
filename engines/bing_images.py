import json

from selectolax.lexbor import LexborHTMLParser

from . import Image

NAME = "bing images"
SUPPORTS_SAFE = True
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


async def search(client, query, page=1, safe=None, **_):
    params = {"q": query}
    if safe in SAFE:
        params["adlt"] = SAFE[safe]
    if page > 1:
        params["first"] = (page - 1) * 35 + 1
    r = await client.get("https://www.bing.com/images/search", params=params)
    r.raise_for_status()
    return parse(r.text)
