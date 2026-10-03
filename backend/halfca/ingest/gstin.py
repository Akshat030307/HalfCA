"""GSTIN structure and checksum.

15 characters: [0:2] state code, [2:12] PAN, [12] entity number, [13] 'Z', [14] checksum.
Checksum: base-36 values, alternate weights 1/2, sum p//36 + p%36, check = (36 - sum%36) % 36.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
_SHAPE = re.compile(r"^\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")

STATES: dict[str, str] = {
    "03": "Punjab",
    "06": "Haryana",
    "07": "Delhi",
    "08": "Rajasthan",
    "09": "Uttar Pradesh",
}


def checksum_char(first14: str) -> str:
    total = 0
    for i, ch in enumerate(first14.upper()):
        product = ALPHABET.index(ch) * (1 if i % 2 == 0 else 2)
        total += product // 36 + product % 36
    return ALPHABET[(36 - total % 36) % 36]


def make_gstin(state_code: str, pan: str, entity: str = "1") -> str:
    body = f"{state_code}{pan.upper()}{entity}Z"
    return body + checksum_char(body)


@dataclass(frozen=True)
class GstinCheck:
    gstin: str
    valid: bool
    reason: str | None
    state_code: str | None = None
    pan: str | None = None


def validate(gstin: str) -> GstinCheck:
    g = (gstin or "").strip().upper()
    if len(g) != 15:
        return GstinCheck(g, False, "must be 15 characters")
    if not _SHAPE.match(g):
        return GstinCheck(g, False, "does not match state · PAN · entity · Z · check")
    if g[:2] not in STATES and not ("01" <= g[:2] <= "38"):
        return GstinCheck(g, False, f"unknown state code {g[:2]}")
    if checksum_char(g[:14]) != g[14]:
        return GstinCheck(g, False, "check digit mismatch", g[:2], g[2:12])
    return GstinCheck(g, True, None, g[:2], g[2:12])


def is_valid(gstin: str) -> bool:
    return validate(gstin).valid
