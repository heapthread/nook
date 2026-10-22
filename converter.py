"""The /convert page: money, units and the time somewhere else, as forms instead of typed queries.

Unit maths is done here (the same tables as the search box). Currency rates come from the
European Central Bank via Frankfurter (no key)."""
import time

import answers
import cards

KINDS = {
    "length": ["mm", "cm", "m", "km", "in", "ft", "yd", "mi", "nmi"],
    "weight": ["mg", "g", "kg", "oz", "lb", "st", "t"],
    "volume": ["ml", "l", "tsp", "tbsp", "floz", "cup", "pt", "qt", "gal"],
    "temperature": ["c", "f", "k"],
    "speed": ["ms", "kph", "mph", "kn", "fps"],
    "area": ["m2", "km2", "ha", "ft2", "acre", "mi2", "cm2", "in2", "yd2", "mm2"],
    "data": ["b", "kb", "mb", "gb", "tb", "kib", "mib", "gib", "tib"],
    "pressure": ["pa", "hpa", "kpa", "mbar", "bar", "psi", "atm", "mmhg", "inhg"],
    "energy": ["j", "kj", "cal", "kcal", "wh", "kwh", "btu"],
    "time": ["s", "min", "h", "d", "wk"],
}
TABLE = {"weight": "mass"}   # the name on the page -> the name in answers._UNITS
NAMES = {"c": "celsius", "f": "fahrenheit", "k": "kelvin", "ms": "m/s", "kph": "km/h", "mph": "mph", "kn": "knots", "fps": "ft/s",
         "m2": "m²", "km2": "km²", "ft2": "ft²", "mi2": "mi²", "cm2": "cm²", "in2": "in²", "yd2": "yd²", "mm2": "mm²",
         "floz": "fl oz", "tsp": "teaspoon", "tbsp": "tablespoon", "pt": "pint", "qt": "quart", "gal": "gallon", "st": "stone",
         "t": "tonne", "h": "hours", "d": "days", "wk": "weeks", "s": "seconds", "min": "minutes", "nmi": "nautical mi",
         "mmhg": "mmHg", "inhg": "inHg", "hpa": "hPa", "kpa": "kPa", "pa": "Pa", "wh": "Wh", "kwh": "kWh", "kj": "kJ", "j": "J"}
POPULAR = ["USD", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "CNY", "INR", "SEK", "NOK", "DKK", "PLN", "CZK", "BRL", "MXN", "TRY", "ZAR"]
KEEP = 3600
_rates = {}


def name(unit):
    return NAMES.get(unit, unit)


def shown(x):
    return answers._number(float(f"{x:.6g}"))


def convert(kind, value, source):
    """Every unit of this kind, for `value` of `source`: [(unit, name, text)]. None when something is not recognised."""
    units = KINDS.get(kind)
    if not units or source not in units:
        return None
    if kind == "temperature":
        return [(u, name(u), shown(answers._temperature(value, source, u))) for u in units]
    table = answers._UNITS[TABLE.get(kind, kind)]
    return [(u, name(u), shown(value * table[source] / table[u])) for u in units]


def number(text, fallback=1.0):
    try:
        return float((text or "").replace(",", "").strip())
    except ValueError:
        return fallback


async def money(client, amount, source):
    """Rates for every currency from `source`: ([(code, text)], note) or None."""
    if source not in cards.CURRENCIES:
        return None
    hit = _rates.get(source)
    if hit and time.monotonic() - hit[0] < KEEP:
        data = hit[1]
    else:
        try:
            r = await client.get("https://api.frankfurter.dev/v1/latest", params={"base": source})
            r.raise_for_status()
            data = r.json()
        except Exception:
            return None
        if len(_rates) > 30:
            _rates.clear()
        _rates[source] = (time.monotonic(), data)
    rates = dict(data.get("rates") or {})
    rates[source] = 1.0
    ordered = [c for c in POPULAR if c in rates] + sorted(c for c in rates if c not in POPULAR)
    rows = [(c, f"{amount * rates[c]:,.2f}") for c in ordered]
    return rows, f"rates from the European Central Bank, {data.get('date', '')}"
