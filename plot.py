"""`plot sin(x)`, `graph x^2 - 3`, `y = 2x + 1`, `plot sin(x), cos(x) from -5 to 5`.

A small expression parser of its own (no eval), so nothing typed can run as code. The curve is
worked out here and drawn as an SVG in nook's colours."""
import math
import re

W, H = 640, 340
LEFT, RIGHT, TOP, BOTTOM = 40, 12, 12, 26
SAMPLES = 480

FUNCS = {
    "sin": math.sin, "cos": math.cos, "tan": math.tan, "asin": math.asin, "acos": math.acos,
    "atan": math.atan, "sinh": math.sinh, "cosh": math.cosh, "tanh": math.tanh, "sqrt": math.sqrt,
    "abs": abs, "ln": math.log, "log": math.log10, "log10": math.log10, "log2": math.log2,
    "exp": math.exp, "floor": math.floor, "ceil": math.ceil, "round": round,
}
CONSTS = {"pi": math.pi, "e": math.e, "tau": math.tau}
TRIG = {"sin", "cos", "tan"}


class Bad(Exception):
    pass


def tokens(text):
    out, i = [], 0
    text = text.replace("**", "^").replace("×", "*").replace("−", "-").replace("÷", "/").replace("π", "pi")
    while i < len(text):
        c = text[i]
        if c.isspace():
            i += 1
        elif c.isdigit() or c == ".":
            m = re.match(r"\d*\.?\d+(?:[eE][+-]?\d+)?|\d+\.", text[i:])
            if not m:
                raise Bad("number")
            out.append(("n", float(m.group(0))))
            i += len(m.group(0))
        elif c.isalpha():
            m = re.match(r"[a-zA-Z]+\d*", text[i:])
            word = m.group(0).lower()
            if word not in FUNCS and word not in CONSTS and word != "x":
                # "2xy" or "xsin(x)": split into known pieces, else give up
                if re.fullmatch(r"x+", word):
                    for _ in word:
                        out.append(("id", "x"))
                    i += len(word)
                    continue
                raise Bad(word)
            out.append(("id", word))
            i += len(word)
        elif c in "+-*/^(),":
            out.append((c, c))
            i += 1
        else:
            raise Bad(c)
    return out


class Parser:
    """expr: term (+|- term)*   term: factor ((*|/|nothing) factor)*   factor: -factor | power"""

    def __init__(self, toks):
        self.t, self.i, self.uses_trig = toks, 0, False

    def peek(self):
        return self.t[self.i][0] if self.i < len(self.t) else None

    def take(self, kind=None):
        if self.i >= len(self.t) or (kind and self.t[self.i][0] != kind):
            raise Bad("syntax")
        self.i += 1
        return self.t[self.i - 1]

    def expr(self):
        node = self.term()
        while self.peek() in ("+", "-"):
            op = self.take()[0]
            right = self.term()
            node = ("+" if op == "+" else "-", node, right)
        return node

    def term(self):
        node = self.factor()
        while True:
            p = self.peek()
            if p in ("*", "/"):
                op = self.take()[0]
                node = (op, node, self.factor())
            elif p in ("n", "id", "("):      # "2x", "3sin(x)", "(x+1)(x-1)"
                node = ("*", node, self.factor())
            else:
                return node

    def factor(self):
        if self.peek() == "-":
            self.take()
            return ("neg", self.factor())
        if self.peek() == "+":
            self.take()
            return self.factor()
        return self.power()

    def power(self):
        base = self.atom()
        if self.peek() == "^":
            self.take()
            return ("^", base, self.factor())   # right-leaning: 2^3^2 = 2^(3^2), 2^-1 works
        return base

    def atom(self):
        kind = self.peek()
        if kind == "n":
            return ("n", self.take()[1])
        if kind == "(":
            self.take()
            node = self.expr()
            self.take(")")
            return node
        if kind == "id":
            name = self.take()[1]
            if name == "x":
                return ("x",)
            if name in CONSTS:
                return ("n", CONSTS[name])
            if name in FUNCS:
                if name in TRIG:
                    self.uses_trig = True
                if self.peek() == "(":
                    self.take()
                    arg = self.expr()
                    self.take(")")
                else:
                    arg = self.power()    # "sin x"
                return ("f", name, arg)
        raise Bad("syntax")


def compile_expr(text):
    """-> (function of x, uses trigonometry). Raises Bad for anything that isn't plain maths."""
    p = Parser(tokens(text))
    tree = p.expr()
    if p.i != len(p.t):
        raise Bad("leftover")

    def run(node, x):
        k = node[0]
        if k == "n":
            return node[1]
        if k == "x":
            return x
        if k == "neg":
            return -run(node[1], x)
        if k == "f":
            return FUNCS[node[1]](run(node[2], x))
        a, b = run(node[1], x), run(node[2], x)
        if k == "+":
            return a + b
        if k == "-":
            return a - b
        if k == "*":
            return a * b
        if k == "/":
            return a / b
        if k == "^":
            if a < 0 and b != int(b):
                raise ValueError("complex")
            return a ** b
        raise Bad(k)

    def f(x):
        try:
            v = run(tree, x)
        except (ValueError, ZeroDivisionError, OverflowError):
            return math.nan
        return v if isinstance(v, (int, float)) and math.isfinite(v) else math.nan

    return f, p.uses_trig


