"""Things nook can answer by itself: bangs (jump straight to a site), sums, unit conversions."""
import ast
import operator
import re
from urllib.parse import quote

BANGS = {
    "w": "https://en.wikipedia.org/wiki/Special:Search?search={}",
    "yt": "https://www.youtube.com/results?search_query={}",
    "gh": "https://github.com/search?q={}",
    "hn": "https://hn.algolia.com/?q={}",
    "so": "https://stackoverflow.com/search?q={}",
    "r": "https://www.reddit.com/search/?q={}",
    "mdn": "https://developer.mozilla.org/en-US/search?q={}",
    "pypi": "https://pypi.org/search/?q={}",
    "npm": "https://www.npmjs.com/search?q={}",
    "maps": "https://www.openstreetmap.org/search?query={}",
    "a": "https://www.amazon.com/s?k={}",
    "imdb": "https://www.imdb.com/find/?q={}",
    "g": "https://www.google.com/search?q={}",
    "ddg": "https://duckduckgo.com/?q={}",
    "bing": "https://www.bing.com/search?q={}",
    # engines nook can't ask for you: these open in your own browser, which can answer their checks
    "brave": "https://search.brave.com/search?q={}",
    "sp": "https://www.startpage.com/do/search?q={}",
    "mojeek": "https://www.mojeek.com/search?q={}",
    "qwant": "https://www.qwant.com/?q={}",
    "yahoo": "https://search.yahoo.com/search?p={}",
}


def bang_target(query, extra=None):
    """`!w sourdough` or `sourdough !w` gives the address to send the visitor to, else None."""
    table = {**BANGS, **{k.lower(): v for k, v in (extra or {}).items()}}
    m = re.match(r"^!(\w+)\s+(.+)$", query.strip())
    leading = bool(m)
    if m:
        name, rest = m.group(1), m.group(2)
    else:
        m = re.match(r"^(.+?)\s+!(\w+)$", query.strip())
        if not m:
            return None
        rest, name = m.group(1), m.group(2)
    template = table.get(name.lower())
    if template is None:
        if leading and re.fullmatch(r"[a-z0-9]{1,15}", name.lower()):   # not one of ours: DuckDuckGo knows thousands
            return "https://duckduckgo.com/?q=" + quote(f"!{name} {rest.strip()}", safe="")
        return None
    if not template.startswith("https://") or "{}" not in template:
        return None
    return template.replace("{}", quote(rest.strip(), safe=""))


# --- sums ---------------------------------------------------------------

_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
        ast.Div: operator.truediv, ast.Mod: operator.mod, ast.FloorDiv: operator.floordiv,
        ast.Pow: operator.pow}


def _eval(node):
    if isinstance(node, ast.Expression):
        return _eval(node.body)
    if isinstance(node, ast.Constant) and type(node.value) in (int, float):
        return node.value
    if isinstance(node, ast.UnaryOp) and type(node.op) in (ast.USub, ast.UAdd):
        v = _eval(node.operand)
        return -v if isinstance(node.op, ast.USub) else v
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        a, b = _eval(node.left), _eval(node.right)
        if isinstance(node.op, ast.Pow) and (abs(b) > 1000 or abs(a) > 1e9):
            raise ValueError("too big")
        return _OPS[type(node.op)](a, b)
    raise ValueError("not a sum")


def _number(v):
    if isinstance(v, float) and v.is_integer() and abs(v) < 1e15:
        v = int(v)
    if isinstance(v, int):
        return f"{v:,}"
    return format(v, ",.10g")


def calculate(query):
    text = query.strip().rstrip("=").strip()
    if not re.fullmatch(r"[\d\s.+\-*/^()%×÷x]+", text) or re.fullmatch(r"[\d.\-]+", text):
        return None  # not sums, or a phone number / date that merely contains hyphens
    expr = re.sub(r"(?<=[\d)])\s*[x×]\s*(?=[\d(])", "*", text).replace("÷", "/").replace("^", "**")
    if "x" in expr or not re.search(r"\d\s*[-+*/%)]|[(]", expr):
        return None  # a bare number, or something that isn't a sum
    try:
        value = _eval(ast.parse(expr, mode="eval"))
    except (ValueError, SyntaxError, ZeroDivisionError, OverflowError, RecursionError, MemoryError):
        return None
    if isinstance(value, float) and (value != value or value in (float("inf"), float("-inf"))):
        return None
    return f"{text} = {_number(value)}"


