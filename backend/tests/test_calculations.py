"""Unit tests for the financial calculations.

Two kinds of check:

* **Hand-computed examples.** Small series where the arithmetic is written out in
  the test, so a reader can verify the expected value without running anything.
* **Invariants.** Properties that must hold for any input, such as risk
  contributions reconciling with total volatility.

No database, no HTTP, no clock.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from app.analytics import calculations as calc

TOLERANCE = 1e-12


# --- Simple returns -----------------------------------------------------------


def test_simple_returns_from_hand_computed_prices():
    # 100 -> 110 is +10%; 110 -> 99 is -10%; 99 -> 108.9 is +10%.
    returns = calc.simple_returns([100.0, 110.0, 99.0, 108.9])

    assert returns == pytest.approx([0.10, -0.10, 0.10], abs=1e-12)


def test_a_single_price_cannot_produce_a_return():
    with pytest.raises(calc.InsufficientDataError) as exc:
        calc.simple_returns([100.0])
    assert exc.value.required == 2
    assert exc.value.available == 1


@pytest.mark.parametrize("prices", [[100.0, 0.0], [100.0, -5.0], [0.0, 100.0]])
def test_non_positive_prices_are_rejected(prices):
    with pytest.raises(calc.DegenerateDataError):
        calc.simple_returns(prices)


def test_a_non_finite_price_is_rejected():
    with pytest.raises(calc.DegenerateDataError):
        calc.simple_returns([100.0, float("nan")])


def test_a_flat_series_has_zero_returns():
    assert calc.simple_returns([100.0, 100.0, 100.0]) == pytest.approx([0.0, 0.0])


# --- Portfolio returns --------------------------------------------------------


def test_portfolio_returns_are_the_weighted_sum():
    # 60% of +10% plus 40% of -5% = 0.06 - 0.02 = 0.04
    matrix = [[0.10, -0.05], [0.00, 0.10]]

    result = calc.portfolio_returns([0.6, 0.4], matrix)

    assert result == pytest.approx([0.04, 0.04], abs=1e-12)


def test_a_zero_weight_asset_contributes_nothing():
    matrix = [[0.10, 0.99], [0.20, -0.99]]

    result = calc.portfolio_returns([1.0, 0.0], matrix)

    assert result == pytest.approx([0.10, 0.20])


def test_mismatched_weights_and_assets_are_rejected():
    with pytest.raises(calc.DegenerateDataError, match="weights"):
        calc.portfolio_returns([0.5], [[0.1, 0.2]])


def test_a_one_dimensional_matrix_is_rejected():
    with pytest.raises(calc.DegenerateDataError, match="two-dimensional"):
        calc.portfolio_returns([1.0], [0.1, 0.2])


# --- Weights ------------------------------------------------------------------


def test_weights_sum_to_one():
    weights = calc.normalize_weights([2500.0, 1500.0, 1000.0])

    assert weights == pytest.approx([0.5, 0.3, 0.2])
    assert float(weights.sum()) == pytest.approx(1.0, abs=TOLERANCE)


def test_an_empty_portfolio_has_no_weights():
    with pytest.raises(calc.DegenerateDataError, match="empty"):
        calc.normalize_weights([])


def test_a_zero_value_portfolio_has_no_weights():
    with pytest.raises(calc.DegenerateDataError, match="no value"):
        calc.normalize_weights([0.0, 0.0])


# --- Compounding --------------------------------------------------------------


def test_cumulative_return_compounds():
    # 1.10 * 0.90 = 0.99, so the total return is -1%.
    assert calc.cumulative_return([0.10, -0.10]) == pytest.approx(-0.01, abs=1e-12)


def test_a_total_loss_makes_compounding_undefined():
    with pytest.raises(calc.DegenerateDataError, match="-100%"):
        calc.cumulative_return([-1.0])


def test_annualized_return_matches_the_documented_formula():
    # 252 daily returns of exactly 0.1% compound to 1.001**252 - 1.
    returns = [0.001] * 252
    expected = 1.001**252 - 1

    assert calc.annualized_return(returns) == pytest.approx(expected, rel=1e-12)


def test_annualizing_a_half_year_scales_the_exponent():
    # 126 periods is half a trading year, so the total return is squared.
    returns = [0.001] * 126
    total = 1.001**126 - 1
    expected = (1 + total) ** 2 - 1

    assert calc.annualized_return(returns) == pytest.approx(expected, rel=1e-12)


def test_value_history_starts_at_the_starting_value():
    path = calc.value_history([0.10, -0.10], starting_value=1000.0)

    assert path == pytest.approx([1000.0, 1100.0, 990.0])


def test_value_history_requires_a_positive_start():
    with pytest.raises(calc.DegenerateDataError):
        calc.value_history([0.01], starting_value=0.0)


# --- Volatility and Sharpe ----------------------------------------------------


def test_volatility_is_the_sample_standard_deviation():
    returns = [0.01, -0.01] * 15  # 30 observations, mean zero
    # Sample stdev of an alternating series about zero is sqrt(sum/(n-1)).
    expected_daily = math.sqrt(30 * 0.0001 / 29)

    assert calc.volatility(returns, annualize=False) == pytest.approx(expected_daily, rel=1e-12)


def test_volatility_annualizes_by_the_square_root_of_periods():
    returns = [0.01, -0.01] * 15
    daily = calc.volatility(returns, annualize=False)

    assert calc.volatility(returns) == pytest.approx(daily * math.sqrt(252), rel=1e-12)


def test_annualization_uses_the_configured_period_count():
    returns = [0.01, -0.01] * 15
    daily = calc.volatility(returns, annualize=False)

    assert calc.volatility(returns, periods_per_year=52) == pytest.approx(
        daily * math.sqrt(52), rel=1e-12
    )


def test_a_constant_series_has_zero_volatility():
    assert calc.volatility([0.01] * 30, annualize=False) == pytest.approx(0.0)


def test_volatility_needs_enough_observations():
    with pytest.raises(calc.InsufficientDataError):
        calc.volatility([0.01, 0.02])


def test_a_rate_is_deannualized_geometrically_not_by_division():
    periodic = calc.deannualize_rate(0.05, periods_per_year=252)

    assert (1 + periodic) ** 252 == pytest.approx(1.05, rel=1e-12)
    # Dividing would give 0.0001984; the geometric rate is slightly smaller.
    assert periodic < 0.05 / 252


def test_deannualizing_zero_gives_zero():
    assert calc.deannualize_rate(0.0, periods_per_year=252) == 0.0


def test_sharpe_ratio_with_no_risk_free_rate():
    returns = [0.01, -0.01] * 15  # mean exactly zero
    assert calc.sharpe_ratio(returns) == pytest.approx(0.0, abs=1e-12)


def test_a_positive_mean_gives_a_positive_sharpe_ratio():
    returns = [0.02, 0.00] * 15  # mean 0.01

    assert calc.sharpe_ratio(returns) > 0


def test_the_risk_free_rate_reduces_the_sharpe_ratio():
    returns = [0.002, 0.000] * 15

    assert calc.sharpe_ratio(returns, annual_risk_free_rate=0.05) < calc.sharpe_ratio(returns)


def test_a_sharpe_ratio_without_variability_is_undefined():
    with pytest.raises(calc.DegenerateDataError, match="undefined"):
        calc.sharpe_ratio([0.001] * 30)


# --- Drawdown -----------------------------------------------------------------


def test_drawdown_is_measured_from_the_running_peak():
    # Peak 120, trough 90: 90/120 - 1 = -25%.
    series = calc.drawdown_series([100.0, 120.0, 90.0, 110.0])

    assert series == pytest.approx([0.0, 0.0, -0.25, -1 / 12], abs=1e-12)


def test_drawdown_is_never_positive():
    rng = np.random.default_rng(7)
    path = 100 * np.cumprod(1 + rng.normal(0.001, 0.02, 500))

    assert np.all(calc.drawdown_series(path) <= 1e-15)


def test_a_monotonically_rising_series_has_no_drawdown():
    assert calc.drawdown_series([100.0, 101.0, 102.0]) == pytest.approx([0.0, 0.0, 0.0])


def test_max_drawdown_reports_its_peak_and_trough():
    worst = calc.max_drawdown([100.0, 120.0, 90.0, 110.0])

    assert worst.drawdown == pytest.approx(-0.25)
    assert worst.peak_index == 1
    assert worst.trough_index == 2
    assert worst.peak_value == 120.0
    assert worst.trough_value == 90.0


def test_max_drawdown_of_a_rising_series_is_zero():
    assert calc.max_drawdown([100.0, 110.0, 120.0]).drawdown == pytest.approx(0.0)


def test_drawdown_requires_positive_values():
    with pytest.raises(calc.DegenerateDataError):
        calc.drawdown_series([100.0, 0.0])


# --- Value at Risk and Expected Shortfall ------------------------------------


def _loss_series() -> list[float]:
    """40 returns: 4 large losses and 36 small gains. Quantiles are easy to read."""
    return [-0.10, -0.08, -0.06, -0.04] + [0.01] * 36


def test_historical_var_is_a_positive_loss_amount():
    result = calc.historical_var(
        _loss_series(),
        confidence=0.95,
        portfolio_value=100_000.0,
    )

    assert result > 0


def test_historical_var_matches_the_numpy_quantile_definition():
    returns = _loss_series()
    expected = -float(np.quantile(returns, 0.05)) * 100_000.0

    result = calc.historical_var(returns, confidence=0.95, portfolio_value=100_000.0)

    assert result == pytest.approx(expected, rel=1e-12)


def test_var_scales_linearly_with_portfolio_value():
    returns = _loss_series()

    small = calc.historical_var(returns, confidence=0.95, portfolio_value=1_000.0)
    large = calc.historical_var(returns, confidence=0.95, portfolio_value=10_000.0)

    assert large == pytest.approx(small * 10, rel=1e-12)


def test_higher_confidence_never_reduces_var():
    returns = _loss_series()

    assert calc.historical_var(
        returns, confidence=0.99, portfolio_value=1_000.0
    ) >= calc.historical_var(returns, confidence=0.95, portfolio_value=1_000.0)


def test_var_is_floored_at_zero_for_an_all_positive_series():
    """A profitable tail would otherwise produce a negative 'loss'."""
    result = calc.historical_var(
        [0.01] * 40,
        confidence=0.95,
        portfolio_value=1_000.0,
    )

    assert result == 0.0


def test_parametric_var_uses_the_normal_quantile():
    returns = [0.01, -0.01] * 20
    mean = 0.0
    deviation = float(np.std(returns, ddof=1))
    from scipy import stats

    expected = -(mean + float(stats.norm.ppf(0.05)) * deviation) * 100_000.0

    result = calc.parametric_var(returns, confidence=0.95, portfolio_value=100_000.0)

    assert result == pytest.approx(expected, rel=1e-10)


def test_parametric_var_needs_variability():
    with pytest.raises(calc.DegenerateDataError):
        calc.parametric_var([0.001] * 40, confidence=0.95, portfolio_value=1_000.0)


def test_expected_shortfall_is_at_least_the_historical_var():
    """ES averages the tail, so it can never be smaller than the VaR threshold."""
    returns = _loss_series()

    var = calc.historical_var(returns, confidence=0.95, portfolio_value=1_000.0)
    shortfall = calc.expected_shortfall(returns, confidence=0.95, portfolio_value=1_000.0)

    assert shortfall >= var


def test_expected_shortfall_averages_the_tail():
    # With 40 observations at 95%, the threshold falls among the worst two.
    returns = _loss_series()
    threshold = float(np.quantile(returns, 0.05))
    tail = [value for value in returns if value <= threshold]
    expected = -sum(tail) / len(tail) * 1_000.0

    result = calc.expected_shortfall(returns, confidence=0.95, portfolio_value=1_000.0)

    assert result == pytest.approx(expected, rel=1e-12)


@pytest.mark.parametrize("confidence", [0.0, 0.49, 1.0, 1.5])
def test_an_invalid_confidence_is_rejected(confidence):
    with pytest.raises(calc.DegenerateDataError):
        calc.historical_var(_loss_series(), confidence=confidence, portfolio_value=1_000.0)


def test_a_non_positive_portfolio_value_is_rejected():
    with pytest.raises(calc.DegenerateDataError):
        calc.historical_var(_loss_series(), confidence=0.95, portfolio_value=0.0)


def test_var_needs_enough_observations():
    with pytest.raises(calc.InsufficientDataError):
        calc.historical_var([0.01] * 10, confidence=0.95, portfolio_value=1_000.0)


def test_the_minimum_observation_count_is_configurable():
    result = calc.historical_var(
        [-0.02, 0.01, 0.01, 0.01, 0.01],
        confidence=0.95,
        portfolio_value=1_000.0,
        minimum_observations=5,
    )

    assert result >= 0


# --- Covariance, correlation, attribution ------------------------------------


def _two_asset_matrix(periods: int = 40) -> np.ndarray:
    """Two assets whose returns are related but not identical."""
    rng = np.random.default_rng(11)
    first = rng.normal(0.0005, 0.01, periods)
    second = 0.6 * first + rng.normal(0.0002, 0.008, periods)
    return np.column_stack([first, second])


def test_covariance_is_symmetric():
    covariance = calc.covariance_matrix(_two_asset_matrix())

    assert covariance == pytest.approx(covariance.T)


def test_annualizing_covariance_scales_by_the_period_count():
    matrix = _two_asset_matrix()

    daily = calc.covariance_matrix(matrix, annualize=False)
    annual = calc.covariance_matrix(matrix, periods_per_year=252)

    assert annual == pytest.approx(daily * 252)


def test_covariance_needs_enough_observations():
    with pytest.raises(calc.InsufficientDataError):
        calc.covariance_matrix(_two_asset_matrix(periods=5))


def test_a_correlation_matrix_has_ones_on_the_diagonal():
    correlation = calc.correlation_matrix(_two_asset_matrix())

    assert np.allclose(np.diag(correlation), 1.0)


def test_identical_nonconstant_series_correlate_perfectly():
    rng = np.random.default_rng(3)
    series = rng.normal(0.0, 0.01, 40)
    matrix = np.column_stack([series, series])

    correlation = calc.correlation_matrix(matrix)

    assert correlation[0][1] == pytest.approx(1.0, abs=1e-12)


def test_an_exactly_inverted_series_correlates_negatively():
    rng = np.random.default_rng(5)
    series = rng.normal(0.0, 0.01, 40)
    matrix = np.column_stack([series, -series])

    assert calc.correlation_matrix(matrix)[0][1] == pytest.approx(-1.0, abs=1e-12)


def test_correlations_stay_within_bounds():
    correlation = calc.correlation_matrix(_two_asset_matrix(periods=200))

    assert np.all(correlation >= -1.0)
    assert np.all(correlation <= 1.0)


def test_a_constant_asset_has_an_undefined_correlation():
    """Reported as nan, so the caller can say so instead of showing a fake zero."""
    rng = np.random.default_rng(9)
    matrix = np.column_stack([rng.normal(0.0, 0.01, 40), np.zeros(40)])

    correlation = calc.correlation_matrix(matrix)

    assert math.isnan(correlation[0][1])


def test_average_pairwise_correlation_excludes_the_diagonal():
    matrix = np.array([[1.0, 0.5, 0.3], [0.5, 1.0, 0.7], [0.3, 0.7, 1.0]])

    # (0.5 + 0.3 + 0.7) / 3 = 0.5
    assert calc.average_pairwise_correlation(matrix) == pytest.approx(0.5)


def test_average_correlation_needs_at_least_two_assets():
    with pytest.raises(calc.InsufficientDataError):
        calc.average_pairwise_correlation([[1.0]])


def test_average_correlation_ignores_undefined_pairs():
    matrix = np.array([[1.0, 0.4, np.nan], [0.4, 1.0, np.nan], [np.nan, np.nan, 1.0]])

    assert calc.average_pairwise_correlation(matrix) == pytest.approx(0.4)


def test_portfolio_volatility_from_a_hand_computed_covariance():
    # Two assets, each with variance 0.04 (20% volatility), correlation zero.
    covariance = np.array([[0.04, 0.0], [0.0, 0.04]])
    # sqrt(0.5^2 * 0.04 + 0.5^2 * 0.04) = sqrt(0.02) = 0.1414...
    expected = math.sqrt(0.02)

    result = calc.portfolio_volatility_from_covariance([0.5, 0.5], covariance)

    assert result == pytest.approx(expected, rel=1e-12)


def test_perfectly_correlated_assets_do_not_diversify():
    covariance = np.array([[0.04, 0.04], [0.04, 0.04]])

    # With correlation 1, portfolio volatility equals asset volatility.
    assert calc.portfolio_volatility_from_covariance([0.5, 0.5], covariance) == pytest.approx(0.2)


def test_risk_contributions_reconcile_with_total_volatility():
    """Euler's theorem: component contributions sum exactly to the total."""
    matrix = _two_asset_matrix(periods=200)
    covariance = calc.covariance_matrix(matrix)
    weights = [0.7, 0.3]

    total = calc.portfolio_volatility_from_covariance(weights, covariance)
    contributions = calc.risk_contributions(weights, covariance)

    assert sum(item.component for item in contributions) == pytest.approx(total, rel=1e-12)


