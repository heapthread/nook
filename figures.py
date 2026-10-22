"""Percentages and number bases, worked out here: `15% of 80`, `20 is what percent of 50`,
`increase 80 by 15%`, `20% off 80`, `change from 50 to 80`, `255 in binary`, `0xff to decimal`."""
import re

NUM = r"(-?\d[\d,]*\.?\d*|-?\.\d+)"
BASES = {"binary": 2, "bin": 2, "octal": 8, "oct": 8, "decimal": 10, "dec": 10, "hex": 16, "hexadecimal": 16}
DIGITS = "0123456789abcdefghijklmnopqrstuvwxyz"


def _n(text):
    return float(text.replace(",", ""))


def _show(v):
    if v == int(v) and abs(v) < 1e15:
        return f"{int(v):,}"
    return f"{v:,.4f}".rstrip("0").rstrip(".")


def _fact(big, small):
    return {"kind": "fact", "big": big, "small": small}


def to_base(n, base):
    if n == 0:
        return "0"
    out, neg, n = "", n < 0, abs(n)
    while n:
        n, r = divmod(n, base)
        out = DIGITS[r] + out
    return ("-" if neg else "") + out


def _money(text):
    """'200,000', '200k', '1.5m', '$300k' -> a number."""
    t = text.lower().replace(",", "").lstrip("$€£")
    scale = 1
    if t.endswith("k"):
        scale, t = 1_000, t[:-1]
    elif t.endswith("m"):
        scale, t = 1_000_000, t[:-1]
    return float(t) * scale


AMT = r"[$€£]?\d[\d,]*\.?\d*[km]?"


def loan(q):
    """`loan 200000 at 4% for 30 years`: what each month costs and what the loan costs in all."""
    m = re.match(rf"^(?:loan|mortgage|monthly payment(?: on| for)?|repayments? (?:on|for)|finance) ({AMT}) (?:at|with|@) (\d+\.?\d*) ?(?:%|percent)(?: interest)?(?: (?:for|over|in))? (\d+\.?\d*) ?(years?|yrs?|months?|mos?)$", q)
    if not m:
        return None
    principal, rate, term = _money(m.group(1)), float(m.group(2)), float(m.group(3))
    months = round(term * (12 if m.group(4).startswith("y") else 1))
    if not (0 < principal < 1e12 and 0 <= rate <= 100 and 1 <= months <= 1200):
        return None
    r = rate / 1200
    pay = principal / months if r == 0 else principal * r / (1 - (1 + r) ** -months)
    total = pay * months
    return _fact(f"{_show(round(pay, 2))} a month",
                 f"{_show(principal)} at {_show(rate)}% over {months // 12 if months % 12 == 0 else months} "
                 f"{'years' if months % 12 == 0 else 'months'} · {_show(round(total))} paid in all, "
                 f"{_show(round(total - principal))} of it interest")


def split(q):
    """`split 84 between 3`, `split 84 between 3 with 15% tip`, `tip 15% on 48`."""
    m = re.match(rf"^(?:split|share|divide) ({AMT})(?: bill)? (?:between|among|by|with) (\d{{1,3}})(?: (?:people|ways|persons))?(?: (?:with|plus|and) (\d+\.?\d*) ?(?:%|percent) tip)?$", q) or \
        re.match(rf"^({AMT}) (?:split|shared|divided) (?:between |by )?(\d{{1,3}})(?: (?:people|ways))?(?: (?:with|plus|and) (\d+\.?\d*) ?(?:%|percent) tip)?$", q)
    if m:
        bill, people, tip = _money(m.group(1)), int(m.group(2)), float(m.group(3) or 0)
        if people >= 1 and bill > 0:
            each = bill * (1 + tip / 100) / people
            note = f"{_show(bill)} between {people}" + (f", with a {_show(tip)}% tip" if tip else "")
            return _fact(f"{_show(round(each, 2))} each", note)
    m = re.match(rf"^(?:tip|gratuity) (\d+\.?\d*) ?(?:%|percent) (?:on|of|for) ({AMT})$", q) or \
        re.match(rf"^(\d+\.?\d*) ?(?:%|percent) tip (?:on|of|for) ({AMT})$", q)
    if m:
        tip, bill = float(m.group(1)), _money(m.group(2))
        if bill > 0:
            return _fact(f"{_show(round(bill * tip / 100, 2))} tip", f"{_show(bill)} plus {_show(tip)}% makes {_show(round(bill * (1 + tip / 100), 2))}")
    return None


