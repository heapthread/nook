import asyncio
import os
import re
import secrets
import time
import tomllib
from pathlib import Path
from collections import Counter
from urllib.parse import quote, unquote, urlparse
from xml.sax.saxutils import escape as xml_escape

import httpx
from flask import (Flask, Response, abort, jsonify, make_response, redirect, render_template, request,
                   send_from_directory, stream_with_context)
from markupsafe import Markup, escape
from werkzeug.exceptions import HTTPException

import answers
import books
import cards
import codesearch
import converter
import daterange
import dates
import check_engines
import earth
import engines
import facts
import forecast
import history
import lenses
import mapstyle
import maps
import me
import merge
import nearby
import netinfo
import news
import packages
import places
import proxy
import regions
import related
import routes
import tools
import translate
import vtiles
import weather
import wiki
import wordtools
import reader
from engines import bing_images, duckduckgo_videos, wikipedia

ROOT = Path(__file__).parent
config = tomllib.loads((ROOT / "config.toml").read_text(encoding="utf-8"))
if os.environ.get("NOOK_CONTACT"):
    config["contact"] = os.environ["NOOK_CONTACT"]
active = engines.load(config["engines"])
wikipedia.CONTACT = config.get("contact", "")
wiki.CONTACT = config.get("contact", "")
proxy.CONTACT = config.get("contact", "")
vtiles.configure(config.get("contact", ""))
maps.configure(config.get("tile_url"), config.get("map_credit"), config.get("map_credit_url"), config.get("contact", ""))
if wikipedia in active and not wikipedia.CONTACT:
    active.remove(wikipedia)  # Wikipedia's API refuses requests that don't say who is asking
    print("nook: wikipedia is off until `contact` is set in config.toml")


def load_secret():
    """Signs picture and reader links. Made once and kept in .secret so links survive restarts."""
    if os.environ.get("NOOK_SECRET"):   # hosts with no writable disk (Vercel and the like) set it here
        return os.environ["NOOK_SECRET"]
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
LENSES = lenses.table(config.get("lenses"))

app = Flask(__name__)
app.config["TEMPLATES_AUTO_RELOAD"] = False
app.jinja_env.globals["px"] = proxy.link
app.jinja_env.globals["rd"] = proxy.read_link
app.jinja_env.globals["audio"] = proxy.audio_link
app.jinja_env.globals["compare"] = proxy.compare_link
app.jinja_env.filters["ago"] = news.ago
app.jinja_env.globals["map_credit"] = maps.CREDIT
app.jinja_env.globals["map_credit_url"] = maps.CREDIT_URL

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


@app.template_filter("crumbs")
def crumbs(url):
    """'https://en.wikipedia.org/wiki/Bonn' -> 'en.wikipedia.org › wiki › Bonn': the address as a trail."""
    p = urlparse(url)
    trail = [unquote(x)[:26] for x in p.path.split("/") if x][:3]
    return " \u203a ".join([(p.hostname or "").removeprefix("www.")] + trail)


FORUMS = ("reddit.com", "news.ycombinator.com", "stackoverflow.com", "stackexchange.com", "quora.com", "lemmy.world")
VIDEO_SITES = ("youtube.com", "youtu.be", "vimeo.com", "dailymotion.com", "twitch.tv")


@app.template_filter("kind")
def kind_of(url):
    """A small label for results that are not an ordinary page: pdf, video, forum."""
    p = urlparse(url)
    host = (p.hostname or "").lower()
    if p.path.lower().endswith(".pdf"):
        return "pdf"
    if any(host == d or host.endswith("." + d) for d in VIDEO_SITES):
        return "video"
    if any(host == d or host.endswith("." + d) for d in FORUMS):
        return "forum"
    return None


@app.template_filter("ytid")
def youtube_id(url):
    m = YOUTUBE.match(url or "")
    return m.group(1) if m else ""

MEDIA = {"images": bing_images, "videos": duckduckgo_videos}
STREAM_MARK = "<!--stream-->"

cache = {}      # (tab, query, page) -> (expires, results, failed)
last_good = {}  # (tab, query, page) -> (when, results): shown, marked as old, if nobody answers
hits = {}    # (bucket, visitor) -> recent request times