def test_risk_shares_sum_to_one():
    covariance = calc.covariance_matrix(_two_asset_matrix(periods=200))
    contributions = calc.risk_contributions([0.6, 0.4], covariance)

    assert sum(item.share for item in contributions) == pytest.approx(1.0, rel=1e-12)


def test_a_zero_weight_asset_contributes_no_risk():
    covariance = calc.covariance_matrix(_two_asset_matrix(periods=200))

    contributions = calc.risk_contributions([1.0, 0.0], covariance)

    assert contributions[1].component == pytest.approx(0.0)


def test_risk_contribution_of_an_equal_weight_uncorrelated_pair_is_symmetric():
    covariance = np.array([[0.04, 0.0], [0.0, 0.04]])

    contributions = calc.risk_contributions([0.5, 0.5], covariance)

    assert contributions[0].component == pytest.approx(contributions[1].component)
    assert contributions[0].share == pytest.approx(0.5)


def test_risk_contributions_are_undefined_without_volatility():
    with pytest.raises(calc.DegenerateDataError, match="undefined"):
        calc.risk_contributions([1.0], np.array([[0.0]]))


# --- Benchmark comparison -----------------------------------------------------


def test_a_portfolio_identical_to_its_benchmark_has_beta_one():
    rng = np.random.default_rng(13)
    series = rng.normal(0.0005, 0.01, 200)

    comparison = calc.benchmark_comparison(series, series)

    assert comparison.beta == pytest.approx(1.0, rel=1e-10)
    assert comparison.correlation == pytest.approx(1.0, rel=1e-10)
    assert comparison.tracking_error == pytest.approx(0.0, abs=1e-12)
    assert comparison.information_ratio is None


