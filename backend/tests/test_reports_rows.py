"""Unit tests for how stored metrics become report rows.

These exist because of a bug that no test caught: every monetary figure in the
PDF was printed as a percentage. The row builder compared a metric's unit with
`is`, which is true for the enum member a service writes and false for the plain
string the database hands back, so in a real report every currency and count row
fell through to the percentage branch. The rows below are built the way they
arrive from the database — with string units — which is the case that matters.
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

from app.reports.service import (
    PERFORMANCE_METRICS,
    RISK_METRICS,
    SUMMARY_METRICS,
    _metric_rows,
    _signal_metric,
)


def _stored(metric: str, value: str | None, unit: str, **metadata: object) -> SimpleNamespace:
    """A risk result as SQLAlchemy returns it: the unit is a `str`, not an enum."""
    return SimpleNamespace(
        metric=metric,
        value=None if value is None else Decimal(value),
        unit=unit,
        result_metadata=dict(metadata),
        unavailable_reason=None if value is not None else "Not enough observations.",
    )


def _rows(wanted, *results: SimpleNamespace) -> dict[str, object]:
    built = _metric_rows(wanted, {item.metric: item for item in results}, "INR")  # type: ignore[arg-type]
    return {row.label: row for row in built}


def test_money_is_printed_as_money_when_the_unit_comes_from_the_database():
    rows = _rows(SUMMARY_METRICS, _stored("portfolio_value", "178760.0049", "currency"))

    row = rows["Portfolio market value"]
    assert row.value == "178,760.00 INR"
    assert row.unit == "INR"
    # The regression itself: this used to read "17,876,000.49%".
    assert "%" not in row.value


def test_a_count_is_printed_as_a_count():
    rows = _rows(SUMMARY_METRICS, _stored("holdings_count", "3", "count"))

    assert rows["Holdings"].value == "3"
    assert rows["Holdings"].unit == "count"


def test_value_at_risk_is_an_amount_of_money_not_a_percentage():
    rows = _rows(
        RISK_METRICS,
        _stored("value_at_risk_historical", "3032.9855", "currency", confidence=0.95),
    )

    row = rows["Value at Risk (historical)"]
    assert row.value == "3,032.99 INR"
    assert "95% confidence" in row.note


def test_a_fraction_is_printed_as_a_percentage():
    rows = _rows(RISK_METRICS, _stored("volatility_annualized", "0.1558", "ratio"))

    assert rows["Volatility (annualized)"].value == "15.58%"


def test_a_plain_ratio_is_not_turned_into_a_percentage():
    rows = _rows(
        RISK_METRICS,
        _stored("sharpe_ratio", "-0.43", "ratio"),
        _stored("sortino_ratio", "0.61", "ratio"),
        _stored("skewness", "-0.37", "ratio"),
    )

    # A Sharpe ratio of -0.43 is not -43%.
    assert rows["Sharpe ratio (annualized)"].value == "-0.43"
    assert rows["Sortino ratio (annualized)"].value == "0.61"
    assert rows["Skewness of returns"].value == "-0.37"


def test_beta_and_capture_are_plain_ratios():
    rows = _rows(
        PERFORMANCE_METRICS,
        _stored("benchmark_beta", "1.04", "ratio"),
        _stored("upside_capture", "1.12", "ratio"),
    )

    assert rows["Beta to benchmark"].value == "1.04"
    assert rows["Upside capture"].value == "1.12"


def test_a_return_carries_its_sign():
    rows = _rows(PERFORMANCE_METRICS, _stored("total_return", "0.0812", "ratio"))

    assert rows["Total return"].value == "+8.12%"


def test_an_unavailable_metric_says_why_instead_of_printing_a_zero():
    rows = _rows(RISK_METRICS, _stored("sortino_ratio", None, "ratio"))

    row = rows["Sortino ratio (annualized)"]
    assert row.value == "unavailable"
    assert row.note == "Not enough observations."


def test_a_metric_the_run_never_produced_is_left_out():
    rows = _rows(PERFORMANCE_METRICS, _stored("total_return", "0.05", "ratio"))

    # No benchmark in this run, so no benchmark rows — not a row of dashes.
    assert "Beta to benchmark" not in rows


def _signal(observed: str, threshold: str, unit: str) -> SimpleNamespace:
    return SimpleNamespace(
        observed_value=Decimal(observed), threshold_value=Decimal(threshold), unit=unit
    )


def test_a_signal_reads_as_a_sentence_not_as_raw_fractions():
    text = _signal_metric(_signal("0.2804", "0.2000", "percent_decline_from_peak"))  # type: ignore[arg-type]

    # Once "0.2804 vs 0.2000 (percent_decline_from_peak)".
    assert text == "28.04% against a threshold of 20.00% below peak"


def test_a_count_based_signal_is_printed_as_whole_numbers():
    text = _signal_metric(_signal("1.0000", "1.0000", "expected_trading_days"))  # type: ignore[arg-type]

    assert text == "1 against a threshold of 1 trading days"


def test_a_ratio_based_signal_is_not_made_a_percentage():
    text = _signal_metric(_signal("1.52", "1.25", "ratio_to_baseline"))  # type: ignore[arg-type]

    assert text == "1.52 against a threshold of 1.25 times baseline"