# Nothing on a nook page may reach another site on its own: pictures come through /img,
# and the only outside things allowed are YouTube's player (after a click) and video files.
CSP = ("default-src 'none'; img-src 'self' data: blob:; style-src 'self'; worker-src 'self' blob:; "
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


def setting(arg, cookie):
    """A setting: the link's own value when it carries one (a shared link), else this browser's cookie."""
    if arg in request.args:
        return request.args.get(arg, "")
    return request.cookies.get(cookie, "")


def chosen_engines():
    """The engines this visitor switched on (kept in a cookie). Everything on if they never chose."""
    names = {n for n in (setting("eng", "nook_engines") or "").split(".") if n}
    return [e for e in active if e.NAME in names] or list(active)


PERIODS = {"d": "past day", "w": "past week", "m": "past month", "y": "past year"}


def chosen_period():
    value = setting("per", "nook_period")
    return value if value in PERIODS else None


def chosen_region():
    value = setting("reg", "nook_region")
    return value if value in regions.VALID else None


def chosen_safe():
    value = setting("saf", "nook_safe")
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


def can_do(engine, period, region, safe, date_range=None):
    """Can this engine apply the time filter, date range, region and strict safe search that were asked for?"""
    if period and period not in getattr(engine, "SUPPORTS_TIME", ()):
        return False
    if date_range and not getattr(engine, "SUPPORTS_RANGE", False):
        return False
    if region and not getattr(engine, "can_region", lambda code: False)(region):
        return False
    return not (safe == "strict" and not getattr(engine, "SUPPORTS_SAFE", False))


def share_params():
    """This browser's non-default search settings as link parameters, for the "share" button."""
    parts = []
    names = [e.NAME for e in chosen_engines()]
    if len(names) < len(active):
        parts.append("eng=" + ".".join(names))
    for key, value in (("per", chosen_period()), ("reg", chosen_region()), ("saf", chosen_safe())):
        if value:
            parts.append(f"{key}={value}")
    return "&".join(parts)


@app.context_processor
def engine_choices():
    on = {e.NAME for e in chosen_engines()}
    here = {e.NAME for e in active}
    return {"engine_choices": [(e.NAME, e.NAME in on) for e in active],
            "engines_skipped": [n for n in config["engines"] if n not in here],
            "periods": PERIODS, "period_now": chosen_period() or "",
            "regions": regions.REGIONS, "region_now": chosen_region() or "", "safe_now": chosen_safe() or "",
            "hide_now": "\n".join(site_list("hide")), "prefer_now": "\n".join(site_list("prefer")),
            "share": share_params(),
            "carry": ("&" + share_params()) if share_params() and any(k in request.args for k in ("eng", "per", "reg", "saf")) else "",
            "pics_on": request.cookies.get("nook_pics") != "off",
            "newtab_on": request.cookies.get("nook_tab") == "new",
            "suggest_on": request.cookies.get("nook_suggest") != "off"}


async def ask(query, page=1, chosen=None, period=None, region=None, safe=None, date_range=None):
    async with httpx.AsyncClient(headers=engines.HEADERS, follow_redirects=True, http2=True,
                                 timeout=config["timeout"]) as client:
        results, failed = await merge.gather(client, chosen or active, query, page, period, region, safe, date_range)
    return merge.collapse(results, config.get("per_site", 2)), failed


async def ask_card(query, picked):
    """The definition / summary / conversion card, if the query wants one."""
    if not (cards.define_word(query) or cards.topic_of(query) or cards._currency(query.strip().lower())
            or places.unknown_places(query) or weather.place_in(query) or wordtools.parse(query)
            or translate.parse(query) or facts.parse(query)
            or routes.parse(query) or earth.parse(query) or history.parse(query)
            or packages.parse(query) or netinfo.parse(query) or nearby.parse(query)):
        return None
    async with httpx.AsyncClient(headers=engines.HEADERS, follow_redirects=True, http2=True, timeout=6) as client:
        try:
            # Wikipedia answers in the language of the chosen region; DuckDuckGo's summary is the
            # fallback, and is only asked for when that engine is on
            return await cards.lookup(client, query, with_knowledge=any(e.NAME == "duckduckgo" for e in picked),
                                      lang=wiki.lang_for(chosen_region()))
        except Exception:
            return None


async def ask_suggestion(query):
    """Wikipedia's "did you mean" for a search that found little."""
    async with httpx.AsyncClient(headers=engines.HEADERS, follow_redirects=True, http2=True, timeout=3) as client:
        return await wiki.suggestion(client, query, wiki.lang_for(chosen_region()))


async def ask_related(query, picked):
    """Other searches people make, if the DuckDuckGo engine is on (it is the one asked)."""
    if not any(e.NAME == "duckduckgo" for e in picked):
        return []
    async with httpx.AsyncClient(headers=engines.HEADERS, follow_redirects=True, http2=True, timeout=4) as client:
        return await related.lookup(client, query)


async def nothing():
    return None


spelling = {}   # query -> the spelling Wikipedia suggests instead, or None


async def web_and_card(query, page, picked, period=None, region=None, safe=None, engine_query=None, date_range=None):
    """`engine_query` is what the engines hear when a lens narrows the search; cards and related
    searches are then left out, since they answer the plain question."""
    heard = engine_query or query
    if page != 1:
        results, failed = await ask(heard, page, picked, period, region=region, safe=safe, date_range=date_range)
        return results, failed, None, []
    if engine_query:
        (results, failed), _ = await asyncio.gather(
            ask(heard, page, picked, period, region=region, safe=safe, date_range=date_range), nothing())
        return results, failed, None, []
    (results, failed), card, more_like, said = await asyncio.gather(
        ask(heard, page, picked, period, region=region, safe=safe, date_range=date_range), ask_card(query, picked),
        ask_related(query, picked), ask_suggestion(query))
    if len(spelling) > 500:
        spelling.clear()
    spelling[query.lower()] = said   # a typo's correction, shown only when nothing else answered
    return results, failed, card, more_like


@app.get("/")
def home():
    return render_template("home.html")


async def ask_media(engine, query, page=1, region=None, safe=None, filters=None):
    options = dict(filters or {}) if getattr(engine, "SUPPORTS_FILTERS", False) else {}
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
    lens = request.args.get("l", "") if tab == "web" else ""
    if lens not in LENSES:
        lens = ""
    # before:2020 / after:2023-05 / during:2021 are taken out of the words and become a date range
    asked_for, date_range = daterange.parse(query) if tab == "web" else (query, None)
    engine_query = (lenses.apply(asked_for, LENSES[lens]) if lens else (asked_for if date_range else None))
    period, region, safe, limit_note = (chosen_period() if tab == "web" else None), chosen_region(), chosen_safe(), ""
    limits = [PERIODS[period]] if period else []
    if date_range:
        limits.append(f"{date_range[0]} to {date_range[1]}")
    if region:
        limits.append(regions.LABELS[region])
    if safe == "strict":
        limits.append("strict safe search")
    if tab == "web" and limits:
        usable = [e for e in picked if can_do(e, period, region, safe, date_range)]
        if usable:  # only some engines can do all of that, so only those are asked
            if len(usable) < len(picked):
                limit_note = f"{', '.join(limits)}: only {' and '.join(e.NAME for e in usable)} can do that."
            picked = usable
        else:
            period = region = date_range = None  # none of the chosen engines can, so ask them without
            engine_query = lenses.apply(asked_for, LENSES[lens]) if lens else asked_for
            safe = None if safe == "strict" else safe
            limit_note = f"none of your engines can do {', '.join(limits)}, so it was left out."
    image_now = {}
    if tab == "images":   # size, kind and colour of pictures: only values Bing's filters know
        for field, arg, table in (("size", "sz", bing_images.SIZES), ("kind", "ty", bing_images.KINDS),
                                  ("colour", "co", bing_images.COLOURS)):
            if request.args.get(arg, "") in table:
                image_now[field] = request.args[arg]
    which = (",".join(e.NAME for e in picked) if tab == "web" else "") + f"|{period}|{region}|{safe}|{lens}|{sorted(image_now.items())}|{date_range}"
    spot = None
    if tab == "web" and "ll" in request.args:
        try:
            lat, lon = (float(v) for v in request.args["ll"].split(","))
            if -85 < lat < 85 and -180 <= lon <= 180:
                spot = (round(lat, 3), round(lon, 3))      # about a hundred metres is plenty
        except ValueError:
            pass
    nearby.here.set(spot)
    which += f"|{spot}"
    key = (tab, query.lower(), page, which)
    asked = [e.NAME for e in picked] if tab == "web" else [MEDIA[tab].NAME]
    started = time.monotonic()
    fixed = dict(q=query, tab=tab, page=page, asked=asked, icons=any(e.NAME == "duckduckgo" for e in picked),
                 limit_note=limit_note, lens=lens, lens_names=list(LENSES), lens_sites=LENSES.get(lens, []),
                 image_now=image_now, image_options={"sizes": list(bing_images.SIZES), "kinds": list(bing_images.KINDS),
                                                     "colours": list(bing_images.COLOURS)})

    def build():
        """Ask the engines (or remember what they said) and gather everything the page shows."""
        hit = cache.get(key)
        card, similar, took = None, [], None
        if hit and hit[0] > time.monotonic():
            _, results, failed, card, similar = hit
        else:
            if tab == "web":
                results, failed, card, similar = asyncio.run(
                    web_and_card(query, page, picked, period, region, safe, engine_query, date_range))
            else:
                results, failed = asyncio.run(ask_media(MEDIA[tab], query, page, region=region, safe=safe,
                                                      **({"filters": image_now} if image_now else {})))
            took = round(time.monotonic() - started, 1)
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
        instant = answers.answer(query) if tab == "web" and page == 1 and not lens else None
        if tab == "web" and page == 1 and not lens:
            card = me.answer(query, request.remote_addr, request.headers.get("User-Agent", "")) or cards.local(query) or card
        else:
            card = None
        said = spelling.get(query.lower()) if tab == "web" and page == 1 and not lens and not card else None
        return dict(fixed, results=results, failed=failed, answered=answered,
                    more=bool(results) and tab != "images",   # Bing's image results do not page for us
                    stale=stale, instant=instant, card=card, hidden_count=hidden_count,
                    similar=similar if page == 1 and tab == "web" else [], didyoumean=said, took=took)

    waiting = cache.get(key) is None or cache[key][0] <= time.monotonic()
    if not waiting or request.args.get("stream") == "0":
        return render_template("results.html", **build())

    # Nothing is remembered yet, so the engines will take a moment. Send the top of the page (the
    # search box, the tabs) straight away and the rest when it is ready.
    empty = dict(fixed, results=[], failed=[], answered=[], more=False, stale=None, instant=None, card=None,
                 hidden_count=0, similar=[], didyoumean=None, took=None)
    top = render_template("results.html", **empty).split(STREAM_MARK)[0]

    def stream():
        yield top + STREAM_MARK + '<p class="loading">asking the engines&hellip;</p>'
        try:
            page_html = render_template("results.html", **build())
        except Exception:
            yield '<span class="loaded"></span><p class="note">something went wrong on nook\'s side. try again in a moment.</p></main></body></html>'
            return
        yield page_html.split(STREAM_MARK, 1)[1]
    return Response(stream_with_context(stream()), mimetype="text/html")


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
    if request.form.get("newtab") == "new":
        resp.set_cookie("nook_tab", "new", max_age=31536000, samesite="Lax")
    else:
        resp.delete_cookie("nook_tab")
    for field in ("pics", "suggest"):  # both are on unless the cookie says "off"
        if request.form.get(field) == "off":
            resp.set_cookie(f"nook_{field}", "off", max_age=31536000, samesite="Lax")
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
    kind = request.form.get("kind", "hide")
    if not site or kind not in ("hide", "prefer"):
        abort(400)
    other = "prefer" if kind == "hide" else "hide"
    sites = site_list(kind)
    if site not in sites:
        sites.append(site)
    resp = Response(status=204)
    resp.set_cookie(f"nook_{kind}", "|".join(sites[-30:]), max_age=31536000, samesite="Lax")
    kept = [s for s in site_list(other) if s != site]   # a site is either hidden or favoured, never both
    if kept:
        resp.set_cookie(f"nook_{other}", "|".join(kept), max_age=31536000, samesite="Lax")
    else:
        resp.delete_cookie(f"nook_{other}")
    return resp


@app.get("/tile/<int:z>/<int:x>/<int:y>.png")
def map_tile(z, x, y):
    """One square of a map, fetched from the tile server and remembered."""
    if not maps.valid_tile(z, x, y):
        abort(404)
    if too_busy(request.remote_addr, "pictures", config.get("picture_limit_per_minute", 600)):
        abort(429)
    try:
        body = maps.tile(z, x, y)
    except (httpx.HTTPError, ValueError):
        abort(502)
    return Response(body, mimetype="image/png", headers={"Cache-Control": "public, max-age=604800"})


def _float(name, low, high):
    try:
        value = float(request.args.get(name, ""))
    except ValueError:
        return None
    return value if low <= value <= high else None


@app.get("/maps")
def maps_page():
    q = request.args.get("q", "").strip()[:120]
    if too_busy(request.remote_addr):
        abort(429)
    places, failed, picked = [], False, 0
    if q:
        try:
            places = maps.search(q, wiki.lang_for(chosen_region()))
        except (httpx.HTTPError, ValueError):
            failed = True
        try:
            picked = min(max(int(request.args.get("i", 0)), 0), max(len(places) - 1, 0))
        except ValueError:
            picked = 0
    markers = [{"lat": p["lat"], "lon": p["lon"], "label": p["name"], "on": n == picked,
                "href": f"/maps?q={quote(q)}&i={n}"} for n, p in enumerate(places)]
    lat, lon, zoom, name = _float("lat", -85, 85), _float("lon", -180, 180), _float("z", 2, 18),         request.args.get("name", "")[:80]
    if places:
        lat, lon, zoom = places[picked]["lat"], places[picked]["lon"], places[picked]["zoom"]
    elif lat is not None and lon is not None:
        zoom = int(zoom or 12)
        markers = [{"lat": lat, "lon": lon, "label": name, "on": True}]
    else:
        lat, lon, zoom = 25.0, 10.0, 2
    return render_template("maps.html", q=q, places=places, picked=picked, failed=failed, markers=markers,
                           lat=lat, lon=lon, zoom=zoom, name=name)


@app.get("/mapstyle/<theme>.json")
def map_style(theme):
    if theme not in ("light", "dark"):
        abort(404)
    resp = jsonify(mapstyle.style(theme, ""))          # addresses are relative; the page adds its own origin
    resp.add_etag()
    resp.cache_control.no_cache = True                 # always ask, so a restyle shows up; a 304 costs nothing
    return resp.make_conditional(request)


@app.get("/vt/<int:z>/<int:x>/<int:y>")
def vector_tile(z, x, y):
    if not vtiles.valid_tile(z, x, y):
        abort(404)
    if too_busy(request.remote_addr, "pictures", config.get("picture_limit_per_minute", 600) * 2):
        abort(429)
    try:
        body = vtiles.tile(z, x, y)
    except (httpx.HTTPError, ValueError, KeyError, IndexError):
        abort(502)
    return Response(body, mimetype="application/x-protobuf", headers={"Cache-Control": "public, max-age=86400"})


@app.get("/glyphs/<stack>/<rng>")
def map_glyphs(stack, rng):
    try:
        body = vtiles.font(stack, rng.removesuffix(".pbf"))
    except ValueError:
        abort(404)
    except httpx.HTTPError:
        abort(502)
    return Response(body, mimetype="application/x-protobuf", headers={"Cache-Control": "public, max-age=604800"})


def get_place(pid):
    try:
        return nearby.get(pid)
    except httpx.HTTPError:
        return None


@app.get("/place/<pid>")
def place_page(pid):
    if too_busy(request.remote_addr, "place", 30):
        abort(429)
    place = get_place(pid)
    if place is None:
        return render_template("message.html", text="couldn't find that place. it may have been removed from the map."), 404
    q = request.args.get("q", "")[:120]
    city = place["town"] or place["address"].split(", ")[-1]
    return render_template("place.html", place=place, q=q, reviews=f"{place['name']} {city} reviews".strip(),
                           osm=f"https://www.openstreetmap.org/{ {'N': 'node', 'W': 'way', 'R': 'relation'}[pid[0]] }/{pid[1:]}")


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


traffic = {}   # visitor -> (window start, bytes passed on): nook is not a free download service


def over_budget(visitor, spent=0):
    """Has this visitor had their share of picture bytes this minute? Adds `spent` first."""
    now = time.monotonic()
    start, used = traffic.get(visitor, (now, 0))
    if now - start > 60:
        start, used = now, 0
    used += spent
    traffic[visitor] = (start, used)
    if len(traffic) > 5000:
        traffic.clear()
    return used > config.get("picture_mb_per_minute", 60) * 1_000_000


@app.get("/img")
def img():
    if too_busy(request.remote_addr, "pictures", config.get("picture_limit_per_minute", 600)) or over_budget(request.remote_addr):
        abort(429)
    url = request.args.get("u", "")
    if not proxy.verify(url, request.args.get("s")):
        abort(403)
    try:
        body, kind = proxy.fetch(url)
    except (proxy.Refused, httpx.HTTPError):
        abort(502)
    over_budget(request.remote_addr, len(body))
    return Response(body, mimetype=kind, headers={"Cache-Control": "public, max-age=86400"})


async def ask_news(selected):
    async with httpx.AsyncClient(headers=engines.HEADERS, follow_redirects=True,
                                 timeout=config["timeout"] * 1.5) as client:
        return await news.gather(client, selected)


@app.get("/news")
def news_page():
    saved = (request.cookies.get("nook_news") or "centre|0").split("|")
    wing = request.args.get("w", saved[0])
    if wing not in (*news.WINGS, "all", "mine"):
        wing = "centre"
    pics = request.args.get("p", saved[1] if len(saved) > 1 else "0") == "1"
    if too_busy(request.remote_addr):
        abort(429)
    if wing == "mine":
        return my_news(pics)
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
        wings=["all", *news.WINGS, "mine"], sources=[f["name"] for f in selected]))
    resp.set_cookie("nook_news", f"{wing}|{int(pics)}", max_age=31536000, samesite="Lax")
    return resp


