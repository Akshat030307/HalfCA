"""Read invoice PDFs with a language model, then check every value against the document.

The configured Groq model has no vision, so a PDF's text layer (pypdf) is what the model
reads. Scanned PDFs and images need a vision model and are marked `needs_review`.

The model fills a fixed schema; it is told never to guess. Its answer is then verified in
Python: every amount must be written somewhere in the document text, the invoice number
and e-way bill must appear verbatim, GSTINs must appear and pass the checksum, and the
date must appear in some common format. A value that fails is dropped and noted. Totals
and the GST rate are worked out here, never by the model.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError, field_validator

from halfca import config, fmt
from halfca.ai.llm import LLMClient, LLMError

from .gstin import is_valid

PDF_SUFFIX = ".pdf"
MIN_TEXT_CHARS = 40  # less than this is a scan with no usable text layer

SYSTEM = """You read Indian GST tax invoices. You get the text layer of one invoice PDF.
Return JSON with exactly these keys. Use null for anything the document does not show.
Copy values as written; never guess, convert or calculate.
{"supplier_name": str, "supplier_gstin": str, "buyer_name": str, "buyer_gstin": str,
 "invoice_no": str, "invoice_date": "YYYY-MM-DD", "place_of_supply": "2-digit state code",
 "hsn": str, "description": str, "qty": number, "unit": str, "unit_price": number,
 "taxable_value": number, "cgst_rate": number, "sgst_rate": number, "igst_rate": number,
 "cgst": number, "sgst": number, "igst": number, "total": number,
 "ewb_no": "e-way bill number, digits only", "vehicle_no": str}
