import asyncio
import socket
import time

import httpcore
import pytest

import answers
import app as nook
import cards
import merge
import netinfo
import packages
import proxy
from engines import Result


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def client(monkeypatch):
    nook.cache.clear()
    nook.hits.clear()
    nook.traffic.clear()
    return nook.app.test_client()


# --- a name cannot answer differently the second time ------------------------------------------

def fake_dns(monkeypatch, *addresses):
    monkeypatch.setattr(proxy.socket, "getaddrinfo", lambda host, port, **kw: [(2, 1, 6, "", (a, port)) for a in addresses])


def test_connections_go_to_the_address_that_was_checked(monkeypatch):
    fake_dns(monkeypatch, "93.184.216.34")
    assert proxy.public_address("example.com", 443) == "93.184.216.34"


@pytest.mark.parametrize("addresses", [("127.0.0.1",), ("10.0.0.5",), ("169.254.169.254",), ("::1",), ("::ffff:127.0.0.1",),
                                      ("93.184.216.34", "127.0.0.1"), ()])
def test_any_non_public_answer_is_refused_at_connect_time(monkeypatch, addresses):
    fake_dns(monkeypatch, *addresses)
    with pytest.raises(httpcore.ConnectError):
        proxy.public_address("rebind.example", 80)


def test_the_pinned_backend_connects_to_the_checked_address_only(monkeypatch):
    seen = []
    monkeypatch.setattr(httpcore.SyncBackend, "connect_tcp", lambda self, host, port, **kw: seen.append(host) or "stream")
    fake_dns(monkeypatch, "93.184.216.34")
    assert proxy._Pinned().connect_tcp("example.com", 443) == "stream" and seen == ["93.184.216.34"]
    fake_dns(monkeypatch, "192.168.1.1")
    with pytest.raises(httpcore.ConnectError):
        proxy._Pinned().connect_tcp("evil.example", 443)
    assert seen == ["93.184.216.34"]


@pytest.mark.parametrize("url", ["http://[::ffff:127.0.0.1]/", "http://0.0.0.0/", "http://169.254.169.254/latest/meta-data/",
                                 "http://localhost/", "http://127.1/", "http://2130706433/", "http://[::1]/", "http://10.0.0.1/",
                                 "ftp://example.com/", "file:///etc/passwd", "http:///nohost"])
def test_the_quick_check_refuses_every_odd_spelling(url):
    assert proxy.is_public(url) is False


def test_the_proxy_client_uses_the_pinned_transport():
    import inspect
    assert "PinnedTransport()" in inspect.getsource(proxy._get)


# --- not a free download service -----------------------------------------------------------------

def test_a_visitor_has_a_picture_budget(client, monkeypatch):
    monkeypatch.setitem(nook.config, "picture_mb_per_minute", 1)
    monkeypatch.setattr(proxy, "fetch", lambda url: (b"x" * 600_000, "image/png"))
    url = "https://example.com/a.png"
    link = f"/img?u={url}&s={proxy.sign(url)}"
    codes = [client.get(link).status_code for _ in range(4)]
    assert codes[:2] == [200, 200] and 429 in codes


def test_the_budget_resets_after_a_minute():
    nook.traffic.clear()
    assert nook.over_budget("v", 100) is False
    nook.traffic["v"] = (time.monotonic() - 61, 10 ** 12)
    assert nook.over_budget("v", 1) is False


# --- one slow engine does not hold the page ---------------------------------------------------------

class Slow:
    def __init__(self, name, delay, results=("https://a.example/",)):
        self.NAME, self.delay, self.found = name, delay, results

    async def search(self, client, query, page=1, **kw):
        await asyncio.sleep(self.delay)
        return [Result(title=self.NAME, url=u, snippet="s", engines=[self.NAME], rank=n) for n, u in enumerate(self.found)]


def test_slow_engines_are_left_behind_once_two_have_answered(monkeypatch):
    monkeypatch.setattr(merge, "GRACE", 0.2)
    merge.strikes.clear()
    merge.resting.clear()
    engines = [Slow("fast", 0.01, ("https://a.example/1",)), Slow("quick", 0.05, ("https://b.example/2",)),
               Slow("slow", 3.0, ("https://c.example/3",))]
    started = time.monotonic()
    results, failed = run(merge.gather(None, engines, "x"))
    assert time.monotonic() - started < 1.5
    assert {r.url for r in results} == {"https://a.example/1", "https://b.example/2"}
    assert failed == ["slow"] and "slow" not in merge.strikes      # late is not the same as broken


def test_everyone_is_waited_for_when_they_are_all_quick(monkeypatch):
    monkeypatch.setattr(merge, "GRACE", 0.5)
    merge.strikes.clear()
    engines = [Slow("a", 0.01, ("https://a.example/1",)), Slow("b", 0.02, ("https://b.example/1",)), Slow("c", 0.1, ("https://c.example/1",))]
    results, failed = run(merge.gather(None, engines, "x"))
    assert len(results) == 3 and failed == []


