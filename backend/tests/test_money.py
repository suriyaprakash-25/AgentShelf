import pytest

from app.errors import DomainError
from app.paypal import money, parse_money


@pytest.mark.parametrize(
    "minor,expected", [(0, "0.00"), (1, "0.01"), (4500, "45.00"), (123456789, "1234567.89")]
)
def test_roundtrip(minor, expected):
    assert money(minor) == expected
    assert parse_money(expected) == minor


@pytest.mark.parametrize("value", [-1, 0.01, True, "45"])
def test_money_refuses_nonintegers(value):
    with pytest.raises(ValueError):
        money(value)


@pytest.mark.parametrize(
    "value",
    ["NaN", "Infinity", "-1.00", "1.001", "1e10000", "1" * 10000, None],
    ids=["nan", "infinity", "negative", "fractional-cent", "exponent", "oversize", "null"],
)
def test_provider_amount_is_exact(value):
    with pytest.raises(DomainError):
        parse_money(value)