MINE_MAX = 6
_mine = {}  # feed address -> (when, stories)


def my_feed_urls():
    """The feeds this browser added (a cookie): addresses, '|' between them."""
    out = []
    for raw in request.cookies.get("nook_myfeeds", "").split("|"):
        url = unquote(raw).strip()
        if url.startswith(("http://", "https://")) and url not in out:
            out.append(url)
    return out[:MINE_MAX]


def load_mine(url):
    """The stories of one added feed, or None. The address is the visitor's, so it must be a public one."""
    hit = _mine.get(url)
    if hit and time.monotonic() - hit[0] < 600:
        return hit[1]
    try:
        xml = proxy.fetch_feed(url)
        stories = news.parse(xml, news.feed_title(xml) or (urlparse(url).hostname or url), "mine")
    except Exception:
        return hit[1] if hit else None
    if len(_mine) > 200:
        _mine.clear()
    if stories:
        _mine[url] = (time.monotonic(), stories)
    return stories or None


def my_news(pics):
    from concurrent.futures import ThreadPoolExecutor
    urls = my_feed_urls()
    with ThreadPoolExecutor(max_workers=MINE_MAX) as pool:
        loaded = list(pool.map(load_mine, urls))
    stories = news.mix([s for s in loaded if s], 10, 60)
    failed = [urlparse(u).hostname or u for u, s in zip(urls, loaded) if not s]
    return render_template("news.html", wing="mine", pics=pics, stories=stories, failed=failed, q="",
                           wings=["all", *news.WINGS, "mine"], sources=[], my_urls=urls,
                           feed_error=request.args.get("e", ""))


