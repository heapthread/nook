from urllib.parse import parse_qs, urlparse

from selectolax.lexbor import LexborHTMLParser

from . import Result

NAME = "duckduckgo"
SUPPORTS_TIME = {"d", "w", "m", "y"}  # past day, week, month, year
SUPPORTS_SAFE = True
SUPPORTS_RANGE = True   # df=2020-01-01..2020-12-31
SAFE = {"strict": "1", "off": "-2"}  # its kp setting; moderate is what it does when told nothing


def can_region(code):
    return True  # its kl setting takes the code as it is


def _unwrap(href):
    if href.startswith("//"):
        href = "https:" + href
    q = parse_qs(urlparse(href).query)
    return q["uddg"][0] if "uddg" in q else href


def parse(text):
    out = []
    for node in LexborHTMLParser(text).css("div.web-result"):
        a = node.css_first("a.result__a")
        if a is None or not a.attributes.get("href"):
            continue
        snip = node.css_first(".result__snippet")
        out.append(Result(
            title=a.text(separator=" ", strip=True),
            url=_unwrap(a.attributes["href"]),
            snippet=snip.text(separator=" ", strip=True) if snip else "",
            engines=[NAME],
            rank=len(out),
        ))
    return out


def next_form(text):
    """The hidden fields of the "Next" button, which is how DuckDuckGo pages its results."""
    for form in LexborHTMLParser(text).css("form"):
        if form.css_first("input[value=Next]"):
            return {i.attributes["name"]: i.attributes.get("value") or ""
                    for i in form.css("input[name]")}
    return None


async def search(client, query, page=1, period=None, region=None, safe=None, date_range=None):
    data = {"q": query}
    if date_range:
        data["df"] = f"{date_range[0]}..{date_range[1]}"
    elif period in SUPPORTS_TIME:
        data["df"] = period
    if region:
        data["kl"] = region
    if safe in SAFE:
        data["kp"] = SAFE[safe]
    r = await client.post("https://html.duckduckgo.com/html/", data=data)
    r.raise_for_status()
    for _ in range(page - 1):  # no way to jump ahead, so walk through the pages
        fields = next_form(r.text)
        if not fields:
            if parse(r.text):
                return []  # a real last page
            raise RuntimeError("duckduckgo is not answering")  # throttled, not finished
        r = await client.post("https://html.duckduckgo.com/html/", data=fields)
        r.raise_for_status()
    return parse(r.text)
