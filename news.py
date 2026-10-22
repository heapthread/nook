import asyncio
import re
import time
import tomllib
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from xml.etree import ElementTree as ET

import httpx
from selectolax.lexbor import LexborHTMLParser

WINGS = ["far-left", "left", "centre", "right", "far-right"]
TTL = 600  # seconds before a feed is fetched again when someone asks for it

ATOM = "{http://www.w3.org/2005/Atom}"
MEDIA = "{http://search.yahoo.com/mrss/}"
CONTENT = "{http://purl.org/rss/1.0/modules/content/}"
DC = "{http://purl.org/dc/elements/1.1/}"
RDF = "{http://purl.org/rss/1.0/}"


@dataclass
class Story:
    title: str
    url: str
    source: str
    wing: str
    summary: str = ""
    image: str = ""
    when: datetime | None = None
    full: str = ""  # whatever HTML the feed itself carried, used if the page can't be fetched
    also: list = field(default_factory=list)  # other outlets' takes on the same story


def load_feeds(path):
    data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    return [f for f in data.get("feed", []) if f.get("wing") in WINGS]


def _text(node, *names):
    for name in names:
        el = node.find(name)
        if el is not None and (el.text or "").strip():
            return el.text.strip()
    return ""


def _plain(html):
    if not html:
        return ""
    text = LexborHTMLParser(f"<div>{html}</div>").text(separator=" ", strip=True)
    return re.sub(r"\s+", " ", text)


def _when(raw):
    if not raw:
        return None
    try:
        d = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        try:
            d = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _image(node, html):
    for tag in (f"{MEDIA}content", f"{MEDIA}thumbnail"):
        for el in node.iter(tag):
            url = el.get("url", "")
            kind = el.get("type", "image/")
            if url.startswith("http") and kind.startswith("image/") and el.get("medium", "image") == "image":
                return url
    for el in node.findall("enclosure"):
        if el.get("type", "").startswith("image/") and el.get("url", "").startswith("http"):
            return el.get("url")
    m = re.search(r"<img[^>]+src=[\"'](https?://[^\"']+)", html or "")
    return m.group(1) if m else ""


def parse(xml, source, wing):
    root = ET.fromstring(xml)
    out = []
    for item in root.iter():
        if item.tag not in ("item", f"{ATOM}entry", f"{RDF}item"):
            continue
        if item.tag == f"{ATOM}entry":
            link = next((l.get("href") for l in item.findall(f"{ATOM}link")
                         if l.get("rel", "alternate") == "alternate"), "")
            body = _text(item, f"{ATOM}summary", f"{ATOM}content")
            title = _text(item, f"{ATOM}title")
            when = _text(item, f"{ATOM}published", f"{ATOM}updated")
        else:
            link = _text(item, "link", f"{RDF}link")
            body = _text(item, "description", f"{RDF}description")
            title = _text(item, "title", f"{RDF}title")
            when = _text(item, "pubDate", f"{DC}date")
        full = _text(item, f"{CONTENT}encoded") or body
        if not (title and link.startswith("http")):
            continue
        out.append(Story(
            title=_plain(title),
            url=link,
            source=source,
            wing=wing,
            summary=_plain(body)[:240],
            image=_image(item, full),
            when=_when(when),
            full=full,
        ))
    return out


def feed_title(xml):
    """The name a feed gives itself (its channel or feed title), or ''."""
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return ""
    node = root.find("channel/title")
    if node is None:
        node = root.find(f"{ATOM}title")
    return _plain(node.text or "")[:60] if node is not None and node.text else ""


def all_cached():
    """Every story we hold right now, whichever wing."""
    return [s for _, stories in list(_cache.values()) for s in stories]


def find(url):
    """A story we fetched recently, by its address."""
    for _, stories in _cache.values():
        for s in stories:
            if s.url == url:
                return s
    return None


_cache = {}  # feed url -> (when it was fetched, stories)


async def _one(client, feed, force=False):
    hit = _cache.get(feed["url"])
    if hit and not force and time.monotonic() - hit[0] < TTL:
        return hit[1]
    try:
        r = await client.get(feed["url"])
        r.raise_for_status()
        stories = parse(r.content, feed["name"], feed["wing"])
    except Exception:
        if hit:  # a feed that is down for a moment keeps showing what we had
            return hit[1]
        raise
    if stories:
        _cache[feed["url"]] = (time.monotonic(), stories)
    return stories


async def gather(client, feeds, force=False):
    """Fetch every feed at once. Returns (stories, names of feeds that failed)."""
    outcomes = await asyncio.gather(*(_one(client, f, force) for f in feeds), return_exceptions=True)
    stories, failed = [], []
    for feed, outcome in zip(feeds, outcomes):
        if isinstance(outcome, BaseException) or not outcome:
            failed.append(feed["name"])
        else:
            stories.append(outcome)
    return stories, failed