@app.post("/feeds")
def feeds_edit():
    """Add or remove one of this browser's own news feeds."""
    urls = my_feed_urls()
    url = request.form.get("url", "").strip()[:300]
    error = ""
    if request.form.get("act") == "remove":
        urls = [u for u in urls if u != url]
    elif not url.startswith(("http://", "https://")):
        error = "that doesn't look like a web address."
    elif len(urls) >= MINE_MAX:
        error = f"that's {MINE_MAX} feeds already. remove one first."
    elif not proxy.is_public(url):
        error = "nook can't reach that address."
    elif url not in urls:
        urls.append(url)
    resp = redirect("/news?w=mine" + (f"&e={quote(error)}" if error else ""), 303)
    safe = ":/?&=-._~"
    if urls:
        resp.set_cookie("nook_myfeeds", "|".join(quote(u, safe=safe) for u in urls), max_age=31536000, samesite="Lax")
    else:
        resp.delete_cookie("nook_myfeeds")
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


async def ask_suggest(prefix):
    async with httpx.AsyncClient(headers=engines.HEADERS, follow_redirects=True, http2=True, timeout=3) as client:
        return await related.suggest(client, prefix)


@app.get("/suggest")
def suggest():
    """What people type after what has been typed so far (DuckDuckGo's suggestions, through nook)."""
    prefix = request.args.get("q", "").strip()[:80]
    if len(prefix) < 2 or request.cookies.get("nook_suggest") == "off":
        return jsonify([])
    if not any(e.NAME == "duckduckgo" for e in chosen_engines()):
        return jsonify([])
    if too_busy(request.remote_addr, "suggest", 240):
        abort(429)
    resp = jsonify(asyncio.run(ask_suggest(prefix)))
    resp.headers["Cache-Control"] = "private, max-age=300"
    return resp


