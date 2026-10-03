import pytest

from halfca.ingest.gstin import checksum_char, is_valid, make_gstin, validate


@pytest.mark.parametrize("gstin", ["07AAKFA4821M1ZA", "06AAHCK3367Q1ZW"])
def test_demo_gstins_validate(gstin: str) -> None:
    assert is_valid(gstin)


def test_corrupted_gstin_is_rejected() -> None:
    check = validate("07AAKFA4821M1ZB")
    assert not check.valid
    assert check.reason == "check digit mismatch"


@pytest.mark.parametrize("bad", ["", "07AAKFA4821M1Z", "07AAKFA4821M1XA", "7AAKFA4821M1ZAA"])
def test_malformed_gstins_are_rejected(bad: str) -> None:
    assert not is_valid(bad)


def test_make_gstin_round_trips() -> None:
    g = make_gstin("03", "AABCS1234K")
    assert g[:14] == "03AABCS1234K1Z"
    assert g[14] == checksum_char(g[:14])
    assert is_valid(g)
