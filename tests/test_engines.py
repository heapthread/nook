from pathlib import Path

from engines import bing, duckduckgo, wikipedia

FIX = Path(__file__).parent / "fixtures"


def read(name):
    return (FIX / name).read_text(encoding="utf-8")


def check(results):
    assert len(results) >= 3
    for i, r in enumerate(results):
        assert r.title and r.url.startswith("http")
        assert r.rank == i


def test_duckduckgo():
    results = duckduckgo.parse(read("duckduckgo.html"))
    check(results)
    assert "duckduckgo.com" not in results[0].url


def test_bing_unwraps_redirects():
    results = bing.parse(read("bing.html"))
    check(results)
    assert not any("bing.com/ck/a" in r.url for r in results)
    assert results[0].url == "https://www.w3schools.com/python/"


def test_wikipedia():
    results = wikipedia.parse(read("wikipedia.json"))
    check(results)
    assert "<" not in results[0].snippet


def test_snippets_keep_their_spaces():
    for mod, fixture in ((duckduckgo, "duckduckgo.html"), (bing, "bing.html")):
        for r in mod.parse(read(fixture)):
            assert not any(len(w) > 40 and w.isalpha() for w in r.snippet.split()), r.snippet


def test_bing_images():
    from engines import bing_images
    results = bing_images.parse(read("bing_images.html"))
    assert len(results) >= 10
    for r in results:
        assert r.thumb.startswith("http") and r.full.startswith("http") and r.page.startswith("http")
        assert "\ue000" not in r.title


def test_duckduckgo_videos():
    from engines import duckduckgo_videos
    results = duckduckgo_videos.parse(read("ddg_videos.json"))
    assert len(results) >= 10
    for r in results:
        assert r.title and r.url.startswith("http") and r.thumb.startswith("http")
    assert any(r.duration for r in results)
    assert any("panda" in r.title.lower() for r in results)


def test_yahoo():
    from engines import yahoo
    results = yahoo.parse(read("yahoo.html"))
    check(results)
    assert not any("r.search.yahoo.com" in r.url for r in results)  # real addresses, not Yahoo's redirects
    assert results[0].url.startswith("https://www.kingarthurbaking.com/")
    assert all(r.snippet for r in results)


def test_seznam():
    from engines import seznam
    results = seznam.parse(read("seznam.html"))
    check(results)
    assert results[0].url.startswith("https://www.motherearthnews.com/")
    assert all(r.snippet for r in results)
    assert results[0].title.startswith("How to Use Sourdough Starter")  # words kept apart
    hosts = [r.url.split("/")[2] for r in results]
    assert not any(h.endswith((".cz", ".sk")) for h in hosts)   # the Czech shops are gone
    assert "www.kingarthurbaking.com" in hosts and "breadtopia.com" in hosts
