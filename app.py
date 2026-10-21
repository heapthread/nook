import asyncio
import os
import re
import secrets
import time
import tomllib
from pathlib import Path
from urllib.parse import urlparse

import httpx
from flask import (Flask, Response, abort, make_response, redirect, render_template, request,
                   send_from_directory)
from markupsafe import Markup, escape
from werkzeug.exceptions import HTTPException

import answers
import cards
import engines
import merge
import news
import places
import proxy
import regions
import related
import weather
import wordtools
import reader
from engines import bing_images, duckduckgo_videos, wikipedia

ROOT = Path(__file__).parent
config = tomllib.loads((ROOT / "config.toml").read_text(encoding="utf-8"))
active = engines.load(config["engines"])
wikipedia.CONTACT = config.get("contact", "")
if wikipedia in active and not wikipedia.CONTACT:
    active.remove(wikipedia)  # Wikipedia's API refuses requests that don't say who is asking
    print("nook: wikipedia is off until `contact` is set in config.toml")


def load_secret():
    """Signs picture and reader links. Made once and kept in .secret so links survive restarts."""
    if config.get("secret"):
        return config["secret"]
    path = ROOT / ".secret"
    try:
        saved = path.read_text(encoding="utf-8").strip()
        if saved:
            return saved
    except OSError:
        pass
    fresh = secrets.token_hex(32)
    try:
        path.write_text(fresh, encoding="utf-8")
    except OSError:
        pass  # read-only folder: links just won't outlive this run
    return fresh


proxy.configure(load_secret())
feeds = news.load_feeds(ROOT / "feeds.toml")

app = Flask(__name__)
app.config["TEMPLATES_AUTO_RELOAD"] = False
app.jinja_env.globals["px"] = proxy.link
app.jinja_env.globals["rd"] = proxy.read_link
app.jinja_env.globals["audio"] = proxy.audio_link
app.jinja_env.globals["compare"] = proxy.compare_link
app.jinja_env.filters["ago"] = news.ago

_TINY = {"a", "an", "the", "of", "in", "on", "at", "to", "for", "and", "or", "is", "it", "by", "as", "be"}


@app.template_filter("mark")
def mark(text, query):
    """The text with the words searched for in bold. Each piece is escaped on its own, so
    a search for "amp" or "39" can never break the markup."""
    query = re.sub(r"(?i)\b(?:site|filetype|intitle|inurl|ext):\S+", " ", query or "")
    words = {w.lower() for w in re.findall(r"[A-Za-z0-9]{2,}", query)} - _TINY
    if not words:
        return escape(text)
    pattern = re.compile(r"\b(" + "|".join(sorted(map(re.escape, words), key=len, reverse=True)) + r")\b", re.I)
    parts = pattern.split(text or "")
    return Markup("".join(f"<b>{escape(p)}</b>" if i % 2 else str(escape(p)) for i, p in enumerate(parts)))


@app.template_filter("host")
def host_of(url):
    return (urlparse(url).hostname or "").lower()

MEDIA = {"images": bing_images, "videos": duckduckgo_videos}

cache = {}      # (tab, query, page) -> (expires, results, failed)
last_good = {}  # (tab, query, page) -> (when, results): shown, marked as old, if nobody answers
hits = {}    # (bucket, visitor) -> recent request times

# Nothing on a nook page may reach another site on its own: pictures come through /img,
# and the only outside things allowed are YouTube's player (after a click) and video files.
CSP = ("default-src 'none'; img-src 'self'; style-src 'self'; "
       "script-src 'self' https://www.youtube.com; frame-src https://www.youtube-nocookie.com; "
       "media-src 'self' https: http:; connect-src 'self'; form-action 'self'; base-uri 'none'")


@app.after_request
def guard(resp):
    resp.headers["Referrer-Policy"] = "no-referrer"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Content-Security-Policy"] = CSP
    return resp


def too_busy(visitor, bucket="pages", limit=None):
    now = time.monotonic()
    key = (bucket, visitor)
    recent = [t for t in hits.get(key, []) if now - t < 60]
    recent.append(now)
    hits[key] = recent
    if len(hits) > 5000:
        hits.clear()
    return len(recent) > (limit or config["rate_limit_per_minute"])


def chosen_engines():
    """The engines this visitor switched on (kept in a cookie). Everything on if they never chose."""
    names = {n for n in (request.cookies.get("nook_engines") or "").split(".") if n}
    return [e for e in active if e.NAME in names] or list(active)


PERIODS = {"d": "past day", "w": "past week", "m": "past month", "y": "past year"}


