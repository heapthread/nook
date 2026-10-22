"""`npm react`, `pypi httpx`, `cargo tokio`: the latest version, what it does, its licence, how to
install it and where its code lives, from the package registries' own public pages.
Fetched by nook, remembered for an hour; only the package name is sent."""
import re
import time
from urllib.parse import quote

NAME = r"(@?[a-z0-9][a-z0-9._\-]*(?:/[a-z0-9][a-z0-9._\-]*)?)"
REGISTRIES = {"npm": "npm", "yarn": "npm", "pnpm": "npm", "pypi": "pypi", "pip": "pypi", "cargo": "crates",
              "crates": "crates", "crate": "crates"}
KEEP = 3600
_cache = {}


def parse(query):
    """-> (registry, package) or None. `npm react`, `pip install httpx`, `cargo add tokio`."""
    q = re.sub(r"\s+", " ", query.strip().lower())
    m = re.fullmatch(rf"({'|'.join(REGISTRIES)})(?: (?:install|add|i|package|crate))? {NAME}", q)
    if not m:
        return None
    registry, name = REGISTRIES[m.group(1)], m.group(2)
    if name in ("install", "add", "i", "package", "crate", "help", "init", "update"):
        return None
    if registry != "npm" and "/" in name:
        return None
    return registry, name


def _short(text, limit=200):
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0].rstrip(",.;:") + "..."


def _repo(url):
    url = (url or "").strip()
    url = re.sub(r"^git\+", "", url)
    url = re.sub(r"^git://", "https://", url)
    url = re.sub(r"\.git$", "", url)
    return url if url.startswith("https://") else ""


def card(registry, name, version, summary, licence, home, extra=""):
    install = {"npm": f"npm install {name}", "pypi": f"pip install {name}", "crates": f"cargo add {name}"}[registry]
    label = {"npm": "npm", "pypi": "PyPI", "crates": "crates.io"}[registry]
    return {"kind": "package", "name": name, "version": version, "summary": _short(summary), "licence": _short(licence, 40),
            "install": install, "home": home if home.startswith("https://") else "", "registry": label, "extra": extra,
            "page": {"npm": f"https://www.npmjs.com/package/{name}", "pypi": f"https://pypi.org/project/{name}/",
                     "crates": f"https://crates.io/crates/{name}"}[registry]}


def from_npm(data, name):
    repo = data.get("repository")
    repo = repo.get("url") if isinstance(repo, dict) else repo
    licence = data.get("license")
    licence = licence if isinstance(licence, str) else (licence or {}).get("type", "")
    if not data.get("version"):
        return None
    return card("npm", data.get("name", name), data["version"], data.get("description"), licence or "",
                _repo(repo) or (data.get("homepage") or ""))


def from_pypi(data, name):
    info = (data or {}).get("info") or {}
    if not info.get("version"):
        return None
    urls = {k.lower(): v for k, v in (info.get("project_urls") or {}).items() if v}
    home = next((urls[k] for k in ("source", "source code", "repository", "homepage", "github") if k in urls), "") \
        or info.get("home_page") or ""
    licence = info.get("license_expression") or ""
    if not licence:
        raw = info.get("license") or ""
        licence = raw if 0 < len(raw) <= 40 and "\n" not in raw else next(
            (c.split("::")[-1].strip() for c in info.get("classifiers", []) if c.startswith("License ::")), "")
    return card("pypi", info.get("name", name), info["version"], info.get("summary"), licence, _repo(home) or home,
                f"python {info['requires_python']}" if info.get("requires_python") else "")


def from_crates(data, name):
    crate = (data or {}).get("crate") or {}
    version = crate.get("max_stable_version") or crate.get("max_version") or crate.get("newest_version")
    if not version:
        return None
    licence = next((v.get("license") for v in (data.get("versions") or []) if v.get("num") == version), "") or ""
    return card("crates", crate.get("name", name), version, crate.get("description"), licence,
                _repo(crate.get("repository")) or crate.get("homepage") or "")


async def lookup(client, query):
    parsed = parse(query)
    if not parsed:
        return None
    hit = _cache.get(parsed)
    if hit and time.monotonic() - hit[0] < KEEP:
        return hit[1]
    registry, name = parsed
    try:
        if registry == "npm":
            r = await client.get(f"https://registry.npmjs.org/{quote(name, safe='@')}/latest", headers={"Accept": "application/json"})
        elif registry == "pypi":
            r = await client.get(f"https://pypi.org/pypi/{quote(name)}/json")
        else:
            r = await client.get(f"https://crates.io/api/v1/crates/{quote(name)}")
        if r.status_code == 404:
            result = None
        else:
            r.raise_for_status()
            result = {"npm": from_npm, "pypi": from_pypi, "crates": from_crates}[registry](r.json(), name)
    except Exception:
        return None
    if len(_cache) > 200:
        _cache.clear()
    _cache[parsed] = (time.monotonic(), result)
    return result
