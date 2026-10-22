"""Fetches things on the visitor's behalf so their browser never talks to third parties.

Only addresses nook itself put on a page are fetchable: each one carries a signature,
so this cannot be used as an open proxy. Private and local addresses are refused too.
"""
import hashlib
import hmac
import ipaddress
import secrets
import socket
import time
from urllib.parse import quote, urljoin, urlparse

import httpcore
import httpx

MAX_IMAGE = 12 * 1024 * 1024
MAX_PAGE = 4 * 1024 * 1024
MAX_AUDIO = 2 * 1024 * 1024
MAX_REDIRECTS = 3
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
IMAGE_HEADERS = {"User-Agent": UA, "Accept": "image/avif,image/webp,image/png,image/jpeg,image/gif,*/*;q=0.5"}
PAGE_HEADERS = {"User-Agent": UA, "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.5",
                "Accept-Language": "en-US,en;q=0.9"}

# Wikimedia's servers turn away clients that pretend to be a browser. They ask for a User-Agent
# that says what the program is and how to reach its owner, so that is what their hosts get.
POLITE = (".wikimedia.org", ".wikipedia.org", ".wikidata.org")
CONTACT = ""


def _headers_for(url, headers):
    host = (urlparse(url).hostname or "").lower()
    if any(host.endswith(d) for d in POLITE):
        who = CONTACT or "self-hosted metasearch page"
        return {**headers, "User-Agent": f"nook/1.0 ({who})"}
    return headers


_secret = secrets.token_bytes(32)


def configure(secret):
    global _secret
    if secret:
        _secret = secret.encode()


def sign(url, purpose="img"):
    return hmac.new(_secret, f"{purpose}:{url}".encode(), hashlib.sha256).hexdigest()[:32]


def link(url):
    """The address a page should use instead of the picture at `url`."""
    if not url:
        return ""
    return f"/img?u={quote(url, safe='')}&s={sign(url)}"


def read_link(url, wing="centre", q="", title=""):
    """The address of nook's reader view for the article at `url`.

    `q` (the search it came from) and `title` are only shown, never trusted."""
    extra = (f"&q={quote(q, safe='')}" if q else "") + (f"&t={quote(title[:200], safe='')}" if title else "")
    return f"/read?u={quote(url, safe='')}&s={sign(url, 'read')}&w={quote(wing, safe='')}{extra}"


def audio_link(url):
    """The address of a pronunciation clip, passed through nook."""
    return f"/audio?u={quote(url, safe='')}&s={sign(url, 'audio')}" if url else ""


def compare_link(url, wing="all"):
    return f"/compare?u={quote(url, safe='')}&s={sign(url, 'compare')}&w={quote(wing, safe='')}"


def verify(url, sig, purpose="img"):
    return hmac.compare_digest(sign(url, purpose), sig or "")


def is_public(url):
    p = urlparse(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        return False
    try:
        addresses = {a[4][0] for a in socket.getaddrinfo(p.hostname, p.port or 443)}
    except OSError:
        return False
    return bool(addresses) and all(ipaddress.ip_address(a).is_global for a in addresses)


class Refused(Exception):
    pass


def public_address(host, port):
    """A public address for `host`, looked up right now. Refuses a name with any non-public address."""
    try:
        found = {a[4][0] for a in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)}
    except OSError as e:
        raise httpcore.ConnectError(f"cannot find {host}") from e
    if not found or not all(ipaddress.ip_address(a).is_global for a in found):
        raise httpcore.ConnectError("not a public address")
    return sorted(found)[0]


class _Pinned(httpcore.SyncBackend):
    """Connects to the very address it checked, so a name that answers differently the second time
    (DNS rebinding) cannot lead inside. The check in is_public() is a quick no; this is the lock."""

    def connect_tcp(self, host, port, timeout=None, local_address=None, socket_options=None):
        return super().connect_tcp(public_address(host, port), port, timeout=timeout,
                                   local_address=local_address, socket_options=socket_options)


class PinnedTransport(httpx.HTTPTransport):
    def __init__(self):
        super().__init__(http2=True)
        self._pool.close()
        self._pool = httpcore.ConnectionPool(ssl_context=httpx.create_ssl_context(), http2=True, max_connections=20,
                                             max_keepalive_connections=5, keepalive_expiry=5.0, network_backend=_Pinned())


def _get(url, headers, accept, limit):
    """Returns (bytes, content type, charset). Raises Refused for anything we won't pass on."""
    with httpx.Client(headers=headers, timeout=8, follow_redirects=False, transport=PinnedTransport()) as client:  # HTTP/2: some hosts (Wikimedia, Yahoo) need it
        for _ in range(MAX_REDIRECTS + 1):
            if not is_public(url):
                raise Refused("not a public address")
            with client.stream("GET", url, headers=_headers_for(url, headers)) as r:
                if r.is_redirect:
                    url = urljoin(url, r.headers.get("location", ""))
                    continue
                if r.status_code != 200:
                    raise Refused(f"upstream said {r.status_code}")
                kind = r.headers.get("content-type", "").split(";")[0].strip().lower()
                if not accept(kind):
                    raise Refused("not the kind of thing we pass on")
                body = bytearray()
                for chunk in r.iter_bytes():
                    body += chunk
                    if len(body) > limit:
                        raise Refused("too large")
                return bytes(body), kind, r.charset_encoding
    raise Refused("too many redirects")


_small = {}  # url -> (when, bytes, kind): icons come back on every results page
SMALL_BYTES, SMALL_KEEP, SMALL_MAX = 32 * 1024, 6 * 3600, 500


def fetch(url):
    """A picture: (bytes, content type). SVG is refused because it can carry scripts."""
    hit = _small.get(url)
    if hit and time.monotonic() - hit[0] < SMALL_KEEP:
        return hit[1], hit[2]
    body, kind, _ = _get(url, IMAGE_HEADERS,
                         lambda k: k.startswith("image/") and k != "image/svg+xml", MAX_IMAGE)
    if len(body) <= SMALL_BYTES:
        if len(_small) >= SMALL_MAX:
            _small.clear()
        _small[url] = (time.monotonic(), body, kind)
    return body, kind


def fetch_page(url):
    """A web page: its HTML as text."""
    body, _, charset = _get(url, PAGE_HEADERS,
                            lambda k: k in ("text/html", "application/xhtml+xml"), MAX_PAGE)
    return body.decode(charset or "utf-8", "replace")


def fetch_feed(url):
    """A news feed (RSS or Atom): its XML as bytes. Whatever address a visitor adds must be public."""
    body, _, _ = _get(url, PAGE_HEADERS, lambda k: "xml" in k or k in ("text/plain", "application/octet-stream", "text/html"),
                      2 * 1024 * 1024)
    return body


def fetch_audio(url):
    """A short sound clip: (bytes, content type)."""
    body, kind, _ = _get(url, IMAGE_HEADERS,
                         lambda k: k.startswith("audio/") or k == "application/octet-stream", MAX_AUDIO)
    return body, kind if kind.startswith("audio/") else "audio/mpeg"
