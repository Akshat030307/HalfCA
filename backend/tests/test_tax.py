from __future__ import annotations

from halfca.engines.tax import verify

from .factories import DELHI_SUPPLIER, frame, hsn_rates, invoice


def _kinds(rows: list[dict]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for f in verify(frame(rows), hsn_rates()).flags:
        out.setdefault(f.invoice_id, []).append(f.kind)
    return out


def test_correct_invoice_is_clean() -> None:
    assert _kinds([invoice("ok", "A/1", "2026-09-12", hsn="7307", rate=18)]) == {}


def test_abolished_slab() -> None:
    rows = [invoice("df", "DF/0450", "2026-09-12", hsn="7307", rate=12, taxable=58_500)]
    (f,) = verify(frame(rows), hsn_rates()).flags
    assert f.kind == "tax_rate" and f.title == "Abolished slab still charged"
    assert (f.recorded, f.expected) == ("12% · ₹7,020", "18% · ₹10,530")
    assert any("abolished by GST 2.0" in n for n in f.evidence["notes"])


def test_rate_checked_against_date_of_supply() -> None:
    before = invoice("old", "C/1", "2025-08-01", hsn="2523", rate=28)  # cement, pre GST 2.0
    after = invoice("new", "C/2", "2026-09-01", hsn="2523", rate=28)
    kinds = _kinds([before, after])
    assert "old" not in kinds and kinds["new"] == ["tax_rate"]


def test_wrong_heads() -> None:
    igst_intra = invoice("h1", "H/1", "2026-09-05", party=DELHI_SUPPLIER, head="igst")
    split_inter = invoice("h2", "H/2", "2026-09-05", head="cgst_sgst")
    kinds = _kinds([igst_intra, split_inter])
    assert kinds == {"h1": ["tax_head"], "h2": ["tax_head"]}


def test_arithmetic_and_transition() -> None:
    bad_maths = invoice("m", "M/1", "2026-09-05", tax=1_999.0)  # 18% of 10,000 is 1,800
    near_switch = invoice("t", "T/1", "2025-09-30", hsn="7307", rate=18)
    kinds = _kinds([bad_maths, near_switch])
    assert kinds["m"] == ["tax_arith"]
    assert kinds["t"] == ["transition_review"]
