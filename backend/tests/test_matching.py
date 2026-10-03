from __future__ import annotations

import pandas as pd

from halfca.engines.matching import link_ims, link_payments, match, narration_ref

from .conftest import stub_adjudicator
from .factories import SUPPLIER, frame, ims_record, invoice, txn, voucher


def _case() -> tuple[pd.DataFrame, pd.DataFrame]:
    invs = [
        invoice("a", "PP/26/0912", "2026-09-11"),  # 1: exact
        invoice("b", "PP/26/0915", "2026-09-12", taxable=20_000),  # 2: retyped reference
        invoice("c", "PP/26/0920", "2026-09-13", taxable=30_000),  # 2: ledger without GSTIN
        invoice(
            "d",
            "AR/S/2050",
            "2026-09-14",
            direction="outward",
            party="07AABCJ1111A1Z1",
            party_name="Jain Builders",
            taxable=40_000,
        ),  # 3: fuzzy
        invoice(
            "e",
            "AR/S/2051",
            "2026-09-15",
            direction="outward",
            party="07AABCM2222B1Z2",
            party_name="Mittal Infra Projects",
            taxable=50_000,
        ),  # 4: alias
        invoice("f", "PP/26/0999", "2026-09-16", taxable=60_000),  # never booked
    ]
    led = [
        voucher("PUR/1", "2026-09-11", "Patel Pipes", invs[0]["total"], ref="PP/26/0912"),
        voucher("PUR/2", "2026-09-12", "Patel Pipes", invs[1]["total"], ref="pp-26-915"),
        voucher(
            "PUR/3", "2026-09-13", "Patel Pipes", invs[2]["total"], ref="PP/26/0920", gstin=None
        ),
        voucher(
            "SAL/1", "2026-09-14", "Jain Builders.", invs[3]["total"], kind="Sales", gstin=None
        ),
        voucher("SAL/2", "2026-09-15", "M.I.P.", invs[4]["total"], kind="Sales", gstin=None),
    ]
    return frame(invs), frame(led)


def test_each_stage() -> None:
    invs, led = _case()
    m = match(invs, led, stub_adjudicator)
    stage = dict(zip(m.pairs.invoice_id, m.pairs.stage, strict=True))
    assert stage == {"a": 1, "b": 2, "c": 2, "d": 3, "e": 4}
    assert list(m.unmatched.invoice_id) == ["f"]
    assert list(m.funnel.paired) == [1, 2, 1, 1]


def test_stage4_skipped_without_adjudicator() -> None:
    invs, led = _case()
    m = match(invs, led, None)
    assert m.stage4_skipped and set(m.unmatched.invoice_id) == {"e", "f"}


def test_adjudicator_cannot_invent_a_voucher() -> None:
    invs, led = _case()
    m = match(invs, led, lambda inv, cands: ("PUR/999", 1.0, "made up"))
    assert "e" not in set(m.pairs.invoice_id)


def test_exact_duplicates_pair_one_to_one() -> None:
    a = invoice("a", "X/1", "2026-09-01")
    b = dict(a, invoice_id="b")
    led = [
        voucher("PUR/1", "2026-09-01", "Patel Pipes", a["total"], ref="X/1"),
        voucher("PUR/2", "2026-09-01", "Patel Pipes", a["total"], ref="X/1"),
    ]
    m = match(frame([a, b]), frame(led), None)
    assert sorted(m.pairs.voucher_no) == ["PUR/1", "PUR/2"]


def test_payment_links() -> None:
    a = invoice("a", "INV-0418", "2026-09-04")
    b = invoice("b", "INV/418", "2026-09-06")
    c = invoice("c", "PP/77", "2026-09-07", taxable=12_345)
    bank = frame(
        [
            txn("t1", "2026-09-10", a["total"], "Patel Pipes", "INV-0418"),
            txn("t2", "2026-09-11", b["total"], "Patel Pipes", "INV/418"),
            txn("t3", "2026-09-12", c["total"], "Patel Pipes"),  # no reference: amount + name
            txn("t4", "2026-09-13", 50_000, "Patel Pipes", "ADVANCE"),  # orphan
        ]
    )
    links = link_payments(frame([a, b, c]), bank, set())
    assert dict(zip(links.txn_id, links.invoice_id, strict=True)) == {
        "t1": "a",
        "t2": "b",
        "t3": "c",
    }


def test_narration_ref() -> None:
    assert narration_ref("NEFT DR-ABC TRADERS-XYZ-0782") == "XYZ-0782"
    assert narration_ref("CHQ PAID 123456-ABC-AR/S/2001") == "AR/S/2001"
    assert narration_ref("UPI CR-ABC") == ""


def test_ims_links_prefer_originals() -> None:
    a = invoice("a", "X/1", "2026-09-01")
    copy = dict(a, invoice_id="z")
    ims = frame([ims_record("m1", a)])
    links = link_ims(frame([copy, a]), ims, {"z"})
    assert list(links.invoice_id) == ["a"]
    assert list(links.method) == ["exact"]


def test_gstin_conflict_blocks_stage2() -> None:
    a = invoice("a", "Q/5", "2026-09-01")
    v = voucher(
        "PUR/1", "2026-09-01", "Someone Else", a["total"], ref="Q-5", gstin="03AAAAA0000A1Z5"
    )
    assert SUPPLIER != "03AAAAA0000A1Z5"
    m = match(frame([a]), frame([v]), None)
    assert m.pairs.empty