# --- reading the query -------------------------------------------------------

def split_top(text):
    """Split on commas and semicolons that are not inside brackets."""
    parts, depth, cur = [], 0, ""
    for c in text:
        depth += (c == "(") - (c == ")")
        if c in ",;" and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += c
    return [p.strip() for p in parts + [cur] if p.strip()]


def parse(query):
    """-> ([expressions], low, high) or None when the query is not a request to draw something."""
    q = re.sub(r"\s+", " ", query.strip().lower().replace("²", "^2").replace("³", "^3"))
    m = re.match(r"^(?:plot|graph|draw|chart|sketch)(?: the)?(?: function| curve| graph)? (.+)$", q)
    body = m.group(1) if m else None
    if body is None:
        m = re.match(r"^(?:y|f\(x\)|g\(x\)) ?= ?(.+)$", q)
        body = m.group(0) if m else None
    if not body:
        return None
    span = re.search(r"\s(?:for|with|from|on|in|over)?\s*(?:x ?)?(?:from |in |between )?(-?\d+(?:\.\d+)?) ?(?:to|and|\.\.|-) ?(-?\d+(?:\.\d+)?)\s*$", " " + body)
    low = high = None
    if span:
        a, b = float(span.group(1)), float(span.group(2))
        if a != b:
            low, high = sorted((a, b))
            body = (" " + body)[:span.start()].strip()
    exprs = []
    for part in split_top(body):
        part = re.sub(r"^(?:y|f\(x\)|g\(x\)) ?= ?", "", part).strip()
        if part:
            exprs.append(part)
    if not exprs or len(exprs) > 3:
        return None
    return exprs, low, high


# --- drawing -----------------------------------------------------------------

def nice_step(span, target=6):
    raw = span / target
    mag = 10 ** math.floor(math.log10(raw))
    for m in (1, 2, 2.5, 5, 10):
        if raw <= m * mag:
            return m * mag
    return 10 * mag


def ticks(low, high):
    step = nice_step(high - low)
    first = math.ceil(low / step - 1e-9) * step
    out, v = [], first
    while v <= high + 1e-9 and len(out) < 14:
        out.append(round(v, 10))
        v += step
    return out


def label(v):
    if abs(v) >= 10000 or (v != 0 and abs(v) < 0.001):
        return f"{v:.0e}".replace("e+0", "e").replace("e-0", "e-")
    return f"{v:.6g}"


def answer(query):
    parsed = parse(query)
    if not parsed:
        return None
    exprs, low, high = parsed
    try:
        compiled = [compile_expr(e) for e in exprs]
    except (Bad, RecursionError):
        return None
    if low is None:
        low, high = (-2 * math.pi, 2 * math.pi) if any(t for _, t in compiled) else (-10.0, 10.0)
    if high - low > 1e6:
        return None
    xs = [low + (high - low) * i / (SAMPLES - 1) for i in range(SAMPLES)]
    curves = [[f(x) for x in xs] for f, _ in compiled]
    values = sorted(v for c in curves for v in c if not math.isnan(v))
    if len(values) < 8:
        return None
    lo_v, hi_v = values[int(len(values) * 0.02)], values[int(len(values) * 0.98) - 1]
    if hi_v - lo_v < 1e-9:
        lo_v, hi_v = lo_v - 1, hi_v + 1
    pad = (hi_v - lo_v) * 0.08
    ylo, yhi = lo_v - pad, hi_v + pad
    pw, ph = W - LEFT - RIGHT, H - TOP - BOTTOM
    px = lambda x: LEFT + (x - low) / (high - low) * pw
    py = lambda y: TOP + (yhi - y) / (yhi - ylo) * ph
    series = []
    for expr, ys in zip(exprs, curves):
        d, pen = [], False
        prev = None
        for x, y in zip(xs, ys):
            if math.isnan(y):
                pen = False
                prev = None
                continue
            ypx = py(y)
            if prev is not None and abs(ypx - prev) > ph * 1.5:   # jumped over an asymptote
                pen = False
            ypx = max(-1e4, min(1e4, ypx))
            d.append(f"{'L' if pen else 'M'}{px(x):.1f} {ypx:.1f}")
            pen, prev = True, ypx
        series.append({"label": expr, "d": " ".join(d)})
    return {
        "kind": "plot", "w": W, "h": H, "series": series,
        "box": {"x": LEFT, "y": TOP, "w": pw, "h": ph},
        "xticks": [{"at": round(px(v), 1), "text": label(v)} for v in ticks(low, high)],
        "yticks": [{"at": round(py(v), 1), "text": label(v)} for v in ticks(ylo, yhi)],
        "axis_y": round(px(0), 1) if low <= 0 <= high else None,
        "axis_x": round(py(0), 1) if ylo <= 0 <= yhi else None,
        "note": f"x from {label(round(low, 3))} to {label(round(high, 3))}",
    }