def chosen_period():
    value = request.cookies.get("nook_period", "")
    return value if value in PERIODS else None


def chosen_region():
    value = request.cookies.get("nook_region", "")
    return value if value in regions.VALID else None


def chosen_safe():
    value = request.cookies.get("nook_safe", "")
    return value if value in ("strict", "off") else None


def clean_site(text):
    """'https://www.Pinterest.com/pin/1' -> 'pinterest.com'; anything that is not a site -> None."""
    t = re.sub(r"^[a-z][a-z0-9+.-]*://", "", (text or "").strip().lower())
    t = t.split("/")[0].split("?")[0].split("#")[0].removeprefix("www.")
    return t if len(t) <= 80 and re.fullmatch(r"[a-z0-9][a-z0-9.-]*\.[a-z]{2,}", t) else None


def site_list(kind):
    """The sites this browser hid or wants first (a cookie, '|' between them)."""
    seen = []
    for raw in request.cookies.get(f"nook_{kind}", "").split("|"):
        site = clean_site(raw)
        if site and site not in seen:
            seen.append(site)
    return seen[:30]


def on_site(url, sites):
    host = (urlparse(url).hostname or "").lower()
    return any(host == d or host.endswith("." + d) for d in sites)


def apply_sites(results):
    """Drop results from hidden sites and bring preferred sites to the front. Returns (results, hidden)."""
    hide, prefer = site_list("hide"), site_list("prefer")
    if not (hide or prefer):
        return results, 0
    address = lambda r: getattr(r, "url", None) or getattr(r, "page", "")
    kept = [r for r in results if not on_site(address(r), hide)]
    first = [r for r in kept if on_site(address(r), prefer)]
    return first + [r for r in kept if r not in first], len(results) - len(kept)


def can_do(engine, period, region, safe):
    """Can this engine apply the time filter, region and strict safe search that were asked for?"""
    if period and period not in getattr(engine, "SUPPORTS_TIME", ()):
        return False
    if region and not getattr(engine, "can_region", lambda code: False)(region):
        return False
    return not (safe == "strict" and not getattr(engine, "SUPPORTS_SAFE", False))


@app.context_processor
def engine_choices():
    on = {e.NAME for e in chosen_engines()}
    here = {e.NAME for e in active}
    return {"engine_choices": [(e.NAME, e.NAME in on) for e in active],
            "engines_skipped": [n for n in config["engines"] if n not in here],
            "periods": PERIODS, "period_now": chosen_period() or "",
            "regions": regions.REGIONS, "region_now": chosen_region() or "", "safe_now": chosen_safe() or "",
            "hide_now": "\n".join(site_list("hide")), "prefer_now": "\n".join(site_list("prefer"))}


async def ask(query, page=1, chosen=None, period=None, region=None, safe=None):
    async with httpx.AsyncClient(headers=engines.HEADERS, follow_redirects=True, http2=True,
                                 timeout=config["timeout"]) as client:
        results, failed = await merge.gather(client, chosen or active, query, page, period, region, safe)
    return merge.collapse(results, config.get("per_site", 2)), failed


async def ask_card(query, picked):
    """The definition / summary / conversion card, if the query wants one."""
    if not (cards.define_word(query) or cards.topic_of(query) or cards._currency(query.strip().lower())
            or places.unknown_places(query) or weather.place_in(query) or wordtools.parse(query)):
        return None
    async with httpx.AsyncClient(headers=engines.HEADERS, follow_redirects=True, http2=True, timeout=6) as client:
        try:
            # a summary comes from DuckDuckGo, so it is only asked for when that engine is on
            return await cards.lookup(client, query, with_knowledge=any(e.NAME == "duckduckgo" for e in picked))
        except Exception:
            return None


async def ask_related(query, picked):
    """Other searches people make, if the DuckDuckGo engine is on (it is the one asked)."""
    if not any(e.NAME == "duckduckgo" for e in picked):
        return []
    async with httpx.AsyncClient(headers=engines.HEADERS, follow_redirects=True, http2=True, timeout=4) as client:
        return await related.lookup(client, query)


async def web_and_card(query, page, picked, period=None, region=None, safe=None):
    if page != 1:
        results, failed = await ask(query, page, picked, period, region=region, safe=safe)
        return results, failed, None, []
    (results, failed), card, more_like = await asyncio.gather(
        ask(query, page, picked, period, region=region, safe=safe), ask_card(query, picked),
        ask_related(query, picked))
    return results, failed, card, more_like


@app.get("/")
def home():
    return render_template("home.html")


