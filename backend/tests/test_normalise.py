import pytest

from halfca.ingest.normalise import normalise_invoice_no


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("INV-0418", "INV418"),
        ("INV/418", "INV418"),
        ("inv 418", "INV418"),
        ("INV0418", "INV418"),
        ("PP/26/0912", "PP26912"),
        ("PP-26-912", "PP26912"),
        ("AR/S/2219/26-27", "ARS2219"),
        ("AR/S/2219/2026-27", "ARS2219"),
        ("KM/26/33", "KM2633"),  # not a financial year: 26 and 33 are not consecutive
        ("MB/0877", "MB877"),
        ("000", "0"),
    ],
)
def test_normalise(raw: str, expected: str) -> None:
    assert normalise_invoice_no(raw) == expected