@app.get("/peek")
def peek():
    """The opening of a result's page, for the small "peek" under a result."""
    url = request.args.get("u", "")
    if not proxy.verify(url, request.args.get("s"), "read"):
        abort(403)
    if too_busy(request.remote_addr, "peek", 40):
        abort(429)
    paras, how = reader.article(url, "")
    text = ""
    if how != "partial":
        for p in paras:
            if len(text) >= 450:
                break
            if len(p) >= 70:
                text += (" " if text else "") + p
    if len(text) > 700:
        cut = text[:700]
        stop = max(cut.rfind(". "), cut.rfind("? "), cut.rfind("! "))
        text = cut[:stop + 1] if stop > 250 else cut.rstrip() + "..."
    return jsonify({"text": text})


def bang_names():
    return sorted({*answers.BANGS, *(k.lower() for k in (config.get("bangs") or {}))})


@app.get("/palette.json")
def palette():
    """What the ctrl+k box can jump to: pages, example searches, bangs."""
    resp = jsonify({"pages": tools.PAGES, "examples": tools.flat(), "bangs": bang_names()})
    resp.headers["Cache-Control"] = "public, max-age=3600"
    return resp


@app.get("/tools")
def tools_page():
    return render_template("tools.html", catalog=tools.CATALOG, bangs=bang_names(), lens_table=LENSES)


