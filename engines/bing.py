import base64
from urllib.parse import parse_qs, urlparse

from selectolax.lexbor import LexborHTMLParser

from . import Result

NAME = "bing"
SUPPORTS_SAFE = True  # (a region is not offered: Bing serves a different page when given one)
SAFE = {"strict": "strict", "off": "off"}


def _unwrap(href):
    # Bing links go through /ck/a?u=a1<base64url of the real address>
    q = parse_qs(urlparse(href).query)
    u = q.get("u", [""])[0]
    if u.startswith("a1"):
        s = u[2:]
        try:
            return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4)).decode()
        except ValueError:
            pass
    return href


def parse(text):
    out = []
    for node in LexborHTMLParser(text).css("li.b_algo"):
        a = node.css_first("h2 a")
        if a is None or not a.attributes.get("href"):
            continue
        snip = node.css_first(".b_lineclamp2, .b_lineclamp3, .b_lineclamp4, p")
        out.append(Result(
            title=a.text(separator=" ", strip=True),
            url=_unwrap(a.attributes["href"]),
            snippet=snip.text(separator=" ", strip=True) if snip else "",
            engines=[NAME],
            rank=len(out),
        ))
    return out


async def search(client, query, page=1, safe=None, **_):
    if page > 1:
        # Bing ignores paging or drifts to unrelated pages for us, so it only gives page one
        return []
    params = {"q": query}
    if safe in SAFE:
        params["adlt"] = SAFE[safe]
    r = await client.get("https://www.bing.com/search", params=params)
    r.raise_for_status()
    return parse(r.text)
