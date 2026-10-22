"""Questions about dates, answered here with no network: days until, days from now, what day,
how old, week number, today's date, the moon."""
import math
import re
from datetime import date, datetime, timedelta, timezone

MONTHS = {m: i + 1 for i, m in enumerate(
    "january february march april may june july august september october november december".split())}
MONTHS.update({m[:3]: i for m, i in list(MONTHS.items())})
MONTHS["sept"] = 9
WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
_NAME = "|".join(sorted(MONTHS, key=len, reverse=True))


def easter(year):
    """Western Easter Sunday (the usual computus)."""
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month, day = divmod(h + l - 7 * m + 114, 31)
    return date(year, month, day + 1)


def _nth_weekday(year, month, weekday, n):
    first = date(year, month, 1)
    return first + timedelta(days=(weekday - first.weekday()) % 7 + 7 * (n - 1))


HOLIDAYS = {
    "christmas": lambda y: date(y, 12, 25), "christmas day": lambda y: date(y, 12, 25),
    "christmas eve": lambda y: date(y, 12, 24), "new year": lambda y: date(y, 1, 1),
    "new years": lambda y: date(y, 1, 1), "new years day": lambda y: date(y, 1, 1),
    "new years eve": lambda y: date(y, 12, 31), "halloween": lambda y: date(y, 10, 31),
    "valentines day": lambda y: date(y, 2, 14), "valentines": lambda y: date(y, 2, 14),
    "easter": easter, "st patricks day": lambda y: date(y, 3, 17),
    "independence day": lambda y: date(y, 7, 4), "thanksgiving": lambda y: _nth_weekday(y, 11, 3, 4),
}


def _clean(text):
    return re.sub(r"\s+", " ", text.lower().replace("'", "").replace("’", "")).strip(" ,.?")


def parse_date(text, today, future=True):
    """'2027-03-01', '1 march 2027', 'march 1', 'christmas', 'friday', 'tomorrow' -> a date, or None."""
    t = _clean(text)
    t = re.sub(r"^(?:the |on )", "", t)
    if t in ("today", "now"):
        return today
    if t == "tomorrow":
        return today + timedelta(days=1)
    if t == "yesterday":
        return today - timedelta(days=1)
    m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", t)
    try:
        if m:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        m = re.fullmatch(rf"(\d{{1,2}})(?:st|nd|rd|th)?(?: of)? ({_NAME})(?: (\d{{4}}))?", t) \
            or re.fullmatch(rf"({_NAME}) (\d{{1,2}})(?:st|nd|rd|th)?(?:,? (\d{{4}}))?", t)
        if m:
            a, b, year = m.groups()
            month, day = (MONTHS[b], int(a)) if a.isdigit() else (MONTHS[a], int(b))
            if year:
                return date(int(year), month, day)
            candidate = date(today.year, month, day)
            return candidate if (candidate >= today or not future) else date(today.year + 1, month, day)
    except ValueError:
        return None
    if t in HOLIDAYS:
        this = HOLIDAYS[t](today.year)
        return this if this >= today or not future else HOLIDAYS[t](today.year + 1)
    m = re.fullmatch(r"(?:next |this )?(" + "|".join(WEEKDAYS) + ")", t)
    if m:
        ahead = (WEEKDAYS.index(m.group(1)) - today.weekday()) % 7
        return today + timedelta(days=ahead or 7)
    return None


def _long(d):
    return f"{d.strftime('%A')} {d.day} {d.strftime('%B %Y')}".lower()


def _plural(n, word):
    return f"{n} {word}{'' if n == 1 else 's'}"


def _span(days):
    days = abs(days)
    weeks, rest = divmod(days, 7)
    return " ".join(x for x in (_plural(weeks, "week") if weeks else "", _plural(rest, "day") if rest else "") if x) or "0 days"


def _add_months(d, n):
    month = d.month - 1 + n
    year, month = d.year + month // 12, month % 12 + 1
    last = (date(year + (month == 12), month % 12 + 1, 1) - timedelta(days=1)).day
    return date(year, month, min(d.day, last))


