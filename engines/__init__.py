from dataclasses import dataclass, field
from importlib import import_module

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
# What a real Chrome 126 sends when you type an address, so requests look like a person's.
HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Ch-Ua": '"Chromium";v="126", "Not.A/Brand";v="24", "Google Chrome";v="126"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
}

# An engine is a module with NAME, async search(client, query), and a pure
# parse(text) that turns a response body into a list of Result.
AVAILABLE = ["duckduckgo", "bing", "yahoo", "seznam", "wikipedia"]


@dataclass
class Result:
    title: str
    url: str
    snippet: str = ""
    engines: list[str] = field(default_factory=list)
    rank: int = 0
    date: str = ""


@dataclass
class Image:
    title: str
    thumb: str
    full: str
    page: str


@dataclass
class Video:
    title: str
    url: str
    thumb: str
    duration: str = ""
    meta: str = ""


def load(names):
    return [import_module(f"engines.{n}") for n in names if n in AVAILABLE]
