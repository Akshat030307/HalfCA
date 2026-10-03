from __future__ import annotations

from datetime import date

from halfca.engines.dupes_gaps import field_diffs, find_duplicates, gaps
from halfca.engines.matching import link_ims, link_payments, match

from .factories import frame, ims_record, invoice, txn, voucher


def test_exact_and_near_duplicates() -> None:
    orig = invoice("a", "INV-0418", "2026-09-04", taxable=94_915.25)
    near = invoice("b", "INV/418", "2026-09-06", taxable=94_915.25)
    exact = dict(invoice("c", "PP/1145", "2026-09-10", taxable=7_000))
    copy = dict(exact, invoice_id="d")
    sequential = invoice("e", "PP/1146", "2026-09-11", taxable=7_100)  # different amount
    far = invoice("f", "PP/1145", "2026-09-29", taxable=7_000)  # same as c but 19 days later
    flags, dup_of = find_duplicates(frame([orig, near, exact, copy, sequential, far]))
    assert dup_of["b"] == "a" and dup_of["d"] == "c"
    kinds = {f.invoice_id: f.kind for f in flags}
    assert kinds["b"] == "near_duplicate" and kinds["d"] == "duplicate"
    assert "e" not in dup_of
    # Same number and amount weeks apart is still the same bill keyed twice.
    assert dup_of.get("f") == "c"


def test_field_diffs() -> None:
    amt = invoice("a", "A/1", "2026-09-01")
    late = invoice("b", "A/2", "2026-09-02")
    retyped = invoice("c", "A/0003", "2026-09-03")
    short = invoice("d", "A/4", "2026-09-04")
    invs = frame([amt, late, retyped, short])
    led = frame(
        [
            voucher("P1", "2026-09-01", "Patel Pipes", amt["total"] - 900, ref="A/1"),
            voucher("P2", "2026-09-12", "Patel Pipes", late["total"], ref="A/2"),
            voucher("P3", "2026-09-03", "Patel Pipes", retyped["total"], ref="a-3"),
            voucher("P4", "2026-09-04", "Patel Pipes", short["total"], ref="A/4"),
        ]
    )
    bank = frame([txn("t1", "2026-09-10", short["total"] - 1_180, "Patel Pipes", "A/4")])
    m = match(invs, led, None)
    pays = link_payments(invs, bank, set())
    flags = field_diffs(invs, led, m.pairs, pays, bank, {})
    got = sorted((f.invoice_id, f.kind) for f in flags)
    assert got == [("a", "amount"), ("b", "date"), ("c", "invoice_id"), ("d", "amount")]
    short_flag = next(f for f in flags if f.invoice_id == "d")
    assert short_flag.title == "Short payment" and short_flag.impact == 1_180


def test_gaps() -> None:
    old = invoice("a", "G/1", "2026-08-20")  # unpaid, aged
    booked_not_filed = invoice("b", "G/2", "2026-09-20")
    filed = invoice("c", "G/3", "2026-09-21")
    invs = frame([old, booked_not_filed, filed])
    led = frame(
        [
            voucher(
                f"P{i}",
                r["invoice_date"].date().isoformat(),
                "Patel Pipes",
                r["total"],
                ref=r["invoice_no"],
            )
            for i, r in enumerate([old, booked_not_filed, filed])
        ]
    )
    stray = invoice("x", "G/9", "2026-09-22")
    ims = frame([ims_record("m1", filed), ims_record("m2", stray)])  # m2 is not in the books
    bank = frame([txn("t1", "2026-09-25", 77_777, "Unknown Co", "ADVANCE")])
    m = match(invs, led, None)
    pays = link_payments(invs, bank, set())
    links = link_ims(invs, ims, set())
    kinds = sorted(
        (f.kind, f.ref) for f in gaps(invs, bank, ims, m.pairs, pays, links, {}, date(2026, 10, 10))
    )
    assert ("unpaid_aged", "G/1") in kinds
    assert ("not_in_ims", "G/1") in kinds and ("not_in_ims", "G/2") in kinds
    assert ("payment_only", "t1") in kinds
    assert ("ims_only", "m2") in kinds
    assert ("not_in_ims", "G/3") not in kinds