def percent(q):
    m = re.match(rf"^(?:what is |what's |calculate )?{NUM} ?(?:%|percent|per cent) of {NUM}$", q)
    if m:
        p, whole = _n(m.group(1)), _n(m.group(2))
        return _fact(_show(p / 100 * whole), f"{_show(p)}% of {_show(whole)}")
    for pattern, order in ((rf"^{NUM} is what (?:%|percent|per cent) of {NUM}$", (0, 1)),
                           (rf"^what (?:%|percent|per cent) of {NUM} is {NUM}$", (1, 0)),
                           (rf"^what (?:%|percent|per cent) is {NUM} of {NUM}$", (0, 1))):
        m = re.match(pattern, q)
        if m:
            a, b = _n(m.group(order[0] + 1)), _n(m.group(order[1] + 1))
            if b:
                return _fact(_show(a / b * 100) + "%", f"{_show(a)} out of {_show(b)}")
    m = re.match(rf"^(increase|raise|add|decrease|reduce|lower|subtract|take) {NUM} (?:by|off|with|from)? ?{NUM} ?(?:%|percent)$", q)
    if m:
        up = m.group(1) in ("increase", "raise", "add")
        base, p = _n(m.group(2)), _n(m.group(3))
        out = base * (1 + p / 100) if up else base * (1 - p / 100)
        return _fact(_show(out), f"{_show(base)} {'plus' if up else 'minus'} {_show(p)}%")
    m = re.match(rf"^{NUM} ?(?:%|percent) (off|discount|more|less|extra|tax|vat) (?:of |on |from )?{NUM}$", q)
    if m:
        p, word, base = _n(m.group(1)), m.group(2), _n(m.group(3))
        down = word in ("off", "discount", "less")
        out = base * (1 - p / 100) if down else base * (1 + p / 100)
        return _fact(_show(out), f"{_show(base)} with {_show(p)}% {'off' if down else 'added'}")
    m = re.match(rf"^(?:(?:percent|percentage|%) )?(?:change|increase|difference) (?:from|between) {NUM} (?:to|and) {NUM}$", q)
    if m:
        a, b = _n(m.group(1)), _n(m.group(2))
        if a:
            change = (b - a) / abs(a) * 100
            return _fact(("+" if change > 0 else "") + _show(change) + "%", f"from {_show(a)} to {_show(b)}")
    return None


def base_convert(q):
    m = re.match(r"^(?:convert )?(?:(binary|octal|hex(?:adecimal)?|decimal) )?(0x[0-9a-f]+|0b[01]+|0o[0-7]+|[0-9a-f]+) ?(binary|octal|hex(?:adecimal)?|decimal)? (?:in|to|into|as) (binary|bin|octal|oct|hex(?:adecimal)?|decimal|dec)$", q)
    if not m:
        return None
    word, digits, after, target = m.groups()
    given = word or after
    if digits.startswith("0x"):
        source = 16
    elif digits.startswith("0b"):
        source = 2
    elif digits.startswith("0o"):
        source = 8
    elif given:
        source = BASES[given]
    elif re.fullmatch(r"\d+", digits):
        source = 10
    else:
        return None   # letters with no base named: more likely a word than a hex number
    try:
        n = int(digits[2:] if digits[:2] in ("0x", "0b", "0o") else digits, source)
    except ValueError:
        return None
    to = BASES[target]
    if source == to or abs(n) > 10 ** 30:
        return None
    names = {2: "binary", 8: "octal", 10: "decimal", 16: "hexadecimal"}
    prefix = {2: "0b", 8: "0o", 16: "0x"}.get(to, "")
    return _fact(prefix + to_base(n, to), f"{digits} ({names[source]}) in {names[to]}")


ROMAN = [(1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"), (50, "L"), (40, "XL"),
         (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")]


def to_roman(n):
    out = ""
    for value, letters in ROMAN:
        while n >= value:
            out += letters
            n -= value
    return out


def from_roman(text):
    """MCMXCIX -> 1999, or None when it is not a correctly written numeral."""
    total, rest = 0, text.upper()
    for value, letters in ROMAN:
        while rest.startswith(letters):
            total += value
            rest = rest[len(letters):]
    return total if not rest and total and to_roman(total) == text.upper() else None


def roman(q):
    m = re.match(r"^(?:roman numerals?|roman)(?: for| of)? (\d{1,4})$", q) or re.match(r"^(\d{1,4}) (?:in|to|as|into) roman(?: numerals?)?$", q)
    if m and 1 <= int(m.group(1)) <= 3999:
        return _fact(to_roman(int(m.group(1))), f"{int(m.group(1))} in roman numerals")
    m = re.match(r"^(?:roman )?([mdclxvi]{1,15}) (?:in|to|as|into) (?:decimal|numbers?|arabic|digits)$", q) or re.match(r"^roman ([mdclxvi]{1,15})$", q)
    if m and from_roman(m.group(1)):
        return _fact(str(from_roman(m.group(1))), f"{m.group(1).upper()} in numbers")
    return None


def answer(query, now=None):
    q = re.sub(r"\s+", " ", query.strip().lower().rstrip("?"))
    try:
        return percent(q) or base_convert(q) or loan(q) or split(q) or roman(q)
    except (ValueError, ZeroDivisionError, OverflowError):
        return None