@app.get("/shelf")
def shelf_page():
    return render_template("shelf.html")


async def ask_code(query):
    async with httpx.AsyncClient(headers=engines.HEADERS, follow_redirects=True, timeout=6) as client:
        return await codesearch.search(client, query)


@app.get("/code")
def code_page():
    q = request.args.get("q", "").strip()[:100]
    sections, failed = [], []
    if q:
        if too_busy(request.remote_addr):
            abort(429)
        sections, failed = asyncio.run(ask_code(q))
    return render_template("code.html", q=q, sections=sections, failed=failed)


def today_prefs():
    """What this browser asked /today to show (a cookie): weather places, clock places, news on or off."""
    parts = request.cookies.get("nook_today", "").split("|")

    def names(i):
        raw = parts[i] if len(parts) > i else ""
        return [p.replace("_", " ") for p in raw.split("~") if p][:4]
    return names(0), names(1), len(parts) > 2 and parts[2] == "1"


@app.post("/today")
def today_set():
    def clean(field):
        out = []
        for line in request.form.get(field, "").splitlines():
            line = re.sub(r"[^\w .'\-]", " ", line)
            line = re.sub(r"\s+", " ", line).strip()[:40]
            if line and line not in out:
                out.append(line.replace(" ", "_"))
        return "~".join(out[:4])
    value = f"{clean('weather')}|{clean('clocks')}|{1 if request.form.get('news') else 0}"
    resp = redirect("/today", 303)
    if value == "||0":
        resp.delete_cookie("nook_today")
    else:
        resp.set_cookie("nook_today", value, max_age=31536000, samesite="Lax")
    return resp


async def ask_today(weather_places, clock_places):
    async with httpx.AsyncClient(headers=engines.HEADERS, follow_redirects=True, http2=True, timeout=6) as client:
        unknown = []
        for p in clock_places:
            unknown += places.unknown_places(f"time in {p}") or []
        if unknown:
            await places.learn(client, list(dict.fromkeys(unknown)))
        found = await asyncio.gather(*(weather.lookup(client, p) for p in weather_places), return_exceptions=True)
    clocks = [places.answer(f"time in {p}") for p in clock_places]
    return [c for c in found if isinstance(c, dict)], [c for c in clocks if c]


@app.get("/today")
def today_page():
    weather_places, clock_places, news_on = today_prefs()
    if too_busy(request.remote_addr):
        abort(429)
    forecasts, clocks, stories = [], [], []
    if weather_places or clock_places:
        forecasts, clocks = asyncio.run(ask_today(weather_places, clock_places))
    if news_on:
        everything, _ = asyncio.run(ask_news(feeds))
        stories = news.top_stories([s for lst in everything for s in lst])[:5]
    return render_template("today.html", forecasts=forecasts, clocks=clocks, stories=stories, news_on=news_on,
                           weather_text="\n".join(weather_places), clock_text="\n".join(clock_places),
                           empty=not (weather_places or clock_places or news_on))


# --- compare engines, a search as data (for watching and feed readers)

async def ask_each(query):
    """Every engine asked on its own: [(name, results or None)]."""
    async with httpx.AsyncClient(headers=engines.HEADERS, follow_redirects=True, http2=True,
                                 timeout=config["timeout"]) as client:
        async def one(engine):
            try:
                return engine.NAME, await asyncio.wait_for(engine.search(client, query), config["timeout"] + 2)
            except Exception:
                return engine.NAME, None
        return await asyncio.gather(*(one(e) for e in active))


@app.get("/versus")
def versus():
    q = request.args.get("q", "").strip()[:200]
    columns, shared, total = [], 0, 0
    if q:
        if too_busy(request.remote_addr, "versus", 10):
            abort(429)
        asked = asyncio.run(ask_each(q))
        seen = Counter(merge.normalize(r.url) for _, found in asked for r in (found or [])[:10])
        for name, found in asked:
            items = [{"title": r.title, "url": r.url, "host": urlparse(r.url).hostname or "",
                      "shared": seen[merge.normalize(r.url)] > 1, "count": seen[merge.normalize(r.url)]}
                     for r in (found or [])[:10]]
            columns.append({"name": name, "ok": found is not None, "rows": items})
        total = len(seen)
        shared = sum(1 for n in seen.values() if n > 1)
    return render_template("versus.html", q=q, columns=columns, shared=shared, total=total)


def search_results():
    """The web results for ?q= (and ?l= for a lens) as a list, for /search.json and /search.rss."""
    q = request.args.get("q", "").strip()[:200]
    if not q:
        abort(400)
    if too_busy(request.remote_addr):
        abort(429)
    lens = request.args.get("l", "")
    heard = lenses.apply(q, LENSES[lens]) if lens in LENSES else q
    found, failed = asyncio.run(ask(heard, 1, chosen_engines(), chosen_period(), region=chosen_region(), safe=chosen_safe()))
    found, _ = apply_sites(found)
    return q, lens, found[:20], failed


@app.get("/search.json")
def search_json():
    q, lens, found, failed = search_results()
    return jsonify({"q": q, "lens": lens, "failed": failed, "results": [
        {"title": r.title, "url": r.url, "snippet": r.snippet, "engines": r.engines} for r in found]})


