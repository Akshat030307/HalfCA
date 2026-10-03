"""Pydantic API models. Mirrored by hand in frontend/lib/api.ts; keep the two in step."""

from __future__ import annotations

from pydantic import BaseModel


class SourceFile(BaseModel):
    kind: str  # invoices | bank | ledger | ims | eway
    filename: str
    records: int


class DatasetInfo(BaseModel):
    scenario: str
    seed: int
    period: str
    as_of: str
    user_gstin: str
    user_name: str
    sources: list[SourceFile]
    counts: dict[str, int]  # every raw table