def test_with_only_two_engines_nobody_is_cut_off(monkeypatch):
    monkeypatch.setattr(merge, "GRACE", 0.01)
    engines = [Slow("a", 0.01), Slow("b", 0.3, ("https://b.example/1",))]
    results, failed = run(merge.gather(None, engines, "x"))
    assert len(results) == 2 and failed == []


# --- every bang, and a straight jump -----------------------------------------------------------------

def test_unknown_bangs_go_to_duckduckgo_which_knows_thousands():
    assert answers.bang_target("!nope x") == "https://duckduckgo.com/?q=%21nope%20x"
    assert answers.bang_target("!aur yay helper") == "https://duckduckgo.com/?q=%21aur%20yay%20helper"
    assert answers.bang_target("sourdough !zzz") is None          # a trailing word is not a bang we guess at
    assert answers.bang_target("!w") is None and answers.bang_target("! x") is None
    assert answers.bang_target("!w sourdough").startswith("https://en.wikipedia.org")
    assert answers.bang_target("!x y", {"x": "javascript:alert({})"}) is None   # our own broken ones stay broken


@pytest.mark.parametrize("query, host", [("reddit.com", "reddit.com"), ("https://www.github.com/pallets/flask", "github.com"),
                                         ("docs.python.org/3/", "docs.python.org"), ("Wikipedia.ORG", "wikipedia.org")])
def test_a_typed_address_offers_a_jump(query, host):
    card = cards.local(query)
    assert card["kind"] == "jump" and card["host"] == host and card["url"].startswith("https://" + host)


@pytest.mark.parametrize("query", ["node.js", "file.txt", "my.notes today", "hello world.com now", "3.14159", "a.b"])
def test_things_that_are_not_sites_do_not(query):
    assert (cards.local(query) or {}).get("kind") != "jump"


# --- packages -----------------------------------------------------------------------------------------

@pytest.mark.parametrize("query, expected", [
    ("npm react", ("npm", "react")), ("pip install httpx", ("pypi", "httpx")), ("pypi flask", ("pypi", "flask")),
    ("cargo add tokio", ("crates", "tokio")), ("npm @types/node", ("npm", "@types/node")), ("yarn lodash", ("npm", "lodash")),
])
def test_package_queries(query, expected):
    assert packages.parse(query) == expected


@pytest.mark.parametrize("query", ["npm", "npm install", "pip", "cargo tokio/x", "npm react hooks tutorial", "install react"])
def test_other_queries_are_not_package_queries(query):
    assert packages.parse(query) is None


def test_package_cards():
    npm = packages.from_npm({"name": "react", "version": "19.3.1", "description": "React is a JavaScript library.", "license": "MIT",
                             "repository": {"url": "git+https://github.com/facebook/react.git"}}, "react")
    assert npm["install"] == "npm install react" and npm["licence"] == "MIT" and npm["home"] == "https://github.com/facebook/react"
    py = packages.from_pypi({"info": {"name": "httpx", "version": "0.28", "summary": "The next generation HTTP client.",
                                      "license": "x" * 500, "classifiers": ["License :: OSI Approved :: BSD License"],
                                      "project_urls": {"Source": "https://github.com/encode/httpx"}, "requires_python": ">=3.8"}}, "httpx")
    assert py["install"] == "pip install httpx" and py["licence"] == "BSD License" and py["extra"] == "python >=3.8"
    crate = packages.from_crates({"crate": {"name": "tokio", "max_stable_version": "1.40", "description": "An event-driven platform.",
                                            "repository": "https://github.com/tokio-rs/tokio"}, "versions": [{"num": "1.40", "license": "MIT"}]}, "tokio")
    assert crate["install"] == "cargo add tokio" and crate["licence"] == "MIT" and crate["registry"] == "crates.io"
    assert packages.from_npm({}, "x") is None and packages.from_pypi({}, "x") is None and packages.from_crates({}, "x") is None
    assert packages.card("npm", "x", "1", "s", "MIT", "javascript:alert(1)")["home"] == ""


def test_package_lookup_asks_the_registry_once():
    packages._cache.clear()
    calls = []

    class Client:
        async def get(self, url, headers=None, **kw):
            calls.append(url)

            class R:
                status_code = 200

                def raise_for_status(s):
                    pass

                def json(s):
                    return {"name": "react", "version": "19", "description": "d", "license": "MIT"}
            return R()
    c = Client()
    assert run(packages.lookup(c, "npm react"))["version"] == "19" and run(packages.lookup(c, "npm react"))["version"] == "19"
    assert calls == ["https://registry.npmjs.org/react/latest"]


# --- networks ------------------------------------------------------------------------------------------