# --- units --------------------------------------------------------------

_UNITS = {
    "length": {"mm": 0.001, "cm": 0.01, "m": 1, "km": 1000, "in": 0.0254, "ft": 0.3048,
               "yd": 0.9144, "mi": 1609.344, "nmi": 1852},
    "mass": {"mg": 0.001, "g": 1, "kg": 1000, "oz": 28.349523125, "lb": 453.59237,
             "st": 6350.29318, "t": 1e6},
    "volume": {"ml": 0.001, "l": 1, "tsp": 0.00492892159375, "tbsp": 0.01478676478125,
               "floz": 0.0295735295625, "cup": 0.2365882365, "pt": 0.473176473,
               "qt": 0.946352946, "gal": 3.785411784},
    "speed": {"ms": 1, "kph": 1 / 3.6, "mph": 0.44704, "kn": 1852 / 3600, "fps": 0.3048},
    "pressure": {"pa": 1, "hpa": 100, "kpa": 1000, "mbar": 100, "bar": 100000, "psi": 6894.757293168,
                 "atm": 101325, "mmhg": 133.322387415, "inhg": 3386.389},
    "area": {"mm2": 1e-6, "cm2": 1e-4, "m2": 1, "km2": 1e6, "ha": 1e4, "in2": 0.00064516, "ft2": 0.09290304,
             "yd2": 0.83612736, "acre": 4046.8564224, "mi2": 2589988.110336},
    "datarate": {"bps": 0.125, "kbps": 125, "mbps": 125000, "gbps": 125000000, "b/s": 1, "kb/s": 1e3, "mb/s": 1e6,
                 "gb/s": 1e9, "kib/s": 1024, "mib/s": 1024 ** 2, "gib/s": 1024 ** 3},
    "energy": {"j": 1, "kj": 1000, "cal": 4.184, "kcal": 4184, "wh": 3600, "kwh": 3.6e6, "btu": 1055.05585},
    "data": {"b": 1, "kb": 1e3, "mb": 1e6, "gb": 1e9, "tb": 1e12,
             "kib": 1024, "mib": 1024 ** 2, "gib": 1024 ** 3, "tib": 1024 ** 4},
    "time": {"s": 1, "min": 60, "h": 3600, "d": 86400, "wk": 604800},
    "temperature": {"c": 0, "f": 0, "k": 0},
}
_ALIASES = {
    "mm": "mm", "millimeter": "mm", "millimetre": "mm", "cm": "cm", "centimeter": "cm", "centimetre": "cm",
    "m": "m", "meter": "m", "metre": "m", "km": "km", "kilometer": "km", "kilometre": "km",
    "in": "in", "inch": "in", "inches": "in", "ft": "ft", "foot": "ft", "feet": "ft",
    "yd": "yd", "yard": "yd", "mi": "mi", "mile": "mi", "nmi": "nmi",
    "mg": "mg", "milligram": "mg", "g": "g", "gram": "g", "kg": "kg", "kilogram": "kg", "kilo": "kg",
    "oz": "oz", "ounce": "oz", "lb": "lb", "lbs": "lb", "pound": "lb", "st": "st", "stone": "st",
    "t": "t", "tonne": "t", "ml": "ml", "milliliter": "ml", "millilitre": "ml",
    "l": "l", "liter": "l", "litre": "l", "tsp": "tsp", "teaspoon": "tsp", "tbsp": "tbsp",
    "tablespoon": "tbsp", "floz": "floz", "cup": "cup", "pt": "pt", "pint": "pt", "qt": "qt",
    "quart": "qt", "gal": "gal", "gallon": "gal",
    "mph": "mph", "kph": "kph", "kmh": "kph", "kmph": "kph", "km/h": "kph", "ms": "ms", "m/s": "ms", "mps": "ms",
    "knot": "kn", "kn": "kn", "kt": "kn", "ft/s": "fps", "fps": "fps",
    "pa": "pa", "pascal": "pa", "hpa": "hpa", "kpa": "kpa", "mbar": "mbar", "millibar": "mbar", "bar": "bar", "psi": "psi",
    "atm": "atm", "atmosphere": "atm", "mmhg": "mmhg", "torr": "mmhg", "inhg": "inhg",
    "mm2": "mm2", "cm2": "cm2", "m2": "m2", "sqm": "m2", "km2": "km2", "sqkm": "km2", "ha": "ha", "hectare": "ha",
    "ft2": "ft2", "sqft": "ft2", "sqin": "in2", "in2": "in2", "yd2": "yd2", "acre": "acre", "mi2": "mi2", "sqmi": "mi2",
    "bps": "bps", "kbps": "kbps", "mbps": "mbps", "gbps": "gbps", "b/s": "b/s", "kb/s": "kb/s", "mb/s": "mb/s", "gb/s": "gb/s",
    "kib/s": "kib/s", "mib/s": "mib/s", "gib/s": "gib/s",
    "j": "j", "joule": "j", "kj": "kj", "cal": "cal", "calorie": "cal", "kcal": "kcal", "wh": "wh", "kwh": "kwh", "btu": "btu",
    "b": "b", "byte": "b", "kb": "kb", "kilobyte": "kb", "mb": "mb", "megabyte": "mb",
    "gb": "gb", "gigabyte": "gb", "tb": "tb", "terabyte": "tb", "kib": "kib", "mib": "mib",
    "gib": "gib", "tib": "tib",
    "s": "s", "sec": "s", "second": "s", "min": "min", "minute": "min", "h": "h", "hr": "h",
    "hour": "h", "d": "d", "day": "d", "wk": "wk", "week": "wk",
    "c": "c", "celsius": "c", "f": "f", "fahrenheit": "f", "k": "k", "kelvin": "k",
}
_KIND = {unit: kind for kind, units in _UNITS.items() for unit in units}


