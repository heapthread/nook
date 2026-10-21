import asyncio

from engines import Result
from merge import gather, merge, normalize


def r(url, engine, rank, snippet=""):
    return Result(title=url, url=url, snippet=snippet, engines=[engine], rank=rank)


def test_normalize_ignores_noise():
    assert normalize("https://www.Example.com/a/?utm_source=x") == normalize("http://example.com/a")
    assert normalize("https://example.com/a?id=1") != normalize("https://example.com/a?id=2")


def test_agreement_rises_and_engines_combine():
    a = [r("https://one.com", "a", 0), r("https://both.com/", "a", 1, "short")]
    b = [r("https://two.com", "b", 0), r("https://www.both.com", "b", 1, "a longer snippet")]
    merged = merge([a, b])
    assert [x.url for x in merged][0] == "https://both.com/"
    assert merged[0].engines == ["a", "b"]
    assert merged[0].snippet == "a longer snippet"
    assert len(merged) == 3


class Fake:
    def __init__(self, name, results=None, boom=False):
        self.NAME, self._r, self._boom = name, results or [], boom

    async def search(self, client, query, page=1):
        if self._boom:
            raise RuntimeError("blocked")
        return self._r


def test_failing_engine_is_reported_not_fatal():
    good = Fake("good", [r("https://x.com", "good", 0)])
    results, failed = asyncio.run(gather(None, [good, Fake("bad", boom=True), Fake("empty")], "q"))
    assert [x.url for x in results] == ["https://x.com"]
    assert failed == ["bad", "empty"]
