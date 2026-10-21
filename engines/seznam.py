import re

from selectolax.lexbor import LexborHTMLParser

from . import Result

NAME = "seznam"

# Seznam is a Czech engine with an index of its own, so it brings results Bing and Yahoo
# don't. Its class names are scrambled and change, so this leans on its data-e-a hooks.
NEEDS_HTTP2 = True

# For an English search it fills up with Czech and Slovak shops, so those sites are left out.
SKIPPED_ENDINGS = (".cz", ".sk")


def _skipped(url):
    host = re.match(r"https?://([^/:?#]+)", url)
    return bool(host) and host.group(1).lower().endswith(SKIPPED_ENDINGS)


def parse(text):
    out, seen = [], set()
    for a in LexborHTMLParser(text).css('h3 a[data-e-a="heading"]'):
        url = a.attributes.get("href", "")
        if not re.match(r"https?://", url) or _skipped(url) or url in seen:
            continue
        seen.add(url)
        block = a.parent.parent.parent  # heading -> its box -> the whole result
        snippet = ""
        if block is not None:
            for span in block.css("span"):
                if span.parent.tag == "a":
                    continue  # the title and the address line
                words = re.sub(r"\s+", " ", span.text(separator=" ", strip=True))
                if len(words) > len(snippet):
                    snippet = words
        out.append(Result(
            title=re.sub(r"\s+", " ", a.text(separator=" ", strip=True)),
            url=url,
            snippet=snippet,
            engines=[NAME],
            rank=len(out),
        ))
    return out


async def search(client, query, page=1, **_):
    if page > 1:
        return []  # its paging is not worth the guesswork
    r = await client.get("https://search.seznam.cz/", params={"q": query})
    r.raise_for_status()
    return parse(r.text)