def mix(per_feed, per_source, total):
    """Newest first, with at most `per_source` stories from any one outlet."""
    picked = []
    for stories in per_feed:
        stories = sorted(stories, key=lambda s: s.when or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        picked.extend(stories[:per_source])
    picked.sort(key=lambda s: s.when or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return picked[:total]


def ago(when, now=None):
    if when is None:
        return ""
    secs = int(((now or datetime.now(timezone.utc)) - when).total_seconds())
    if secs < 90:
        return "just now"
    if secs < 3600:
        return f"{secs // 60}m ago"
    if secs < 86400:
        return f"{secs // 3600}h ago"
    return f"{secs // 86400}d ago"


def keep_warm(feeds, headers, timeout, minutes):
    """Refresh every feed in the background so /news never waits on the outlets."""
    import threading

    async def once():
        async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=timeout) as client:
            await gather(client, feeds, force=True)

    def loop():
        while True:
            try:
                asyncio.run(once())
            except Exception:
                pass
            time.sleep(minutes * 60)

    thread = threading.Thread(target=loop, name="news-refresh", daemon=True)
    thread.start()
    return thread


# --- the same story, told by different outlets -----------------------------

STOP = set("""a an the and or but of in on at to for from by with as is are was were be been it its this
that these those he she they we you i his her their our your not no new says say said after before over
under about into out up down more most less than then how why what who when where will would could
should can may might has have had do does did just also amid vs behind whats heres explained live watch latest update updates""".split())
WINDOW = 2 * 86400  # seconds: two headlines this far apart are not the same news


def _tokens(title):
    words = re.findall(r"[a-z0-9]+", title.lower().replace("’", "").replace("'", ""))
    return {w for w in words if w not in STOP and len(w) > 2}


def _same(a, b):
    shared = len(a & b)
    return shared >= 3 and shared / min(len(a), len(b)) >= 0.6


def with_coverage(stories, everything, cap=4):
    """Copies of `stories`, each with `also`: other outlets' takes on the same story.

    `everything` is every story we have, whichever wing, so a headline in one wing can
    point at how the others covered it."""
    pool = [(s, _tokens(s.title)) for s in everything]
    out = []
    for s in stories:
        mine = _tokens(s.title)
        others, outlets = [], {s.source}
        for t, theirs in sorted(pool, key=lambda p: p[0].when or datetime.min.replace(tzinfo=timezone.utc), reverse=True):
            if t.source in outlets or not _same(mine, theirs):
                continue
            if s.when and t.when and abs((s.when - t.when).total_seconds()) > WINDOW:
                continue
            outlets.add(t.source)
            others.append(t)
            if len(others) >= cap:
                break
        out.append(replace(s, also=others))
    return out


def matching(stories, query):
    """Stories whose headline or summary has every word searched for, newest first."""
    terms = [t for t in re.findall(r"[a-z0-9]{2,}", query.lower())]
    if not terms:
        return []
    hits = [s for s in stories if all(t in f"{s.title} {s.summary}".lower() for t in terms)]
    return sorted(hits, key=lambda s: s.when or datetime.min.replace(tzinfo=timezone.utc), reverse=True)


def top_stories(everything, total=60, per_source=3, hours=36):
    """The biggest stories across every wing: ones several outlets told come first.

    Headlines about the same thing are grouped (newest telling leads, the rest become `also`),
    then groups are ordered by how many outlets covered them, then by recency. Stories only
    one outlet ran follow, newest first, with at most `per_source` from any one outlet."""
    floor = datetime.now(timezone.utc) - timedelta(hours=hours)
    newest_first = sorted((s for s in everything if s.when is None or s.when >= floor),
                          key=lambda s: s.when or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    groups = []  # [lead, lead tokens, [others]]
    for s in newest_first:
        mine = _tokens(s.title)
        for g in groups:
            if len(g[2]) < 5 and s.source != g[0].source and all(s.source != o.source for o in g[2])                     and _same(mine, g[1]):
                g[2].append(s)
                break
        else:
            groups.append([s, mine, []])
    covered = [replace(g[0], also=g[2]) for g in groups if g[2]]
    covered.sort(key=lambda s: (-len(s.also), -(s.when.timestamp() if s.when else 0)))
    alone, used = [], {}
    for g in groups:
        if g[2]:
            continue
        used[g[0].source] = used.get(g[0].source, 0) + 1
        if used[g[0].source] <= per_source:
            alone.append(g[0])
    return (covered + alone)[:total]
