import re
from urllib.parse import unquote

from selectolax.lexbor import LexborHTMLParser

import regions

from . import Result

NAME = "yahoo"
SUPPORTS_TIME = {"d", "w", "m"}  # no "past year" on Yahoo
SUPPORTS_SAFE = True
SAFE = {"strict": "r", "off": "p"}


def can_region(code):
    return regions.yahoo_site(code) is not None

# Yahoo turns away plain HTTP/1.1 clients with a server error but answers HTTP/2 ones
# like any browser, so the client nook passes in must be created with http2=True.
NEEDS_HTTP2 = True


def _unwrap(href):
    """Yahoo's links go through r.search.yahoo.com/.../RU=<the real address>/RK=..."""
    m = re.search(r"/RU=([^/]+)/R[KS]=", href)
    return unquote(m.group(1)) if m else href


def parse(text):
    out = []
    for node in LexborHTMLParser(text).css("div.algo"):
        a = node.css_first("h3.title a") or node.css_first("div.compTitle a")
        if a is None or not a.attributes.get("href"):
            continue
        url = _unwrap(a.attributes["href"])
        if not url.startswith("http"):
            continue
        title = node.css_first("h3.title") or a
        snippet = node.css_first("div.compText")
        out.append(Result(
            title=title.text(separator=" ", strip=True),
            url=url,
            snippet=snippet.text(separator=" ", strip=True) if snippet else "",
            engines=[NAME],
            rank=len(out),
        ))
    return out


async def search(client, query, page=1, period=None, region=None, safe=None):
    params = {"p": query}
    if period in SUPPORTS_TIME:
        params["btf"] = period
    if safe in SAFE:
        params["vm"] = SAFE[safe]
    if page > 1:
        params["b"] = (page - 1) * 7 + 1  # about seven organic results per page
    site = regions.yahoo_site(region)
    host = f"{site}.search.yahoo.com" if site else "search.yahoo.com"
    r = await client.get(f"https://{host}/search", params=params)
    r.raise_for_status()
    return parse(r.text)
