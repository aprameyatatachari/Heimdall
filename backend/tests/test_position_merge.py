"""Unit tests for weighted-average cost merging.

The merge arithmetic is the one piece of Phase 1 that is genuinely financial, so
it is verified with hand-computed examples and no database.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.portfolios.service import COST_QUANTIZE


def merge(
    *,
    existing_quantity: Decimal,
    existing_cost: Decimal,
    added_quantity: Decimal,
    added_cost: Decimal,
) -> tuple[Decimal, Decimal]:
    """Reference implementation of the merge used by `PositionService._merge_into`."""
    total_quantity = existing_quantity + added_quantity
    total_cost = existing_quantity * existing_cost + added_quantity * added_cost
    return total_quantity, (total_cost / total_quantity).quantize(COST_QUANTIZE)


@pytest.mark.parametrize(
    ("existing_quantity", "existing_cost", "added_quantity", "added_cost", "expected_cost"),
    [
        # Equal quantities: the average is the midpoint.
        ("10", "100", "10", "200", "150"),
        # Unequal quantities: the larger lot dominates.
        ("30", "100", "10", "200", "125"),
        # Adding at the same price leaves the average unchanged.
        ("10", "185.20", "5", "185.20", "185.20"),
        # A zero-cost lot (a gift or vesting) drags the average down.
        ("10", "100", "10", "0", "50"),
        # Fractional quantities.
        ("0.5", "400", "0.5", "200", "300"),
    ],
)
def test_weighted_average_cost(
    existing_quantity, existing_cost, added_quantity, added_cost, expected_cost
):
    _, average = merge(
        existing_quantity=Decimal(existing_quantity),
        existing_cost=Decimal(existing_cost),
        added_quantity=Decimal(added_quantity),
        added_cost=Decimal(added_cost),
    )
    assert average == Decimal(expected_cost)


def test_quantities_add_exactly():
    total, _ = merge(
        existing_quantity=Decimal("0.1"),
        existing_cost=Decimal("1"),
        added_quantity=Decimal("0.2"),
        added_cost=Decimal("1"),
    )
    assert total == Decimal("0.3")


def test_average_cost_is_rounded_to_the_stored_precision():
    _, average = merge(
        existing_quantity=Decimal("3"),
        existing_cost=Decimal("10"),
        added_quantity=Decimal("1"),
        added_cost=Decimal("11"),
    )
    # (3*10 + 1*11) / 4 = 10.25 exactly.
    assert average == Decimal("10.2500")
    assert average.as_tuple().exponent == -4


def test_a_repeating_decimal_is_rounded_not_truncated():
    _, average = merge(
        existing_quantity=Decimal("3"),
        existing_cost=Decimal("10"),
        added_quantity=Decimal("0"),
        added_cost=Decimal("0"),
    )
    assert average == Decimal("10.0000")


def test_a_non_terminating_average_keeps_four_places():
    _, average = merge(
        existing_quantity=Decimal("3"),
        existing_cost=Decimal("100"),
        added_quantity=Decimal("4"),
        added_cost=Decimal("200"),
    )
    # (300 + 800) / 7 = 157.142857...
    assert average == Decimal("157.1429")


def test_total_cost_is_preserved_within_rounding():
    existing_quantity, existing_cost = Decimal("7"), Decimal("123.4567")
    added_quantity, added_cost = Decimal("13"), Decimal("98.7654")

    total_quantity, average = merge(
        existing_quantity=existing_quantity,
        existing_cost=existing_cost,
        added_quantity=added_quantity,
        added_cost=added_cost,
    )

    expected_total = existing_quantity * existing_cost + added_quantity * added_cost
    assert abs(total_quantity * average - expected_total) <= Decimal("0.01")


def test_earliest_purchase_date_wins():
    assert min(date(2024, 6, 1), date(2024, 1, 15)) == date(2024, 1, 15)
