"""Network questions: `dns example.com`, `dig example.com mx`, `whois github.com`,
`192.168.1.0/24 range`.

Subnet maths is done here. DNS answers come from Cloudflare's public DNS-over-HTTPS service and
domain registration details from the public RDAP service; only the domain name is sent."""
import asyncio
import ipaddress
import re
import time

DOH = "https://cloudflare-dns.com/dns-query"
TYPES = {"a": 1, "aaaa": 28, "mx": 15, "txt": 16, "ns": 2, "cname": 5, "soa": 6}
DOMAIN = r"((?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,24})"
KEEP = 600
_cache = {}


def parse(query):
    """-> ("subnet", cidr) / ("dns", domain, [types]) / ("whois", domain) / None."""
    q = re.sub(r"\s+", " ", query.strip().lower()).rstrip("?")
    m = re.fullmatch(r"(?:subnet |cidr |ip range |range of )?(\d{1,3}(?:\.\d{1,3}){3}/\d{1,2}|[0-9a-f:]{2,39}/\d{1,3})(?: (?:range|subnet|info|mask|hosts|calculator))?", q)
    if m:
        try:
            ipaddress.ip_network(m.group(1), strict=False)
            return "subnet", m.group(1)
        except ValueError:
            return None
    m = re.fullmatch(rf"(?:whois|rdap|who owns|domain info(?:rmation)?(?: for)?) {DOMAIN}", q)
    if m:
        return "whois", m.group(1)
    m = re.fullmatch(rf"(?:dns|dig|nslookup|host)(?: (?:lookup|records?|for))? (?:({'|'.join(TYPES)}) )?{DOMAIN}(?: ({'|'.join(TYPES)}))?(?: records?)?", q) or \
        re.fullmatch(rf"({'|'.join(TYPES)}) records? (?:for|of) {DOMAIN}", q) or \
        re.fullmatch(rf"dns ({'|'.join(TYPES)}) {DOMAIN}", q)
    if m:
        groups = [g for g in m.groups() if g]
        kinds = [g for g in groups if g in TYPES]
        domain = next(g for g in groups if g not in TYPES or "." in g)
        return "dns", domain, kinds[:1] or ["a", "aaaa", "mx", "ns", "txt"]
    return None


def subnet(cidr):
    net = ipaddress.ip_network(cidr, strict=False)
    v4 = net.version == 4
    hosts = net.num_addresses - 2 if v4 and net.prefixlen < 31 else net.num_addresses
    rows = [("network", str(net.network_address)), ("mask", str(net.netmask) if v4 else f"/{net.prefixlen}")]
    if v4:
        rows.append(("wildcard", str(net.hostmask)))
        if net.prefixlen < 31:
            rows += [("first host", str(net.network_address + 1)), ("last host", str(net.broadcast_address - 1))]
        rows.append(("broadcast", str(net.broadcast_address)))
    else:
        rows += [("first", str(net.network_address)), ("last", str(net.broadcast_address))]
    rows.append(("addresses", f"{net.num_addresses:,}" if net.num_addresses < 10 ** 15 else f"2^{net.max_prefixlen - net.prefixlen}"))
    rows.append(("usable hosts", f"{hosts:,}" if hosts < 10 ** 15 else "a great many"))
    if v4:
        rows.append(("kind", "private" if net.is_private else "public"))
    return {"kind": "table", "title": str(net), "rows": rows, "note": "worked out here"}


def parse_dns(answers_by_type, domain):
    rows = []
    for kind, data in answers_by_type:
        for a in (data or {}).get("Answer", []):
            if a.get("type") != TYPES[kind]:
                continue
            value = str(a.get("data", "")).strip('"').replace('" "', "")
            rows.append((kind.upper(), (value[:140] + "…") if len(value) > 140 else value))
    return {"kind": "table", "title": domain, "rows": rows, "note": "DNS answers via Cloudflare's public resolver"} if rows else None


def parse_rdap(data, domain):
    registrar = ""
    for e in data.get("entities", []):
        if "registrar" in e.get("roles", []):
            vcard = (e.get("vcardArray") or [None, []])[1]
            registrar = next((f[3] for f in vcard if f and f[0] == "fn"), "")
    events = {e.get("eventAction"): (e.get("eventDate") or "")[:10] for e in data.get("events", [])}
    rows = [("registrar", registrar)] if registrar else []
    for label, key in (("registered", "registration"), ("expires", "expiration"), ("last changed", "last changed")):
        if events.get(key):
            rows.append((label, events[key]))
    names = [n.get("ldhName", "").lower() for n in data.get("nameservers", [])][:4]
    if names:
        rows.append(("name servers", ", ".join(names)))
    if data.get("status"):
        rows.append(("status", ", ".join(data["status"][:3])))
    return {"kind": "table", "title": domain, "rows": rows, "note": "registration details via RDAP"} if rows else None


def local(query):
    """The subnet answer, which needs no network."""
    parsed = parse(query)
    return subnet(parsed[1]) if parsed and parsed[0] == "subnet" else None


async def lookup(client, query):
    parsed = parse(query)
    if not parsed:
        return None
    if parsed[0] == "subnet":
        return subnet(parsed[1])
    key = parsed[:2] + (tuple(parsed[2]) if len(parsed) > 2 else ())
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < KEEP:
        return hit[1]
    try:
        if parsed[0] == "whois":
            r = await client.get(f"https://rdap.org/domain/{parsed[1]}", headers={"Accept": "application/rdap+json"})
            card = parse_rdap(r.json(), parsed[1]) if r.status_code == 200 else None
        else:
            async def one(kind):
                r = await client.get(DOH, params={"name": parsed[1], "type": kind.upper()}, headers={"Accept": "application/dns-json"})
                r.raise_for_status()
                return kind, r.json()
            card = parse_dns(await asyncio.gather(*(one(k) for k in parsed[2])), parsed[1])
    except Exception:
        return None
    if len(_cache) > 200:
        _cache.clear()
    _cache[key] = (time.monotonic(), card)
    return card
