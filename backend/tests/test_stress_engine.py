"""Unit tests for the stress-testing engine. No database, no HTTP."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.stress_testing.engine import (
    HoldingInput,
    apply_returns,
    apply_shocks,
    resolve_shock,
    window_return,
)
from app.stress_testing.scenarios import (
    HISTORICAL_SCENARIOS,
    SCENARIOS_BY_KEY,
    Shock,
    ShockTargetType,
    ShockType,
)


def shock(target_type: str, target: str | None, value: str) -> Shock:
    return Shock(
        target_type=ShockTargetType(target_type),
        target=target,
        shock_type=ShockType.RELATIVE_PRICE,
        value=Decimal(value),
    )


def holding(symbol: str, sector: str, value: str) -> HoldingInput:
    return HoldingInput(symbol=symbol, sector=sector, market_value=Decimal(value))


TECH = [
    holding("AAPL", "Technology", "10000"),
    holding("MSFT", "Technology", "5000"),
]
MIXED = [*TECH, holding("JNJ", "Healthcare", "5000")]


# --- Shock precedence ---------------------------------------------------------


def test_an_asset_shock_overrides_a_sector_shock():
    shocks = [shock("sector", "Technology", "-0.20"), shock("symbol", "AAPL", "-0.30")]

    chosen = resolve_shock(symbol="AAPL", sector="Technology", shocks=shocks)

    assert chosen is not None
    assert chosen.value == Decimal("-0.30")


def test_a_sector_shock_overrides_a_portfolio_shock():
    shocks = [shock("portfolio", None, "-0.10"), shock("sector", "Technology", "-0.20")]

    chosen = resolve_shock(symbol="AAPL", sector="Technology", shocks=shocks)

    assert chosen is not None
    assert chosen.value == Decimal("-0.20")


def test_precedence_is_independent_of_list_order():
    forward = [shock("symbol", "AAPL", "-0.30"), shock("sector", "Technology", "-0.20")]
    backward = list(reversed(forward))

    assert resolve_shock(symbol="AAPL", sector="Technology", shocks=forward) == resolve_shock(
        symbol="AAPL", sector="Technology", shocks=backward
    )


def test_all_three_levels_resolve_to_the_most_specific():
    shocks = [
        shock("portfolio", None, "-0.05"),
        shock("sector", "Technology", "-0.20"),
        shock("symbol", "AAPL", "-0.40"),
    ]

    assert resolve_shock(symbol="AAPL", sector="Technology", shocks=shocks).value == Decimal(
        "-0.40"
    )
    assert resolve_shock(symbol="MSFT", sector="Technology", shocks=shocks).value == Decimal(
        "-0.20"
    )
    assert resolve_shock(symbol="JNJ", sector="Healthcare", shocks=shocks).value == Decimal("-0.05")


def test_a_later_shock_of_equal_specificity_wins():
    shocks = [shock("symbol", "AAPL", "-0.10"), shock("symbol", "AAPL", "-0.50")]

    assert resolve_shock(symbol="AAPL", sector="Technology", shocks=shocks).value == Decimal(
        "-0.50"
    )


def test_symbol_matching_ignores_case():
    shocks = [shock("symbol", "aapl", "-0.30")]

    assert resolve_shock(symbol="AAPL", sector="Technology", shocks=shocks) is not None


def test_sector_matching_ignores_case():
    shocks = [shock("sector", "technology", "-0.20")]

    assert resolve_shock(symbol="AAPL", sector="Technology", shocks=shocks) is not None


def test_a_shock_for_another_symbol_does_not_apply():
    assert (
        resolve_shock(symbol="AAPL", sector="Technology", shocks=[shock("symbol", "MSFT", "-1")])
        is None
    )


def test_a_shock_for_another_sector_does_not_apply():
    assert (
        resolve_shock(symbol="JNJ", sector="Healthcare", shocks=[shock("sector", "Energy", "-1")])
        is None
    )


def test_a_portfolio_shock_applies_to_every_holding():
    shocks = [shock("portfolio", None, "-0.10")]

    for item in MIXED:
        assert resolve_shock(symbol=item.symbol, sector=item.sector, shocks=shocks) is not None


# --- Applying shocks ----------------------------------------------------------


def test_a_portfolio_shock_reduces_every_position_proportionally():
    result = apply_shocks(MIXED, shocks=[shock("portfolio", None, "-0.10")])

    assert result.starting_value == Decimal("20000.00")
    assert result.ending_value == Decimal("18000.00")
    assert result.total_impact == Decimal("-2000.00")
    assert result.total_impact_percent == Decimal("-0.1")


def test_a_sector_shock_leaves_other_sectors_untouched():
    result = apply_shocks(MIXED, shocks=[shock("sector", "Technology", "-0.20")])

    impacts = {item.symbol: item for item in result.impacts}
    assert impacts["AAPL"].impact == Decimal("-2000.00")
    assert impacts["MSFT"].impact == Decimal("-1000.00")
    assert impacts["JNJ"].impact == Decimal("0.00")
    assert result.total_impact == Decimal("-3000.00")


def test_an_asset_shock_overrides_its_sector_in_the_result():
    result = apply_shocks(
        MIXED,
        shocks=[shock("sector", "Technology", "-0.20"), shock("symbol", "AAPL", "-0.50")],
    )

    impacts = {item.symbol: item for item in result.impacts}
    assert impacts["AAPL"].impact == Decimal("-5000.00")
    assert impacts["MSFT"].impact == Decimal("-1000.00")
    assert result.total_impact == Decimal("-6000.00")


def test_position_impacts_reconcile_with_the_portfolio_total():
    result = apply_shocks(
        MIXED,
        shocks=[
            shock("portfolio", None, "-0.07"),
            shock("sector", "Technology", "-0.23"),
            shock("symbol", "AAPL", "-0.41"),
        ],
    )

    assert result.reconciles()
    assert sum(item.impact for item in result.impacts) == result.total_impact


def test_contribution_to_loss_sums_to_one_for_a_losing_scenario():
    result = apply_shocks(
        MIXED,
        shocks=[shock("sector", "Technology", "-0.20"), shock("symbol", "JNJ", "-0.05")],
    )

    shares = [item.contribution_to_loss for item in result.impacts]
    assert all(share is not None for share in shares)
    assert sum(shares) == pytest.approx(Decimal("1"), abs=Decimal("0.000001"))


def test_a_gaining_holding_offsets_part_of_the_loss():
    """Its contribution is negative, which keeps the breakdown reconciled."""
    result = apply_shocks(
        MIXED,
        shocks=[shock("sector", "Technology", "-0.20"), shock("symbol", "JNJ", "0.10")],
    )

    impacts = {item.symbol: item for item in result.impacts}
    assert impacts["JNJ"].impact > 0
    assert impacts["JNJ"].contribution_to_loss < 0
    assert result.reconciles()


def test_contribution_is_absent_for_a_gaining_scenario():
    result = apply_shocks(MIXED, shocks=[shock("portfolio", None, "0.10")])

    assert result.total_impact > 0
    assert all(item.contribution_to_loss is None for item in result.impacts)


def test_an_untargeted_holding_keeps_its_value_and_says_so():
    result = apply_shocks(MIXED, shocks=[shock("symbol", "AAPL", "-0.50")])

    untouched = next(item for item in result.impacts if item.symbol == "JNJ")
    assert untouched.impact == Decimal("0.00")
    assert untouched.applied_return == Decimal("0")
    assert "no shock" in untouched.source


def test_the_worst_position_is_listed_first():
    result = apply_shocks(
        MIXED,
        shocks=[shock("symbol", "AAPL", "-0.50"), shock("symbol", "MSFT", "-0.10")],
    )

    assert result.impacts[0].symbol == "AAPL"


def test_impacts_are_rounded_to_the_cent():
    result = apply_shocks(
        [holding("AAPL", "Technology", "1000")], shocks=[shock("portfolio", None, "-0.333333")]
    )

    assert result.impacts[0].ending_value == Decimal("666.67")
    assert result.impacts[0].impact == Decimal("-333.33")


def test_a_maximum_severity_shock_does_not_produce_a_negative_value():
    result = apply_shocks(MIXED, shocks=[shock("portfolio", None, "-0.99")])

    assert result.ending_value > 0
    assert all(item.ending_value >= 0 for item in result.impacts)


# --- Applying observed returns -----------------------------------------------


def test_observed_returns_are_applied_per_symbol():
    result = apply_returns(
        MIXED,
        returns={
            "AAPL": Decimal("-0.40"),
            "MSFT": Decimal("-0.30"),
            "JNJ": Decimal("-0.10"),
        },
        sources={},
    )

    impacts = {item.symbol: item for item in result.impacts}
    assert impacts["AAPL"].impact == Decimal("-4000.00")
    assert impacts["MSFT"].impact == Decimal("-1500.00")
    assert impacts["JNJ"].impact == Decimal("-500.00")
    assert result.total_impact == Decimal("-6000.00")


def test_a_holding_without_a_return_is_excluded_not_zeroed():
    result = apply_returns(
        MIXED,
        returns={"AAPL": Decimal("-0.50"), "MSFT": Decimal("-0.50")},
        sources={},
    )

    assert result.excluded_symbols == ["JNJ"]
    assert {item.symbol for item in result.impacts} == {"AAPL", "MSFT"}
    # The excluded holding's value is not part of the starting total either.
    assert result.starting_value == Decimal("15000.00")


def test_excluding_a_holding_keeps_the_percentage_honest():
    """The percentage is of the analyzed value, not of the whole portfolio."""
    result = apply_returns(
        MIXED,
        returns={"AAPL": Decimal("-0.10"), "MSFT": Decimal("-0.10")},
        sources={},
    )

    assert result.total_impact_percent == Decimal("-0.1")


def test_an_empty_portfolio_produces_a_zero_result():
    result = apply_returns([], returns={}, sources={})

    assert result.starting_value == Decimal("0")
    assert result.total_impact == Decimal("0")
    assert result.total_impact_percent == Decimal("0")
    assert result.impacts == []


def test_the_return_source_is_recorded_for_explainability():
    result = apply_returns(
        [holding("AAPL", "Technology", "1000")],
        returns={"AAPL": Decimal("-0.5")},
        sources={"AAPL": "observed return from 2020-02-19 to 2020-03-23"},
    )

    assert "2020-02-19" in result.impacts[0].source


# --- Window returns -----------------------------------------------------------


def test_window_return_is_last_over_first():
    prices = [
        (date(2024, 1, 1), Decimal("100")),
        (date(2024, 1, 2), Decimal("110")),
        (date(2024, 1, 3), Decimal("90")),
    ]

    assert window_return(prices) == Decimal("-0.1")


def test_a_single_observation_gives_no_return():
    assert window_return([(date(2024, 1, 1), Decimal("100"))]) is None


def test_an_empty_window_gives_no_return():
    assert window_return([]) is None


def test_a_non_positive_first_price_gives_no_return():
    prices = [(date(2024, 1, 1), Decimal("0")), (date(2024, 1, 2), Decimal("10"))]

    assert window_return(prices) is None


# --- Catalogue ----------------------------------------------------------------


def test_the_catalogue_is_not_empty():
    assert len(HISTORICAL_SCENARIOS) >= 4


def test_every_scenario_key_is_unique():
    keys = [scenario.key for scenario in HISTORICAL_SCENARIOS]

    assert len(keys) == len(set(keys))
    assert set(keys) == set(SCENARIOS_BY_KEY)


def test_every_scenario_has_an_ordered_date_range():
    for scenario in HISTORICAL_SCENARIOS:
        assert scenario.start < scenario.end, scenario.key


def test_every_scenario_is_described():
    for scenario in HISTORICAL_SCENARIOS:
        assert scenario.name
        assert len(scenario.description) > 40, scenario.key


def test_scenario_windows_fall_inside_the_fixture_data_range():
    """A catalogue entry outside the committed data would silently return nothing."""
    for scenario in HISTORICAL_SCENARIOS:
        assert scenario.start >= date(2007, 1, 1), scenario.key
        assert scenario.end <= date(2024, 12, 31), scenario.key


def test_a_scenario_serializes_its_exact_dates():
    scenario = SCENARIOS_BY_KEY["covid_19_crash_2020"]

    payload = scenario.to_dict()

    assert payload["start"] == "2020-02-19"
    assert payload["end"] == "2020-03-23"
    assert payload["scenario_type"] == "historical"