def test_a_doubled_benchmark_has_beta_two():
    rng = np.random.default_rng(17)
    benchmark = rng.normal(0.0005, 0.01, 200)

    comparison = calc.benchmark_comparison(2 * benchmark, benchmark)

    assert comparison.beta == pytest.approx(2.0, rel=1e-10)


def test_mismatched_series_lengths_are_rejected():
    with pytest.raises(calc.DegenerateDataError, match="same periods"):
        calc.benchmark_comparison([0.01] * 30, [0.01] * 29)


def test_a_constant_benchmark_makes_beta_undefined():
    rng = np.random.default_rng(19)
    with pytest.raises(calc.DegenerateDataError, match="beta is undefined"):
        calc.benchmark_comparison(rng.normal(0, 0.01, 40), np.zeros(40))


# --- Alignment ----------------------------------------------------------------


def test_alignment_uses_only_dates_present_in_every_series():
    from datetime import date

    series = {
        "AAA": [(date(2024, 1, 1), 100.0), (date(2024, 1, 2), 101.0), (date(2024, 1, 3), 102.0)],
        "BBB": [(date(2024, 1, 1), 50.0), (date(2024, 1, 3), 52.0)],
    }

    aligned = calc.align_price_series(series)

    assert aligned.symbols == ["AAA", "BBB"]
    assert aligned.dates == [date(2024, 1, 3)]
    assert aligned.dropped_dates == [date(2024, 1, 2)]
    assert aligned.observation_count == 1


