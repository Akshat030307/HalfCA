"""Invoice-number normalisation used by stage 2 of the matching cascade.

Uppercase; drop FY suffixes like /26-27; split on separators (- / _ . space) and on
letter/digit boundaries; strip leading zeros from numeric runs; join.
So INV-0418, INV/418, inv 418 and INV0418/26-27 all become INV418.
"""

from __future__ import annotations

import re

from rapidfuzz import fuzz, utils

_FY_SUFFIX = re.compile(r"[-/_. ]?(?:20)?(\d{2})[-/](?:20)?(\d{2})$")
_RUNS = re.compile(r"[A-Z]+|\d+")


def _strip_fy(s: str) -> str:
    m = _FY_SUFFIX.search(s)
    # Only a real financial year (consecutive years) counts, so KM/26/33 survives.
    if m and int(m.group(2)) == (int(m.group(1)) + 1) % 100 and m.start() > 0:
        return s[: m.start()]
    return s


def normalise_invoice_no(raw: str) -> str:
    s = _strip_fy((raw or "").strip().upper())
    out: list[str] = []
    for run in _RUNS.findall(s):
        out.append((run.lstrip("0") or "0") if run.isdigit() else run)
    return "".join(out)


def name_similarity(a: str, b: str) -> float:
    """Counterparty name similarity, 0-100 (stage 3 uses >= STAGE3_NAME_MIN).

    token_sort_ratio after lowercasing and stripping punctuation, so word order and
    "&" vs "and" style noise matter less than the words themselves.
    """
    return float(fuzz.token_sort_ratio(a or "", b or "", processor=utils.default_process))
