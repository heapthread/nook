import json
import re
from urllib.parse import quote

from . import Result

NAME = "wikipedia"
CONTACT = ""  # set by app.py from config.toml


def parse(text):
    out = []
    for hit in json.loads(text).get("query", {}).get("search", []):
        title = hit["title"]
        out.append(Result(
            title=f"{title} - Wikipedia",
            url="https://en.wikipedia.org/wiki/" + quote(title.replace(" ", "_")),
            snippet=re.sub(r"<[^>]+>", "", hit.get("snippet", "")).replace("&quot;", '"'),
            engines=[NAME],
            rank=len(out),
        ))
    return out


async def search(client, query, page=1, **_):
    if page > 1:
        return []  # one short "answer" is all it gives
    # Wikimedia rejects browser-style agents and asks API clients to identify themselves.
    ua = f"nook-metasearch/0.1 (self-hosted personal project; {CONTACT})"
    if not CONTACT:
        raise RuntimeError("wikipedia needs `contact` in config.toml")
    r = await client.get("https://en.wikipedia.org/w/api.php", params={
        "action": "query", "list": "search", "srsearch": query,
        "format": "json", "srlimit": 3,
    }, headers={"User-Agent": ua})
    r.raise_for_status()
    return parse(r.text)
