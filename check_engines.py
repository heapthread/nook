"""Asks every engine and news feed something real and says which ones still work.

    .venv/Scripts/python check_engines.py

Scrapers break when a site changes its pages, or just get turned away for a while. When an
engine fails here, run it again a bit later: if it keeps failing, its parser needs updating.
Exits with 1 if anything failed, so it can run on a schedule.
"""
import asyncio
import sys
import tomllib
from pathlib import Path

import httpx

import engines
import news
from engines import bing_images, duckduckgo_videos, wikipedia

ROOT = Path(__file__).parent
QUERY = "python tutorial"


def problem(results):
    if not results:
        return "no results (turned away, or the page changed)"
    first = results[0]
    url = getattr(first, "url", None) or getattr(first, "full", "")
    if not getattr(first, "title", "") or not str(url).startswith("http"):
        return "results are missing a title or address (the page changed)"
    return None


async def check_one(client, mod):
    try:
        return mod.NAME, problem(await mod.search(client, QUERY)), None
    except httpx.HTTPStatusError as e:
        return mod.NAME, f"the site answered {e.response.status_code}", None
    except Exception as e:
        return mod.NAME, f"{type(e).__name__}: {str(e)[:60]}", None


async def main():
    config = tomllib.loads((ROOT / "config.toml").read_text(encoding="utf-8"))
    wikipedia.CONTACT = config.get("contact", "")
    web = [m for m in engines.load(config["engines"]) if m is not wikipedia or wikipedia.CONTACT]
    failures = 0
    async with httpx.AsyncClient(headers=engines.HEADERS, follow_redirects=True, http2=True, timeout=15) as client:
        print("search engines")
        for mod in (*web, bing_images, duckduckgo_videos):
            name, bad, _ = await check_one(client, mod)
            print(f"  {'FAIL' if bad else 'ok  '} {name:20} {bad or ''}")
            failures += bool(bad)
        feeds = news.load_feeds(ROOT / "feeds.toml")
        print("news feeds")
        per_feed, failed = await news.gather(client, feeds, force=True)
        for feed in feeds:
            bad = feed["name"] in failed
            print(f"  {'FAIL' if bad else 'ok  '} {feed['name']:26} {feed['wing']}")
            failures += bad
    print(f"\n{failures} problem{'s' if failures != 1 else ''}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
