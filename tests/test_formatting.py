from datetime import datetime
from decimal import Decimal

import pytest

from db import Unit
from formatting import (
    fmt_datetime_br,
    fmt_money,
    fmt_quantity,
    month_label,
    parse_datetime_br,
    parse_decimal,
    parse_money,
    parse_month_choice,
    parse_quantity,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("10,50", Decimal("10.50")),
        ("  10.50  ", Decimal("10.50")),
        ("0,0001", Decimal("0.0001")),
    ],
)
def test_parse_decimal_valid(raw, expected):
    assert parse_decimal(raw) == expected


@pytest.mark.parametrize("raw", ["", "0", "-5", "abc", "NaN", "Infinity"])
def test_parse_decimal_invalid(raw):
    with pytest.raises(ValueError):
        parse_decimal(raw)


def test_parse_money_half_up_rounding():
    assert parse_money("10,555") == Decimal("10.56")
    assert parse_money("10.554") == Decimal("10.55")


def test_parse_quantity_unit_enforces_integers():
    assert parse_quantity("3,00", Unit.UNIT) == Decimal(3)
    with pytest.raises(ValueError):
        parse_quantity("3,5", Unit.UNIT)


def test_parse_quantity_kg_quantizes_four_decimals():
    assert parse_quantity("1,23456", Unit.KG) == Decimal("1.2346")


def test_parse_datetime_br_valid_empty_and_invalid():
    assert parse_datetime_br("15/11/2026 09:30") == datetime(2026, 11, 15, 9, 30)

    now_parsed = parse_datetime_br("   ")
    assert now_parsed.second == 0 and now_parsed.microsecond == 0

    with pytest.raises(ValueError):
        parse_datetime_br("31/02/2026 10:00")


def test_formatting_and_month_roundtrip():
    assert fmt_money(Decimal("12.5")) == "12.50"
    assert fmt_quantity(Decimal("4.0"), Unit.UNIT) == "4"
    assert fmt_quantity(Decimal("1.2"), Unit.KG) == "1.200"
    assert fmt_datetime_br(datetime(2026, 3, 5, 8, 7)) == "05/03/2026 08:07"

    for m in range(1, 13):
        assert parse_month_choice(month_label(m)) == m