def _unit(word):
    w = word.strip().lower().replace("°", "").replace("degrees", "").replace("degree", "").strip()
    w = re.sub(r"\s+", "", w).replace("²", "2").replace("per", "/")
    if w in _ALIASES:
        return _ALIASES[w]
    if w.endswith("es") and w[:-2] in _ALIASES:
        return _ALIASES[w[:-2]]
    if w.endswith("s") and w[:-1] in _ALIASES:
        return _ALIASES[w[:-1]]
    return None


def _temperature(value, a, b):
    kelvin = {"c": value + 273.15, "f": (value - 32) * 5 / 9 + 273.15, "k": value}[a]
    return {"c": kelvin - 273.15, "f": (kelvin - 273.15) * 9 / 5 + 32, "k": kelvin}[b]


def convert(query):
    m = re.fullmatch(r"\s*(-?[\d,]*\.?\d+)\s*([a-zA-Z°][a-zA-Z0-9°/ ²]*?)\s+(?:in|to|into|as)\s+([a-zA-Z°][a-zA-Z0-9°/ ²]*?)\s*",
                     query)
    if not m:
        return None
    value = float(m.group(1).replace(",", ""))
    a, b = _unit(m.group(2)), _unit(m.group(3))
    if not a or not b or _KIND[a] != _KIND[b]:
        return None
    if _KIND[a] == "temperature":
        result = _temperature(value, a, b)
    else:
        units = _UNITS[_KIND[a]]
        result = value * units[a] / units[b]
    shown = _number(float(f"{result:.6g}"))
    return f"{_number(value)} {m.group(2).strip()} = {shown} {m.group(3).strip()}"


def answer(query):
    """A one-line answer if the query is a sum or a unit conversion, else None."""
    return calculate(query) or convert(query)
