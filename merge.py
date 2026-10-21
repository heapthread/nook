import asyncio
import re
import time
from urllib.parse import parse_qsl, urlencode, urlparse

import httpx

TRACKING = {"fbclid", "gclid", "ref", "ref_src", "mc_cid", "mc_eid"}
RRF_K = 60

# An engine that fails twice in a row is left alone for a while, so a throttled
# engine isn't hammered and the page isn't slowed by waiting on it.
REST_FIRST = 60
REST_MAX = 600
resting = {}   # engine name -> (until, current rest length)


def normalize(url):
    p = urlparse(url)
    host = p.netloc.lower().removeprefix("www.")
    query = urlencode([(k, v) for k, v in parse_qsl(p.query)
                       if not k.startswith("utm_") and k not in TRACKING])
    return f"{host}{p.path.rstrip('/')}" + (f"?{query}" if query else "")


_DATE = re.compile(
    r"^((?:[A-Z][a-z]{2,8}\.? \d{1,2}, \d{4}|\d{1,2} [A-Z][a-z]{2,8}\.? \d{4}|\d+ (?:minutes?|hours?|days?|weeks?|months?|years?) ago))"
    r"\s*[·\-–—…:]\s*")


def tidy(snippet, title):
    """A snippet without the date engines put in front of it or the title they repeat.

    Returns (snippet, date)."""
    text, date = (snippet or "").strip(), ""
    m = _DATE.match(text)
    if m:
        date, text = m.group(1), text[m.end():]
    name = re.split(r"\s+[-|–—·:]\s+", title.strip())[0].rstrip(".…").strip()
    if len(name) > 12 and text.lower().startswith(name.lower()):
        text = text[len(name):].lstrip(" -–—:|·.")
    return text, date


def merge(per_engine):
    """Reciprocal-rank fusion: pages several engines agree on rise to the top."""
    seen, score = {}, {}
    for results in per_engine:
        for r in results:
            key = normalize(r.url)
            score[key] = score.get(key, 0) + 1 / (RRF_K + r.rank)
            if key not in seen:
                seen[key] = r
            else:
                kept = seen[key]
                for name in r.engines:
                    if name not in kept.engines:
                        kept.engines.append(name)
                if len(r.snippet) > len(kept.snippet):
                    kept.snippet = r.snippet
    ranked = [seen[k] for k in sorted(score, key=score.get, reverse=True)]
    for r in ranked:
        r.snippet, found = tidy(r.snippet, r.title)
        r.date = r.date or found
    return ranked


SECOND_LEVEL = {"co", "com", "org", "net", "gov", "edu", "ac"}


def site_of(url):
    """The site a result belongs to: reddit.com for old.reddit.com, bbc.co.uk for www.bbc.co.uk."""
    labels = (urlparse(url).hostname or "").lower().split(".")
    if len(labels) >= 3 and len(labels[-1]) == 2 and labels[-2] in SECOND_LEVEL:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


def collapse(results, per_site=2):
    """Keep at most `per_site` results from any one site, so one site can't fill a page."""
    if per_site <= 0:
        return results
    counts, kept = {}, []
    for r in results:
        site = site_of(r.url)
        counts[site] = counts.get(site, 0) + 1
        if counts[site] <= per_site:
            kept.append(r)
    return kept


def is_resting(name, now=None):
    until = resting.get(name, (0, 0))[0]
    return until > (now if now is not None else time.monotonic())


strikes = {}   # engine name -> failed searches in a row


def _failed(name):
    """Note a failure. The second one in a row sends the engine to rest, for longer each time."""
    strikes[name] = strikes.get(name, 0) + 1
    if strikes[name] >= 2:
        _, length = resting.get(name, (0, 0))
        length = min(max(length * 2, REST_FIRST), REST_MAX)
        resting[name] = (time.monotonic() + length, length)


def _worked(name):
    strikes.pop(name, None)
    resting.pop(name, None)


async def _attempt(engine, client, query, page, period=None, region=None, safe=None):
    """One engine, with one quick second try if it failed for a reason other than being slow."""
    for attempt in (1, 2):
        try:
            options = {}
            if period and period in getattr(engine, "SUPPORTS_TIME", ()):
                options["period"] = period
            if region and getattr(engine, "can_region", lambda code: False)(region):
                options["region"] = region
            if safe and getattr(engine, "SUPPORTS_SAFE", False):
                options["safe"] = safe
            results = await engine.search(client, query, page, **options)
        except (httpx.TimeoutException, asyncio.TimeoutError):
            break  # slow: a retry would only make the page slower
        except Exception:
            results = None
        if results or (results == [] and page > 1):
            _worked(engine.NAME)
            return results
        if attempt == 1:
            await asyncio.sleep(0.4)
    _failed(engine.NAME)
    return None


async def gather(client, engines, query, page=1, period=None, region=None, safe=None):
    """Ask every engine at once. Returns (merged results, names that failed or are resting)."""
    asking = [e for e in engines if not is_resting(e.NAME)]
    outcomes = await asyncio.gather(*(_attempt(e, client, query, page, period, region, safe) for e in asking))
    ok, failed = [], [e.NAME for e in engines if e not in asking]
    for engine, outcome in zip(asking, outcomes):
        if outcome is None:
            failed.append(engine.NAME)
        elif outcome:
            ok.append(outcome)
    return merge(ok), failed
