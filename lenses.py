"""Lenses: a small button that narrows a web search to a kind of site. A lens is only a list of
sites, added to the search as `site:` filters, so every engine understands it. Edit the lists
(or add your own lens) under `[lenses]` in config.toml."""

DEFAULT = {
    "discussions": ["reddit.com", "news.ycombinator.com", "stackoverflow.com", "stackexchange.com",
                    "lemmy.world", "quora.com"],
    "code": ["github.com", "stackoverflow.com", "developer.mozilla.org", "docs.python.org", "gitlab.com",
             "npmjs.com", "pypi.org"],
    "academic": ["arxiv.org", "wikipedia.org", "pubmed.ncbi.nlm.nih.gov", "nature.com", "sciencedirect.com",
                 "jstor.org", "scholar.archive.org"],
}


def table(config_lenses=None):
    """The lenses on offer: the built-in ones, with config.toml's changes on top."""
    out = {k: list(v) for k, v in DEFAULT.items()}
    for name, sites in (config_lenses or {}).items():
        if isinstance(sites, list) and all(isinstance(s, str) for s in sites):
            if sites:
                out[str(name).lower()[:20]] = [s.strip() for s in sites if s.strip()][:10]
            else:
                out.pop(str(name).lower(), None)   # an empty list switches a built-in lens off
    return out


def apply(query, sites):
    """The query as the engines should hear it."""
    if not sites:
        return query
    return f"{query} ({' OR '.join('site:' + s for s in sites)})"