@app.get("/search.rss")
def search_rss():
    """A search as a feed: a feed reader polling it is an alert for new results, and nook keeps nothing."""
    q, lens, found, _ = search_results()
    items = "".join(
        f"<item><title>{xml_escape(r.title)}</title><link>{xml_escape(r.url)}</link>"
        f"<guid isPermaLink=\"true\">{xml_escape(r.url)}</guid><description>{xml_escape(r.snippet)}</description></item>"
        for r in found)
    base = request.host_url.rstrip("/")
    xml = ("<?xml version=\"1.0\" encoding=\"UTF-8\"?><rss version=\"2.0\"><channel>"
           f"<title>nook: {xml_escape(q)}</title><link>{xml_escape(base + '/search?q=' + quote(q))}</link>"
           f"<description>web results for {xml_escape(q)}</description>{items}</channel></rss>")
    return Response(xml, mimetype="application/rss+xml")


@app.get("/cli")
def cli():
    """The same search as plain text, for a terminal: curl "https://your-nook/cli?q=sourdough" """
    q = request.args.get("q", "").strip()[:200]
    if not q:
        return Response("usage: curl \"" + request.host_url + "cli?q=your+search\"\n", mimetype="text/plain")
    lines = []
    sure = answers.answer(q)
    if sure:
        lines += [sure, ""]
    _, lens, shown, failed = search_results()
    for n, r in enumerate(shown[:min(int(request.args.get("n", 8) or 8), 20)], 1):
        lines += [f"{n}. {r.title}", f"   {r.url}"] + ([f"   {r.snippet[:160]}"] if r.snippet else []) + [""]
    if not shown:
        lines.append("nothing found.")
    return Response("\n".join(lines) + "\n", mimetype="text/plain")


@app.get("/watching")
def watching_page():
    return render_template("watching.html")


# --- status

last_check = []   # [(when, [(name, problem or None)])]


async def ask_check():
    """The same live check as check_engines.py: one real search per engine."""
    async with httpx.AsyncClient(headers=engines.HEADERS, follow_redirects=True, http2=True, timeout=15) as client:
        done = await asyncio.gather(*(check_engines.check_one(client, m) for m in (*active, bing_images, duckduckgo_videos)))
    return [(name, bad) for name, bad, _ in done]


def health():
    now = time.monotonic()
    rows = []
    for e in active:
        rest = merge.resting.get(e.NAME)
        ok, bad = merge.last_ok.get(e.NAME), merge.last_bad.get(e.NAME)
        rows.append({"name": e.NAME, "resting": max(0, int(rest[0] - now)) if rest and rest[0] > now else 0,
                     "ok": int(now - ok) if ok else None, "bad": int(now - bad) if bad else None,
                     "strikes": merge.strikes.get(e.NAME, 0)})
    feed_rows = []
    for f in feeds:
        hit = news._cache.get(f["url"])
        feed_rows.append({"name": f["name"], "wing": f["wing"], "age": int(now - hit[0]) if hit else None,
                          "count": len(hit[1]) if hit else 0})
    return rows, feed_rows


@app.get("/status")
def status_page():
    rows, feed_rows = health()
    checked = last_check[0] if last_check else None
    return render_template("status.html", engine_rows=rows, feed_rows=feed_rows, checked=checked,
                           checked_ago=int(time.time() - checked[0]) if checked else None,
                           cooling=bool(checked and time.time() - checked[0] < 60))


@app.post("/status")
def status_check():
    if not (last_check and time.time() - last_check[0][0] < 60) and not too_busy(request.remote_addr, "check", 3):
        last_check[:] = [(time.time(), asyncio.run(ask_check()))]
    return redirect("/status", 303)


# --- travel, the world right now, learn

async def ask_travel(a, b, mode):
    async with httpx.AsyncClient(headers=engines.HEADERS, follow_redirects=True, http2=True, timeout=8) as client:
        route = await routes.lookup(client, f"{mode} from {a} to {b}")
        gap_query = f"time difference between {a} and {b}"
        unknown = places.unknown_places(gap_query) or []
        if unknown:
            await places.learn(client, unknown)
        there = await asyncio.gather(weather.lookup(client, a), weather.lookup(client, b), return_exceptions=True)
    gap = places.answer(gap_query)
    return route, gap if gap and gap.get("kind") == "zones" else None, [w if isinstance(w, dict) else None for w in there]


@app.get("/travel")
def travel_page():
    a, b = request.args.get("from", "").strip()[:60], request.args.get("to", "").strip()[:60]
    mode = request.args.get("mode", "drive") if request.args.get("mode") in ("drive", "walk", "bike") else "drive"
    route = gap = None
    forecasts = [None, None]
    if a and b:
        if too_busy(request.remote_addr, "travel", 10):
            abort(429)
        route, gap, forecasts = asyncio.run(ask_travel(a, b, mode))
    return render_template("travel.html", a=a, b=b, mode=mode, route=route, gap=gap, forecasts=forecasts)


async def ask_world():
    async with httpx.AsyncClient(headers=engines.HEADERS, follow_redirects=True, http2=True, timeout=8) as client:
        shaken, station = await asyncio.gather(earth.quakes(client, "day"), earth.iss(client), return_exceptions=True)
    return (shaken if isinstance(shaken, dict) else None), (station if isinstance(station, dict) else None)


@app.get("/world")
def world_page():
    if too_busy(request.remote_addr):
        abort(429)
    quakes, station = asyncio.run(ask_world())
    markers = list(quakes["markers"]) if quakes else []
    if station:
        markers.append({"lat": station["lat"], "lon": station["lon"], "label": "the space station", "on": True})
    return render_template("world.html", quakes=quakes, station=station, markers=markers, moon=dates.moon())


async def ask_learn():
    async with httpx.AsyncClient(headers=engines.HEADERS, follow_redirects=True, http2=True, timeout=8) as client:
        return await history.learn(client)