@pytest.mark.parametrize("query, expected", [
    ("192.168.1.0/24", ("subnet", "192.168.1.0/24")), ("192.168.1.0/24 range", ("subnet", "192.168.1.0/24")),
    ("subnet 10.0.0.0/8", ("subnet", "10.0.0.0/8")), ("dns example.com", ("dns", "example.com", ["a", "aaaa", "mx", "ns", "txt"])),
    ("dig example.com mx", ("dns", "example.com", ["mx"])), ("dns txt google.com", ("dns", "google.com", ["txt"])),
    ("mx records for example.com", ("dns", "example.com", ["mx"])), ("whois github.com", ("whois", "github.com")),
])
def test_network_queries(query, expected):
    assert netinfo.parse(query) == expected


@pytest.mark.parametrize("query", ["dns", "dig", "999.1.1.0/24", "1/2", "whois", "dns localhost", "dns not a domain"])
def test_other_queries_are_not_network_queries(query):
    assert netinfo.parse(query) is None


def test_subnet_maths():
    rows = dict(netinfo.subnet("192.168.1.77/24")["rows"])
    assert rows["network"] == "192.168.1.0" and rows["mask"] == "255.255.255.0" and rows["broadcast"] == "192.168.1.255"
    assert rows["first host"] == "192.168.1.1" and rows["last host"] == "192.168.1.254" and rows["usable hosts"] == "254"
    assert rows["kind"] == "private" and dict(netinfo.subnet("8.8.8.0/24")["rows"])["kind"] == "public"
    assert dict(netinfo.subnet("2001:db8::/32")["rows"])["addresses"].startswith("2^")


def test_dns_and_rdap_answers():
    card = netinfo.parse_dns([("mx", {"Answer": [{"type": 15, "data": "10 mail.example.com."}]}),
                              ("txt", {"Answer": [{"type": 16, "data": "\"v=spf1\" \"-all\""}, {"type": 5, "data": "ignored"}]}),
                              ("a", {})], "example.com")
    assert card["rows"] == [("MX", "10 mail.example.com."), ("TXT", "v=spf1-all")]
    assert netinfo.parse_dns([("a", {})], "x.example") is None
    rdap = {"entities": [{"roles": ["registrar"], "vcardArray": ["vcard", [["fn", {}, "text", "MarkMonitor Inc."]]]}],
            "events": [{"eventAction": "registration", "eventDate": "2007-10-09T18:20:50Z"}, {"eventAction": "expiration", "eventDate": "2026-10-09T18:20:50Z"}],
            "nameservers": [{"ldhName": "NS1.EXAMPLE.COM"}], "status": ["client delete prohibited"]}
    rows = dict(netinfo.parse_rdap(rdap, "github.com")["rows"])
    assert rows["registrar"] == "MarkMonitor Inc." and rows["registered"] == "2007-10-09" and rows["name servers"] == "ns1.example.com"


def test_subnets_need_no_network(client):
    html = client.get("/search", query_string={"q": "192.168.1.0/24 range"}).get_data(as_text=True)
    assert 'class="card facts"' in html and "255.255.255.0" in html


# --- more units ------------------------------------------------------------------------------------------

@pytest.mark.parametrize("query, shown", [
    ("60 mph in km/h", "96.5606 km/h"), ("15 psi in bar", "1.03421 bar"), ("100 mbps in mb/s", "12.5 mb/s"),
    ("1 atm in kpa", "101.325 kpa"), ("10 m/s in km/h", "36 km/h"), ("1 acre in m2", "4,046.86 m2"),
    ("500 kcal in kj", "2,092 kj"), ("1 gb/s in mbps", "8,000 mbps"), ("100 sqm in sqft", "1,076.39 sqft"),
])
def test_compound_units(query, shown):
    assert answers.answer(query).endswith(shown)


def test_units_of_different_kinds_still_do_not_mix():
    assert answers.answer("5 psi in mph") is None and answers.answer("5 mbps in kg") is None


# --- a search for a terminal --------------------------------------------------------------------------------

def test_the_terminal_route(client, monkeypatch):
    async def ask(query, page=1, chosen=None, period=None, **kw):
        return [Result(title="One <b>post</b>", url="https://a.example/1", snippet="about it", engines=["bing"], rank=0),
                Result(title="Two", url="https://b.example/2", snippet="", engines=["bing"], rank=1)], []
    monkeypatch.setattr(nook, "ask", ask)
    r = client.get("/cli", query_string={"q": "12*7"})
    body = r.get_data(as_text=True)
    assert r.mimetype == "text/plain" and body.startswith("12*7 = 84") and "1. One <b>post</b>\n   https://a.example/1\n   about it" in body
    assert "2. Two\n   https://b.example/2\n\n" in body
    assert "usage: curl" in client.get("/cli").get_data(as_text=True)
    assert body.count("https://") == 2 and "html" not in body.lower().replace("<b>", "")
    assert client.get("/cli", query_string={"q": "x", "n": "1"}).get_data(as_text=True).count("https://") == 1