async def ask_media(engine, query, page=1, region=None, safe=None):
    options = {}
    if region and getattr(engine, "can_region", lambda code: False)(region):
        options["region"] = region
    if safe and getattr(engine, "SUPPORTS_SAFE", False):
        options["safe"] = safe
    async with httpx.AsyncClient(headers=engines.HEADERS, follow_redirects=True,
                                 timeout=config["timeout"] * 2) as client:
        try:
            return await engine.search(client, query, page, **options), []
        except Exception:
            return [], [engine.NAME]


def ident(result):
    """What makes two results the same thing, whichever tab they are on."""
    return merge.normalize(getattr(result, "url", None) or result.full)


def seen_before(tab, query, page, which):
    """Identities already shown on earlier pages (an engine may repeat itself when paged)."""
    seen = set()
    for earlier in range(1, page):
        hit = cache.get((tab, query, earlier, which))
        if hit:
            seen.update(ident(r) for r in hit[1])
    return seen


@app.get("/search")
def search():
    query = request.args.get("q", "").strip()[:200]
    tab = request.args.get("t", "web")
    if tab not in ("web", *MEDIA):
        tab = "web"
    if not query:
        return render_template("home.html")
    jump = answers.bang_target(query, config.get("bangs"))
    if jump:
        return redirect(jump)
    try:
        page = min(max(int(request.args.get("page", 1)), 1), 10)
    except ValueError:
        page = 1
    if too_busy(request.remote_addr):
        abort(429)
    picked = chosen_engines()
    period, region, safe, limit_note = (chosen_period() if tab == "web" else None), chosen_region(), chosen_safe(), ""
    limits = [PERIODS[period]] if period else []
    if region:
        limits.append(regions.LABELS[region])
    if safe == "strict":
        limits.append("strict safe search")
    if tab == "web" and limits:
        usable = [e for e in picked if can_do(e, period, region, safe)]
        if usable:  # only some engines can do all of that, so only those are asked
            if len(usable) < len(picked):
                limit_note = f"{', '.join(limits)}: only {' and '.join(e.NAME for e in usable)} can do that."
            picked = usable
        else:
            period = region = None  # none of the chosen engines can, so ask them without
            safe = None if safe == "strict" else safe
            limit_note = f"none of your engines can do {', '.join(limits)}, so it was left out."
    which = (",".join(e.NAME for e in picked) if tab == "web" else "") + f"|{period}|{region}|{safe}"
    key = (tab, query.lower(), page, which)
    asked = [e.NAME for e in picked] if tab == "web" else [MEDIA[tab].NAME]
    hit = cache.get(key)
    card, similar = None, []
    if hit and hit[0] > time.monotonic():
        _, results, failed, card, similar = hit
    else:
        if tab == "web":
            results, failed, card, similar = asyncio.run(web_and_card(query, page, picked, period, region, safe))
        else:
            results, failed = asyncio.run(ask_media(MEDIA[tab], query, page, region=region, safe=safe))
        if page > 1:
            seen = seen_before(tab, query.lower(), page, which)
            results = [r for r in results if ident(r) not in seen]
        if results or not failed:  # never remember a page that only came back empty by failing
            if len(cache) > 200:
                cache.clear()
            cache[key] = (time.monotonic() + config["cache_seconds"], results, failed, card, similar)
        if results:
            if len(last_good) > 300:
                last_good.clear()
            last_good[key] = (time.time(), results)
    results, hidden_count = apply_sites(results)
    stale = None
    old = last_good.get(key)
    if not results and old and len(failed) == len(asked) and time.time() - old[0] < 86400:
        results, stale = old[1], max(1, int((time.time() - old[0]) // 60))
    if tab == "web":
        answered = [n for n in asked if any(n in r.engines for r in results)] if not stale else []
    else:
        answered = asked if results and not stale else []
    instant = answers.answer(query) if tab == "web" and page == 1 else None
    if tab == "web" and page == 1:
        card = cards.local(query) or card  # time, dice and timers are worked out fresh every time
    else:
        card = None
    # Bing's image results do not page for us, so offer no "more" there
    more = bool(results) and tab != "images"
    return render_template("results.html", q=query, tab=tab, page=page, results=results,
                           failed=failed, answered=answered, asked=asked, more=more,
                           stale=stale, instant=instant, card=card,
                           icons=any(e.NAME == "duckduckgo" for e in picked), limit_note=limit_note,
                           hidden_count=hidden_count, similar=similar if page == 1 and tab == "web" else [])


@app.post("/engines")
def set_engines():
    """Remember which engines this browser wants. A cookie, so there is no account or page of settings."""
    on = [e.NAME for e in active if e.NAME in request.form.getlist("engine")]
    back = request.form.get("next", "/")
    if not back.startswith("/") or back.startswith("//") or "\\" in back:
        back = "/"
    resp = redirect(back, 303)
    period = request.form.get("period", "")
    if period in PERIODS:
        resp.set_cookie("nook_period", period, max_age=31536000, samesite="Lax")
    else:
        resp.delete_cookie("nook_period")
    for field in ("hide", "prefer"):
        sites = []
        for line in re.split(r"[\s,;]+", request.form.get(field, "")):
            site = clean_site(line)
            if site and site not in sites:
                sites.append(site)
        if sites:
            resp.set_cookie(f"nook_{field}", "|".join(sites[:30]), max_age=31536000, samesite="Lax")
        else:
            resp.delete_cookie(f"nook_{field}")
    for field, valid in (("region", regions.VALID), ("safe", ("strict", "off"))):
        value = request.form.get(field, "")
        if value in valid:
            resp.set_cookie(f"nook_{field}", value, max_age=31536000, samesite="Lax")
        else:
            resp.delete_cookie(f"nook_{field}")
    if on and len(on) < len(active):
        resp.set_cookie("nook_engines", ".".join(on), max_age=31536000, samesite="Lax")
    else:
        resp.delete_cookie("nook_engines")  # nothing, or everything, picked: back to the default
    return resp


@app.post("/sites")
def one_site():
    """The small "hide site" button on a result: add one site to this browser's hidden list."""
    site = clean_site(request.form.get("site", ""))
    if not site:
        abort(400)
    sites = site_list("hide")
    if site not in sites:
        sites.append(site)
    resp = Response(status=204)
    resp.set_cookie("nook_hide", "|".join(sites[-30:]), max_age=31536000, samesite="Lax")
    return resp


@app.get("/audio")
def audio_clip():
    if too_busy(request.remote_addr, "pictures", config.get("picture_limit_per_minute", 600)):
        abort(429)
    url = request.args.get("u", "")
    if not proxy.verify(url, request.args.get("s"), "audio"):
        abort(403)
    try:
        body, kind = proxy.fetch_audio(url)
    except (proxy.Refused, httpx.HTTPError):
        abort(502)
    return Response(body, mimetype=kind, headers={"Cache-Control": "public, max-age=86400"})


@app.get("/img")
def img():
    if too_busy(request.remote_addr, "pictures", config.get("picture_limit_per_minute", 600)):
        abort(429)
    url = request.args.get("u", "")
    if not proxy.verify(url, request.args.get("s")):
        abort(403)
    try:
        body, kind = proxy.fetch(url)
    except (proxy.Refused, httpx.HTTPError):
        abort(502)
    return Response(body, mimetype=kind, headers={"Cache-Control": "public, max-age=86400"})


async def ask_news(selected):
    async with httpx.AsyncClient(headers=engines.HEADERS, follow_redirects=True,
                                 timeout=config["timeout"] * 1.5) as client:
        return await news.gather(client, selected)


@app.get("/news")
def news_page():
    saved = (request.cookies.get("nook_news") or "centre|0").split("|")
    wing = request.args.get("w", saved[0])
    if wing not in (*news.WINGS, "all"):
        wing = "centre"
    pics = request.args.get("p", saved[1] if len(saved) > 1 else "0") == "1"
    if too_busy(request.remote_addr):
        abort(429)
    selected = [f for f in feeds if wing == "all" or f["wing"] == wing]
    # every wing is fetched (they are kept warm anyway) so a story can point at how the others told it
    everything, failed_all = asyncio.run(ask_news(feeds))
    names = {f["name"] for f in selected}
    failed = [n for n in failed_all if n in names]
    flat = [s for lst in everything for s in lst]
    q = request.args.get("q", "").strip()[:100]
    if q:  # searching the news: every story in the feeds, not just the newest from each outlet
        hits = news.matching(flat, q)
        if wing == "all":
            stories = news.top_stories(hits, hours=24 * 14)
        else:
            stories = news.with_coverage([s for s in hits if s.wing == wing][:60], flat)
    elif wing == "all":
        stories = news.top_stories(flat)
    else:
        per_feed = [lst for lst in everything if lst[0].wing == wing]
        stories = news.with_coverage(news.mix(per_feed, 8, 60), flat)
    resp = make_response(render_template(
        "news.html", wing=wing, pics=pics, stories=stories, failed=failed, q=q,
        wings=["all", *news.WINGS], sources=[f["name"] for f in selected]))
    resp.set_cookie("nook_news", f"{wing}|{int(pics)}", max_age=31536000, samesite="Lax")
    return resp


@app.get("/compare")
def compare_page():
    """One story, told by every outlet we have that ran it, grouped by wing."""
    url = request.args.get("u", "")
    if not proxy.verify(url, request.args.get("s"), "compare"):
        abort(403)
    if too_busy(request.remote_addr):
        abort(429)
    wing = request.args.get("w", "all")
    if wing not in (*news.WINGS, "all"):
        wing = "all"
    lead = news.find(url)
    if lead is None:
        return render_template("message.html", text="that story has moved on. open news again."), 404
    told = [lead, *news.with_coverage([lead], news.all_cached(), cap=14)[0].also]
    by_wing = [(w, [t for t in told if t.wing == w]) for w in news.WINGS]
    return render_template("compare.html", lead=lead, groups=[g for g in by_wing if g[1]],
                           missing=[w for w, stories in by_wing if not stories], wing=wing, count=len(told))


@app.get("/read")
def read():
    url = request.args.get("u", "")
    if not proxy.verify(url, request.args.get("s"), "read"):
        abort(403)
    if too_busy(request.remote_addr):
        abort(429)
    wing = request.args.get("w", "centre")
    if wing not in (*news.WINGS, "all"):
        wing = "centre"
    pics = (request.cookies.get("nook_news") or "|0").split("|")[-1] == "1"
    story = news.find(url)
    paras, how = reader.article(url, story.full if story else "")
    host = urlparse(url).netloc.removeprefix("www.")
    q = request.args.get("q", "")[:200]
    if story is None:  # a search result, or a story no longer in the feed cache
        story = news.Story(title=request.args.get("t", "")[:200] or host, url=url, source=host, wing=wing)
    words = sum(len(p.split()) for p in paras)
    return render_template("read.html", story=story, paras=paras, how=how, wing=wing, pics=pics,
                           host=host, q=q, minutes=max(1, round(words / 230)) if how != "partial" else 0)


YOUTUBE = re.compile(
    r"^https?://(?:www\.|m\.)?(?:youtube\.com/(?:watch\?(?:.*&)?v=|embed/|shorts/)|youtu\.be/)([\w-]{11})")
FILE = re.compile(r"^https?://[^\s]+\.(?:mp4|webm|ogv)(?:\?[^\s]*)?$", re.I)


@app.get("/watch")
def watch():
    url = request.args.get("v", "")
    q = request.args.get("q", "")[:200]
    title = request.args.get("title", "")[:200]
    m = YOUTUBE.match(url)
    poster = ""
    if m:
        kind, source = "youtube", m.group(1)
        poster = f"https://i.ytimg.com/vi/{source}/hqdefault.jpg"
    elif FILE.match(url):
        kind, source = "file", url
    else:
        return render_template("message.html", text="this one can't play here."), 404
    return render_template("watch.html", kind=kind, source=source, url=url, title=title, q=q,
                           poster=poster)


@app.get("/opensearch.xml")
def opensearch():
    base = request.host_url.rstrip("/")
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<OpenSearchDescription xmlns="http://a9.com/-/spec/opensearch/1.1/">
  <ShortName>nook</ShortName>
  <Description>a quiet search page</Description>
  <InputEncoding>UTF-8</InputEncoding>
  <Url type="text/html" method="get" template="{base}/search?q={{searchTerms}}"/>
</OpenSearchDescription>"""
    return Response(xml, mimetype="application/opensearchdescription+xml")


@app.get("/about")
def about():
    return render_template("about.html", engines=[e.NAME for e in active], outlets=len(feeds))


@app.get("/favicon.ico")
def favicon():
    return send_from_directory(app.static_folder, "favicon.svg", mimetype="image/svg+xml")


SAID = {
    403: "that link isn't one nook gave out.",
    404: "nothing lives here.",
    405: "that isn't something nook does.",
    429: "a little too fast. give it a minute.",
    500: "something went wrong on nook's side. try again in a moment.",
    502: "couldn't fetch that one.",
}


@app.errorhandler(Exception)
def friendly(error):
    code = error.code if isinstance(error, HTTPException) else 500
    return render_template("message.html", text=SAID.get(code, "something went wrong.")), code


if __name__ == "__main__":
    from waitress import serve
    port = int(os.environ.get("PORT", config["port"]))
    print(f"nook on http://{config['host']}:{port}")
    minutes = config.get("news_refresh_minutes", 8)
    if minutes and feeds:
        news.keep_warm(feeds, engines.HEADERS, config["timeout"] * 1.5, minutes)
    # pictures are fetched one request each, so allow plenty of threads
    serve(app, host=config["host"], port=port, threads=16)