Numbers are plain JSON numbers: no ₹, no commas."""


class Extracted(BaseModel):
    """What the model may return. Everything optional: missing beats invented."""

    supplier_name: str | None = None
    supplier_gstin: str | None = None
    buyer_name: str | None = None
    buyer_gstin: str | None = None
    invoice_no: str | None = None
    invoice_date: date | None = None
    place_of_supply: str | None = None
    hsn: str | None = None
    description: str | None = None
    qty: float | None = None
    unit: str | None = None
    unit_price: float | None = None
    taxable_value: float | None = None
    cgst_rate: float | None = None
    sgst_rate: float | None = None
    igst_rate: float | None = None
    cgst: float | None = None
    sgst: float | None = None
    igst: float | None = None
    total: float | None = None
    ewb_no: str | None = None
    vehicle_no: str | None = None

    @field_validator("supplier_gstin", "buyer_gstin", "invoice_no", "hsn", "vehicle_no")
    @classmethod
    def _strip(cls, v: str | None) -> str | None:
        return v.strip().upper() if isinstance(v, str) and v.strip() else None

    @field_validator("ewb_no", mode="before")
    @classmethod
    def _digits(cls, v: Any) -> str | None:
        d = re.sub(r"\D", "", str(v)) if v is not None else ""
        return d or None

    @field_validator("place_of_supply", mode="before")
    @classmethod
    def _state(cls, v: Any) -> str | None:
        d = re.sub(r"\D", "", str(v)) if v is not None else ""
        return d.zfill(2) if d else None


@dataclass
class DocRead:
    """One document after reading and checking."""

    file: str
    status: str  # read | needs_review | unread
    fields: dict[str, Any] = field(default_factory=dict)
    problems: list[str] = field(default_factory=list)
    model: str | None = None
    chars: int = 0

    def as_row(self) -> dict[str, Any]:
        return {
            "file": self.file,
            "status": self.status,
            "invoice_no": self.fields.get("invoice_no"),
            "supplier_gstin": self.fields.get("supplier_gstin"),
            "fields": json.dumps(self.fields, default=str),
            "problems": json.dumps(self.problems),
            "model": self.model,
        }


def pdf_text(path: Path) -> str:
    from pypdf import PdfReader  # small, but only needed here

    reader = PdfReader(path)
    text = "\n".join(page.extract_text() or "" for page in reader.pages[:4])
    return re.sub(r"[ \t]+", " ", text).strip()[: config.EXTRACT_MAX_CHARS]


# ── verification: the model's answer against the document's own text ────────

_DATE_FORMATS = ("%d %b %Y", "%d %B %Y", "%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d.%m.%Y", "%d-%b-%Y")
_AMOUNTS = ("qty", "unit_price", "taxable_value", "cgst", "sgst", "igst", "total")
_RATES = ("cgst_rate", "sgst_rate", "igst_rate")


def _squash(s: str) -> str:
    return re.sub(r"\s+", "", s).upper()


def verify(x: Extracted, text: str) -> tuple[dict[str, Any], list[str]]:
    """Keep only what the document backs up; say what was dropped and why."""
    nums = set(fmt.numbers_in(text))
    flat = _squash(text)
    low = text.lower()
    out: dict[str, Any] = {}
    problems: list[str] = []

    for k in _AMOUNTS + _RATES:
        v = getattr(x, k)
        if v is None:
            continue
        if v == 0 or fmt.norm_number(f"{v:.2f}") in nums:
            out[k] = float(v)
        else:
            problems.append(f"{k} {v:g} is not written on the document")

    for k in ("supplier_gstin", "buyer_gstin"):
        v = getattr(x, k)
        if v is None:
            continue
        if v not in flat:
            problems.append(f"{k} {v} is not on the document")
        elif not is_valid(v):
            problems.append(f"{k} {v} fails the GSTIN check digit")
            out[k] = v  # it is what the document says; the GSTIN engine flags it too
        else:
            out[k] = v

    for k in ("invoice_no", "hsn", "vehicle_no", "ewb_no", "place_of_supply"):
        v = getattr(x, k)
        if v is None:
            continue
        if _squash(str(v)) in flat:
            out[k] = v
        else:
            problems.append(f"{k} {v} is not on the document")

    if x.invoice_date is not None:
        shown = {x.invoice_date.strftime(f).lower() for f in _DATE_FORMATS}
        if any(s in low for s in shown):
            out["invoice_date"] = x.invoice_date.isoformat()
        else:
            problems.append(f"invoice_date {x.invoice_date} is not on the document")

    for k in ("supplier_name", "buyer_name", "description", "unit"):
        v = getattr(x, k)
        if v and _squash(v)[:12] in flat:
            out[k] = v.strip()

    # Worked out here, not by the model.
    rates = [out.get(r) for r in _RATES]
    if out.get("igst_rate"):
        out["rate"] = out["igst_rate"]
    elif out.get("cgst_rate") is not None and out.get("sgst_rate") is not None:
        out["rate"] = out["cgst_rate"] + out["sgst_rate"]
    elif not any(rates) and out.get("taxable_value") and "total" in out:
        tax = sum(out.get(h, 0.0) for h in ("cgst", "sgst", "igst"))
        out["rate"] = round(100 * tax / out["taxable_value"], 1)
    parts = [out.get(k) for k in ("taxable_value", "cgst", "sgst", "igst")]
    if out.get("total") is not None and out.get("taxable_value") is not None:
        computed = sum(p or 0.0 for p in parts)
        if abs(computed - out["total"]) > config.TAX_ARITH_TOL:
            problems.append(
                f"On the document, taxable value plus tax is {fmt.inr(computed)} but the "
                f"total says {fmt.inr(out['total'])}"
            )
    return out, problems


REQUIRED = ("invoice_no", "supplier_gstin", "total")


def read_document(path: Path, client: LLMClient | None, name: str | None = None) -> DocRead:
    shown = name or path.name
    if path.suffix.lower() != PDF_SUFFIX:
        return DocRead(shown, "needs_review", problems=["An image needs a vision model to read"])
    try:
        text = pdf_text(path)
    except Exception as e:  # a broken or encrypted PDF is the user's to fix, not a crash
        return DocRead(shown, "needs_review", problems=[f"Could not open the PDF ({e})"])
    if len(text) < MIN_TEXT_CHARS:
        return DocRead(
            shown, "needs_review", problems=["Scanned PDF without a text layer: needs vision"]
        )
    if client is None:
        return DocRead(shown, "unread", problems=["No AI model configured"], chars=len(text))

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": text},
    ]
    extracted: Extracted | None = None
    error, raw = "", ""
    for attempt in range(2):  # one retry on a schema failure
        try:
            raw = client.chat(
                messages, json_mode=True, max_tokens=900, cache=attempt == 0, max_wait=60
            )
            extracted = Extracted.model_validate(json.loads(raw))
            break
        except (ValueError, ValidationError) as e:
            error = str(e).splitlines()[0][:160]
            messages = messages[:2] + [
                {"role": "assistant", "content": raw},
                {"role": "user", "content": f"That did not fit the schema ({error}). Try again."},
            ]
        except LLMError as e:
            return DocRead(shown, "unread", problems=[f"AI model unavailable ({e})"])
    if extracted is None:
        return DocRead(shown, "needs_review", problems=[f"Unreadable answer ({error})"])

    fields, problems = verify(extracted, text)
    status = "read" if all(k in fields for k in REQUIRED) else "needs_review"
    return DocRead(shown, status, fields, problems, client.model, len(text))
