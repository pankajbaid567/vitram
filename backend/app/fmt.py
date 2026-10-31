"""Indian digit grouping for user-facing text (₹12,34,567)."""

import re


def group(x: float | None) -> str:
    if x is None:
        return "not available"
    neg = x < 0
    s = str(int(round(abs(x))))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        s = re.sub(r"(\d)(?=(\d{2})+$)", r"\1,", head) + "," + tail
    return ("−" if neg else "") + s


def inr(x: float | None, paise: bool = False) -> str:
    """₹12,34,567 — or ₹808.81 with `paise=True` when the amount has paise (receipts, bills)."""
    if x is None:
        return "not available"
    if paise and round(abs(x) * 100) % 100:
        whole = int(abs(x))
        frac = round((abs(x) - whole) * 100)
        if frac == 100:
            whole, frac = whole + 1, 0
        g = group(whole) + f".{frac:02d}"
        return ("−₹" if x < 0 else "₹") + g
    g = group(x)
    return ("−₹" + g[1:]) if g.startswith("−") else "₹" + g