@app.get("/learn")
def learn_page():
    if too_busy(request.remote_addr):
        abort(429)
    return render_template("learn.html", today=asyncio.run(ask_learn()))


async def ask_random():
    async with httpx.AsyncClient(headers=engines.HEADERS, follow_redirects=True, http2=True, timeout=4) as client:
        r = await client.get("https://en.wikipedia.org/api/rest_v1/page/random/summary", headers=wiki.headers())
        r.raise_for_status()
        return r.json().get("title")


@app.get("/surprise")
def surprise():
    """Something to read: a random Wikipedia subject, searched like anything else."""
    if too_busy(request.remote_addr, "surprise", 10):
        abort(429)
    try:
        title = asyncio.run(ask_random())
    except Exception:
        title = None
    return redirect(f"/search?q={quote(title)}" if title else "/")


@app.get("/daily.json")
def daily():
    """Today's word, for the home page (only asked when the visitor switched it on there)."""
    if too_busy(request.remote_addr, "daily", 30):
        abort(429)
    resp = jsonify((asyncio.run(ask_learn()).get("word")) or {})
    resp.headers["Cache-Control"] = "private, max-age=3600"
    return resp


# --- /weather, /convert, /books

def _ll():
    try:
        lat, lon = (float(v) for v in request.args.get("ll", "").split(","))
    except ValueError:
        return None
    return (round(lat, 3), round(lon, 3)) if -85 < lat < 85 and -180 <= lon <= 180 else None


async def ask_forecast(place, ll, unit):
    async with httpx.AsyncClient(headers=engines.HEADERS, follow_redirects=True, http2=True, timeout=8) as client:
        return await forecast.lookup(client, place, ll, unit)


@app.get("/weather")
def weather_page():
    place, unit, ll = forecast.valid_place(request.args.get("q", "")), forecast.clean_unit(request.args.get("u")), _ll()
    page = None
    if place or ll:
        if too_busy(request.remote_addr, "weather", 30):
            abort(429)
        page = asyncio.run(ask_forecast(place, ll, unit))
    return render_template("weather.html", q=place, unit=unit, page=page, asked=bool(place or ll), ll=ll)


async def ask_money(amount, source):
    async with httpx.AsyncClient(headers=engines.HEADERS, follow_redirects=True, http2=True, timeout=8) as client:
        return await converter.money(client, amount, source)


async def ask_gap(query, names):
    async with httpx.AsyncClient(headers=engines.HEADERS, follow_redirects=True, http2=True, timeout=8) as client:
        unknown = []
        for n in names:
            unknown += places.unknown_places(f"time in {n}") or []
        if unknown:
            await places.learn(client, list(dict.fromkeys(unknown)))
    return places.answer(query)


@app.get("/convert")
def convert_page():
    mode = request.args.get("m") if request.args.get("m") in ("money", "units", "time") else "money"
    ctx = {"mode": mode, "kinds": list(converter.KINDS), "name": converter.name, "currencies": sorted(cards.CURRENCIES),
           "units": converter.KINDS}
    a = converter.number(request.args.get("v"), 100.0 if mode == "money" else 1.0)
    if mode == "money":
        source = request.args.get("from", "USD").upper()
        source = source if source in cards.CURRENCIES else "USD"
        ctx.update(amount=a, source=source, result=None)
        if too_busy(request.remote_addr, "convert", 60):
            abort(429)
        ctx["result"] = asyncio.run(ask_money(a, source))
    elif mode == "units":
        kind = request.args.get("k") if request.args.get("k") in converter.KINDS else "length"
        source = request.args.get("from") if request.args.get("from") in converter.KINDS[kind] else converter.KINDS[kind][0]
        ctx.update(kind=kind, amount=a, source=source, rows=converter.convert(kind, a, source))
    else:
        a_place, b_place = request.args.get("a", "").strip()[:40], request.args.get("b", "").strip()[:40]
        at = request.args.get("at", "").strip()[:10]
        card = None
        if a_place and b_place:
            if too_busy(request.remote_addr, "convert", 60):
                abort(429)
            query = f"{at} in {a_place} to {b_place}" if at else f"{a_place} time to {b_place} time"
            card = asyncio.run(ask_gap(query, [a_place, b_place]))
        ctx.update(a=a_place, b=b_place, at=at, card=card if card and card.get("kind") == "zones" else None, asked=bool(a_place and b_place))
    return render_template("convert.html", **ctx)


async def ask_books(query):
    async with httpx.AsyncClient(headers=engines.HEADERS, follow_redirects=True, http2=True, timeout=8) as client:
        return await books.search(client, query)


async def ask_work(work_id):
    async with httpx.AsyncClient(headers=engines.HEADERS, follow_redirects=True, http2=True, timeout=8) as client:
        return await books.work(client, work_id)


@app.get("/books")
def books_page():
    q = request.args.get("q", "").strip()[:100]
    found = None
    if q:
        if too_busy(request.remote_addr, "books", 30):
            abort(429)
        found = asyncio.run(ask_books(q))
    return render_template("books.html", q=q, found=found)


@app.get("/book/<work_id>")
def book_page(work_id):
    if too_busy(request.remote_addr, "books", 30):
        abort(429)
    book = asyncio.run(ask_work(work_id))
    if book is None:
        return render_template("message.html", text="couldn't find that book."), 404
    who = book["authors"].split(",")[0]
    return render_template("book.html", b=book, q=request.args.get("q", "")[:100],
                           reviews=f'"{book["title"]}" {who} book review'.strip())


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
