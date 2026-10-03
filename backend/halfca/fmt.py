"""Text formatting for evidence, reasons and reports (the frontend has lib/format.ts)."""

from __future__ import annotations

import re
from datetime import date, datetime

MINUS = "−"


def _group(n: int) -> str:
    """Indian digit grouping: 2,12,400 and 1,23,45,678."""
    s = str(n)
    if len(s) <= 3:
        return s
    head, tail = s[:-3], s[-3:]
    parts = []
    while len(head) > 2:
        parts.insert(0, head[-2:])
        head = head[:-2]
    if head:
        parts.insert(0, head)
    return ",".join(parts) + "," + tail


def inr(value: float) -> str:
    """₹2,12,400 (whole rupees)."""
    sign = MINUS if value < 0 else ""
    return f"{sign}₹{_group(round(abs(value)))}"


def lakh(value: float, digits: int = 1) -> str:
    """₹4.2 L"""
    sign = MINUS if value < 0 else ""
    return f"{sign}₹{abs(value) / 1e5:.{digits}f} L"


def pct(rate: float) -> str:
    return f"{rate:g}%"


def duration(minutes: float) -> str:
    """3h 02m"""
    total = round(minutes)
    h, m = divmod(total, 60)
    return f"{h}h {m:02d}m" if h else f"{m}m"


def day(d: date | datetime) -> str:
    """04 Sep"""
    return d.strftime("%d %b")


def day_long(d: date | datetime) -> str:
    """12 Sep 2026"""
    return d.strftime("%d %b %Y")


def stamp(d: datetime) -> str:
    """19 Sep, 23:01"""
    return d.strftime("%d %b, %H:%M")


def ewb(no: str) -> str:
    """3812 4471 0093"""
    s = str(no)
    return " ".join(s[i : i + 4] for i in range(0, len(s), 4))


_NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")


def norm_number(tok: str) -> str:
    """'1,18,000.00' → '118000', '0.820' → '0.82': one spelling per value."""
    t = tok.strip(",").replace(",", "")
    whole, _, frac = t.partition(".")
    whole = whole.lstrip("0") or "0"
    frac = frac.rstrip("0")
    return f"{whole}.{frac}" if frac else whole


def numbers_in(text: str) -> list[str]:
    """Every number written in `text`, normalised (Indian or western grouping alike)."""
    return [norm_number(t) for t in _NUM.findall(text)]
