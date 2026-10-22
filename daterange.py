"""`before:2020`, `after:2023-05`, `during:2021`: search operators for dates.

They are taken out of the words the engines hear and turned into the date range some engines can
apply themselves (DuckDuckGo). A year or a month means its first day for `after:` and `during:`,
and the day before it begins for `before:`, the way people read them: `before:2020` is everything up
to the end of 2019. `after:2020-05-17` includes that day."""
import re
from datetime import date, timedelta

START = date(1995, 1, 1)   # what "any time before" means: the web's own beginning
_OP = re.compile(r"(?<!\S)(before|after|during):(\d{4})(?:-(\d{1,2}))?(?:-(\d{1,2}))?(?!\S)", re.I)


def _first_day(y, m, d):
    try:
        return date(int(y), int(m or 1), int(d or 1))
    except ValueError:
        return None


def _last_day(y, m, d):
    start = _first_day(y, m, d)
    if start is None:
        return None
    if d:
        return start
    if m:
        return (date(start.year + (start.month == 12), start.month % 12 + 1, 1)) - timedelta(days=1)
    return date(start.year, 12, 31)


def parse(query, today=None):
    """-> (the query without the operators, (from, to) as 'YYYY-MM-DD' strings, or None)."""
    today = today or date.today()
    after = before = None
    for m in _OP.finditer(query):
        word, y, mo, d = m.group(1).lower(), m.group(2), m.group(3), m.group(4)
        if word == "after":
            after = _first_day(y, mo, d) or after
        elif word == "before":
            first = _first_day(y, mo, d)
            before = (first - timedelta(days=1)) if first else before
        else:
            after, before = _first_day(y, mo, d) or after, _last_day(y, mo, d) or before
    clean = re.sub(r"\s+", " ", _OP.sub(" ", query)).strip()
    if after is None and before is None:
        return clean or query, None
    low, high = after or START, before or today
    if low > high:
        low, high = high, low
    return clean or query, (low.isoformat(), high.isoformat())