def _age(born, today):
    years = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
    months = (today.month - born.month - (today.day < born.day)) % 12
    anchor = _add_months(date(born.year + years, born.month, born.day) if not (born.month == 2 and born.day == 29) else date(born.year + years, 2, 28), months)
    return years, months, (today - anchor).days


def fact(big, small):
    return {"kind": "fact", "big": big, "small": small}


# --- the moon ------------------------------------------------------------------

SYNODIC = 29.530588853
_NEW_MOON = datetime(2000, 1, 6, 18, 14, tzinfo=timezone.utc)
PHASES = [(1.85, "new moon"), (5.54, "waxing crescent"), (9.22, "first quarter"), (12.91, "waxing gibbous"),
          (16.61, "full moon"), (20.30, "waning gibbous"), (23.99, "last quarter"), (27.68, "waning crescent")]


def moon(now=None):
    now = now or datetime.now(timezone.utc)
    age = ((now - _NEW_MOON).total_seconds() / 86400) % SYNODIC
    name = next((label for limit, label in PHASES if age < limit), "new moon")
    lit = round((1 - math.cos(2 * math.pi * age / SYNODIC)) / 2 * 100)
    to_full = (SYNODIC / 2 - age) % SYNODIC
    to_new = (SYNODIC - age) % SYNODIC
    soon, label = (to_full, "full moon") if to_full < to_new else (to_new, "new moon")
    when = (now + timedelta(days=soon)).date()
    return fact(name, f"{lit}% lit · next {label} in {_plural(round(soon), 'day')}, {when.day} {when.strftime('%B').lower()}")


# --- the questions ---------------------------------------------------------------

def month_card(q, today):
    """`calendar`, `calendar october 2026`, `march 2027 calendar`, `calendar next month`."""
    import calendar as cal
    names = [m.lower() for m in cal.month_name if m]
    year, month = today.year, today.month
    m = re.fullmatch(r"(?:calendar|cal)(?: (?:for )?(this month|next month|last month|previous month))?", q)
    if m:
        step = {"next month": 1, "last month": -1, "previous month": -1}.get(m.group(1) or "", 0)
    else:
        m = re.fullmatch(rf"(?:calendar|cal)(?: for| of)? ({'|'.join(names)}|{'|'.join(n[:3] for n in names)})(?: (\d{{4}}))?", q) or \
            re.fullmatch(rf"({'|'.join(names)}|{'|'.join(n[:3] for n in names)})(?: (\d{{4}}))? calendar", q)
        if not m:
            m2 = re.fullmatch(r"(?:calendar|cal)(?: for| of)? (\d{4}) ([a-z]+)", q)
            if not m2 or m2.group(2) not in names:
                return None
            year, month, step = int(m2.group(1)), names.index(m2.group(2)) + 1, 0
        else:
            name = m.group(1)
            month = next(i for i, n in enumerate(names, 1) if n == name or n[:3] == name)
            year = int(m.group(2)) if m.group(2) else today.year
            step = 0
    month += step
    year += (month - 1) // 12
    month = (month - 1) % 12 + 1
    if not 1 <= year <= 9999:
        return None
    weeks = cal.Calendar(firstweekday=0).monthdayscalendar(year, month)
    rows = [{"week": date(year, month, next(d for d in w if d)).isocalendar()[1], "days": w} for w in weeks]
    return {"kind": "calendar", "title": f"{names[month - 1]} {year}", "rows": rows,
            "today": today.day if (today.year, today.month) == (year, month) else None,
            "days": ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]}