def test_alignment_reports_returns_over_the_common_dates():
    from datetime import date

    series = {
        "AAA": [(date(2024, 1, 1), 100.0), (date(2024, 1, 2), 110.0)],
        "BBB": [(date(2024, 1, 1), 50.0), (date(2024, 1, 2), 45.0)],
    }

    aligned = calc.align_price_series(series)

    assert aligned.matrix[0].tolist() == pytest.approx([0.10, -0.10])


def test_alignment_needs_two_overlapping_dates():
    from datetime import date

    series = {
        "AAA": [(date(2024, 1, 1), 100.0)],
        "BBB": [(date(2024, 1, 2), 50.0)],
    }

    with pytest.raises(calc.InsufficientDataError, match="Overlapping"):
        calc.align_price_series(series)


def test_alignment_rejects_an_empty_input():
    with pytest.raises(calc.DegenerateDataError, match="No price series"):
        calc.align_price_series({})


def test_alignment_is_insensitive_to_input_order():
    from datetime import date

    forward = [(date(2024, 1, 1), 100.0), (date(2024, 1, 2), 110.0)]
    result_forward = calc.align_price_series({"AAA": forward, "BBB": forward})
    result_reversed = calc.align_price_series(
        {"BBB": list(reversed(forward)), "AAA": list(reversed(forward))}
    )

    assert np.allclose(result_forward.matrix, result_reversed.matrix)
    assert result_forward.symbols == result_reversed.symbols
