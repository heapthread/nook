"""Turns an article page into plain paragraphs for nook's reader view."""
import re
import time

import trafilatura
from selectolax.lexbor import LexborHTMLParser

import proxy

ENOUGH = 600       # fewer characters than this and we treat the article as not really fetched
TTL = 1800
_cache = {}        # url -> (expires, paragraphs, how)


def paragraphs(html):
    """Block-level text of an HTML fragment, one string per paragraph."""
    if not html:
        return []
    tree = LexborHTMLParser(f"<div>{html}</div>")
    out = []
    for node in tree.css("p, h2, h3, h4, li, blockquote"):
        if node.tag == "blockquote" and node.css_first("p"):
            continue  # its paragraphs are picked up on their own
        text = re.sub(r"\s+", " ", node.text(separator=" ", strip=True)).strip()
        if len(text) > 1:
            out.append(text)
    return out


def from_page(html, url):
    text = trafilatura.extract(html, url=url, include_comments=False, include_tables=False,
                               include_images=False, output_format="txt") or ""
    return [p.strip() for p in text.split("\n") if p.strip()]


def size(paras):
    return sum(len(p) for p in paras)


def article(url, feed_html=""):
    """Returns (paragraphs, how). `how` is "page" or "feed" for a real article, else "partial"."""
    hit = _cache.get(url)
    if hit and hit[0] > time.monotonic():
        return hit[1], hit[2]
    best, how = [], "partial"
    try:
        page = from_page(proxy.fetch_page(url), url)
        if size(page) >= ENOUGH:
            best, how = page, "page"
    except Exception:
        pass
    if how == "partial":
        feed = paragraphs(feed_html)
        if size(feed) >= ENOUGH:
            best, how = feed, "feed"
    if len(_cache) > 100:
        _cache.clear()
    _cache[url] = (time.monotonic() + TTL, best, how)
    return best, how