def answer(query, today=None, now=None):
    today = today or date.today()
    q = _clean(query)
    shown = month_card(q, today)
    if shown:
        return shown
    if re.fullmatch(r"(?:the )?(?:moon(?: phase)?|phase of the moon|moon tonight|current moon phase|what phase is the moon)", q):
        return moon(now)
    if re.fullmatch(r"(?:what(?:s| is)?(?: the)? )?(?:todays? date|date today|date|today|what day is it(?: today)?|current date)", q):
        return fact(_long(today), f"week {today.isocalendar()[1]} · day {today.timetuple().tm_yday} of {366 if today.year % 4 == 0 and (today.year % 100 or today.year % 400 == 0) else 365}")
    if re.fullmatch(r"(?:what(?:s| is)?(?: the)? )?(?:current )?(?:week number|week of the year|iso week|what week is it|which week is it)(?: now| today)?", q):
        week = today.isocalendar()
        return fact(f"week {week[1]}", f"of {week[0]} · {today.strftime('%A').lower()} {today.day} {today.strftime('%B').lower()}")

    m = re.fullmatch(r"(?:how many )?(?:days|weeks|months)? ?(?:until|till|since|to|left until|left till|before)\s+(.+)", q) \
        or re.fullmatch(r"(?:countdown to|how long until|how long till|how long to|time until)\s+(.+)", q) \
        or re.fullmatch(r"how many days (?:are there )?(?:until|till|to|before)\s+(.+)", q)
    if m and not re.search(r"\d\s*(?:am|pm)", q):
        target = parse_date(m.group(1), today)
        if target:
            delta = (target - today).days
            what = _clean(m.group(1))
            if delta == 0:
                return fact("today", f"{what} · {_long(target)}")
            return fact(_plural(abs(delta), "day"), f"{'until' if delta > 0 else 'since'} {what} · {_long(target)}"
                        + (f" · {_span(delta)}" if abs(delta) >= 7 else ""))

    m = re.fullmatch(r"(?:how many )?days between (.+?) and (.+)", q) or re.fullmatch(r"days from (.+?) to (.+)", q)
    if m:
        a, b = parse_date(m.group(1), today, False), parse_date(m.group(2), today, False)
        if a and b:
            return fact(_plural(abs((b - a).days), "day"), f"{_long(a)} to {_long(b)} · {_span((b - a).days)}")

    m = re.fullmatch(r"(?:what(?:s| is)? )?(?:the date )?(?:in )?(\d+) (day|week|month|year)s?(?: from (?:now|today|(.+))| ago)?(?: from now)?", q)
    if m and (" from " in q or q.endswith("ago") or q.startswith(("in ", "what"))):
        n, unit, base_text = int(m.group(1)), m.group(2), m.group(3)
        base = parse_date(base_text, today) if base_text else today
        sign = -1 if q.endswith(" ago") else 1
        if base and n < 100000:
            try:
                if unit in ("day", "week"):
                    result = base + timedelta(days=sign * n * (7 if unit == "week" else 1))
                else:
                    result = _add_months(base, sign * n * (12 if unit == "year" else 1))
            except (ValueError, OverflowError):
                return None
            return fact(_long(result), f"{n} {unit}{'' if n == 1 else 's'} {'ago' if sign < 0 else 'from ' + ('now' if base == today else _long(base))}")

    m = re.fullmatch(r"what day (?:of the week )?(?:is|was|will be|does|did)\s+(.+?)(?: fall on| land on)?", q) \
        or re.fullmatch(r"day of the week (?:for|of)\s+(.+)", q)
    if m:
        target = parse_date(m.group(1), today)
        if target:
            return fact(target.strftime("%A").lower(), f"{_long(target)} · {'today' if target == today else _span((target - today).days) + (' from now' if target > today else ' ago')}")

    m = re.fullmatch(r"(?:how old is (?:someone |a person |somebody )?(?:born|who was born)(?: on| in)?|age (?:of someone )?born(?: on)?|age(?: of)?|born(?: on)?)\s+(.+?)(?: how old)?", q)
    if m:
        born = parse_date(m.group(1), today, False)
        if born and born <= today:
            years, months, days = _age(born, today)
            nxt = date(today.year, born.month, min(born.day, 28 if born.month == 2 else born.day))
            if nxt < today:
                nxt = date(today.year + 1, nxt.month, nxt.day)
            soon = "birthday today" if nxt == today else f"next birthday in {_plural((nxt - today).days, 'day')}"
            return fact(f"{years} years old", f"born {_long(born)} · {_plural(years, 'year')} {_plural(months, 'month')} {_plural(days, 'day')} · {soon}")
    return None
