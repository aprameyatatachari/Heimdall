"""Financial calculations.

**Pure functions only.** Nothing in this module touches HTTP, the database, or the
clock. Every function takes plain numbers in and returns plain numbers out, so
each one can be checked against a hand-computed example.

Conventions, all of them deliberate and documented in
`docs/financial-methodology.md`:

* Returns are **simple** (arithmetic), computed from **adjusted closing prices**.
* `trading_periods` defaults to 252 and is a parameter everywhere it matters.
* Value at Risk and Expected Shortfall are returned as **positive loss amounts**.
* An annual risk-free rate is de-annualized geometrically before being subtracted
  from a periodic return. It is never subtracted directly.
* A quantity that cannot be computed raises `InsufficientDataError` or
  `DegenerateDataError` rather than returning zero. Callers report the reason.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Final

import numpy as np
from numpy.typing import NDArray
from scipy import stats

FloatArray = NDArray[np.float64]

TRADING_DAYS_PER_YEAR: Final = 252
TRADING_WEEKS_PER_YEAR: Final = 52
TRADING_MONTHS_PER_YEAR: Final = 12

# Below this, a standard deviation is treated as structurally zero rather than as
# a very small number, because dividing by it produces meaningless magnitudes.
ZERO_TOLERANCE: Final = 1e-12

# Minimum observations for each family of statistic.
MIN_OBSERVATIONS_RETURN: Final = 2
MIN_OBSERVATIONS_VOLATILITY: Final = 20
MIN_OBSERVATIONS_VAR: Final = 30
MIN_OBSERVATIONS_COVARIANCE: Final = 30


class ReturnFrequency(StrEnum):
    """How often a return observation is sampled."""

    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


PERIODS_PER_YEAR: Final[dict[ReturnFrequency, int]] = {
    ReturnFrequency.DAILY: TRADING_DAYS_PER_YEAR,
    ReturnFrequency.WEEKLY: TRADING_WEEKS_PER_YEAR,
    ReturnFrequency.MONTHLY: TRADING_MONTHS_PER_YEAR,
}


class VarMethod(StrEnum):
    """How Value at Risk is estimated."""

    HISTORICAL = "historical"
    PARAMETRIC = "parametric"


class CalculationError(Exception):
    """A metric could not be computed. Reported, never silently zeroed."""

    code = "calculation_failed"


class InsufficientDataError(CalculationError):
    """Not enough observations to compute the metric."""

    code = "insufficient_data"

    def __init__(self, *, required: int, available: int, metric: str) -> None:
        super().__init__(
            f"{metric} needs at least {required} observations; {available} are available."
        )
        self.required = required
        self.available = available
        self.metric = metric


class DegenerateDataError(CalculationError):
    """The data is structurally unusable: zero variance, a singular matrix, no value."""

    code = "degenerate_data"


def _require(values: FloatArray, *, minimum: int, metric: str) -> None:
    if values.size < minimum:
        raise InsufficientDataError(required=minimum, available=int(values.size), metric=metric)


def as_array(values: object) -> FloatArray:
    """Coerce a sequence of numbers into a 1-D float array."""
    array = np.asarray(values, dtype=np.float64).ravel()
    if array.size and not np.all(np.isfinite(array)):
        raise DegenerateDataError("The series contains non-finite values.")
    return array


# --- Returns ------------------------------------------------------------------


def simple_returns(prices: object) -> FloatArray:
    """Simple period-over-period returns.

        r(t) = price(t) / price(t-1) - 1

    Requires at least two prices, and every price must be positive: a zero or
    negative price makes the return undefined rather than large.
    """
    series = as_array(prices)
    _require(series, minimum=MIN_OBSERVATIONS_RETURN, metric="Return calculation")

    if np.any(series <= 0):
        raise DegenerateDataError("Prices must be positive to compute returns.")

    return series[1:] / series[:-1] - 1.0


def portfolio_returns(weights: object, asset_returns: object) -> FloatArray:
    """Weighted portfolio returns from a matrix of asset returns.

        portfolio_return(t) = sum over i of weight(i) * asset_return(i, t)

    `asset_returns` is shaped (periods, assets). The weights are **fixed** across
    the window, which is an approximation: it does not reconstruct what the
    portfolio actually held historically. Callers must label it as such.
    """
    weight_array = as_array(weights)
    matrix = np.asarray(asset_returns, dtype=np.float64)

    if matrix.ndim != 2:
        raise DegenerateDataError("Asset returns must be a two-dimensional matrix.")
    if matrix.shape[1] != weight_array.size:
        raise DegenerateDataError(
            f"Received {weight_array.size} weights for {matrix.shape[1]} assets."
        )
    if matrix.shape[0] == 0:
        raise InsufficientDataError(required=1, available=0, metric="Portfolio returns")

    return matrix @ weight_array


def normalize_weights(values: object) -> FloatArray:
    """Scale position values into weights that sum to one.

    Raises `DegenerateDataError` for an empty or zero-value portfolio: a portfolio
    worth nothing has no weights, and reporting zeroes would imply it does.
    """
    array = as_array(values)
    if array.size == 0:
        raise DegenerateDataError("An empty portfolio has no weights.")

    total = float(array.sum())
    if abs(total) < ZERO_TOLERANCE:
        raise DegenerateDataError("A portfolio with no value has no weights.")

    return array / total


def cumulative_return(returns: object) -> float:
    """Compound a series of periodic returns into one total return.

    total = product of (1 + r) - 1
    """
    series = as_array(returns)
    if series.size == 0:
        raise InsufficientDataError(required=1, available=0, metric="Cumulative return")
    if np.any(series <= -1.0):
        raise DegenerateDataError("A return of -100% or worse makes compounding undefined.")

    return float(np.prod(1.0 + series) - 1.0)


def annualized_return(
    returns: object,
    *,
    periods_per_year: int = TRADING_DAYS_PER_YEAR,
) -> float:
    """Geometric annualized return (compound annual growth rate).

    annualized = (1 + total_return) ** (periods_per_year / periods) - 1
    """
    series = as_array(returns)
    _require(series, minimum=MIN_OBSERVATIONS_RETURN, metric="Annualized return")

    total = cumulative_return(series)
    return float((1.0 + total) ** (periods_per_year / series.size) - 1.0)


def value_history(returns: object, *, starting_value: float) -> FloatArray:
    """Compound a return series into a value path, starting at `starting_value`.

    The result has one more point than the return series: the starting value, then
    one value per period.
    """
    series = as_array(returns)
    if starting_value <= 0:
        raise DegenerateDataError("The starting value must be positive.")

    path = np.empty(series.size + 1, dtype=np.float64)
    path[0] = starting_value
    path[1:] = starting_value * np.cumprod(1.0 + series)
    return path


# --- Risk ---------------------------------------------------------------------


def volatility(
    returns: object,
    *,
    annualize: bool = True,
    periods_per_year: int = TRADING_DAYS_PER_YEAR,
    minimum_observations: int = MIN_OBSERVATIONS_VOLATILITY,
) -> float:
    """Standard deviation of returns, annualized by default.

        annualized_volatility = stdev(returns) * sqrt(periods_per_year)

    Uses the **sample** standard deviation (`ddof=1`), because the observations are
    a sample of a process rather than a whole population.
    """
    series = as_array(returns)
    _require(series, minimum=max(minimum_observations, 2), metric="Volatility")

    deviation = float(np.std(series, ddof=1))
    return deviation * float(np.sqrt(periods_per_year)) if annualize else deviation


def deannualize_rate(annual_rate: float, *, periods_per_year: int) -> float:
    """Convert an annual rate into the equivalent rate for one period.

        periodic = (1 + annual) ** (1 / periods_per_year) - 1

    Done geometrically, not by dividing. Subtracting an annual rate directly from a
    daily return would overstate the risk-free drag by two orders of magnitude.
    """
    if periods_per_year <= 0:
        raise DegenerateDataError("periods_per_year must be positive.")
    if annual_rate <= -1.0:
        raise DegenerateDataError("An annual rate of -100% or worse cannot be de-annualized.")

    return float((1.0 + annual_rate) ** (1.0 / periods_per_year) - 1.0)


def sharpe_ratio(
    returns: object,
    *,
    annual_risk_free_rate: float = 0.0,
    periods_per_year: int = TRADING_DAYS_PER_YEAR,
) -> float:
    """Annualized Sharpe ratio.

        excess(t) = return(t) - periodic_risk_free_rate
        Sharpe    = mean(excess) / stdev(excess) * sqrt(periods_per_year)

    Raises `DegenerateDataError` when excess returns have no variance: the ratio is
    undefined, and a large sentinel would be read as a very good result.
    """
    series = as_array(returns)
    _require(series, minimum=MIN_OBSERVATIONS_VOLATILITY, metric="Sharpe ratio")

    periodic_rate = deannualize_rate(annual_risk_free_rate, periods_per_year=periods_per_year)
    excess = series - periodic_rate

    deviation = float(np.std(excess, ddof=1))
    if deviation < ZERO_TOLERANCE:
        raise DegenerateDataError(
            "Excess returns have no variability, so a Sharpe ratio is undefined."
        )

    return float(np.mean(excess) / deviation * np.sqrt(periods_per_year))


def drawdown_series(values: object) -> FloatArray:
    """Drawdown at each point, relative to the running peak.

        drawdown(t) = value(t) / running_peak(t) - 1

    Every element is zero or negative.
    """
    series = as_array(values)
    if series.size == 0:
        raise InsufficientDataError(required=1, available=0, metric="Drawdown")
    if np.any(series <= 0):
        raise DegenerateDataError("Portfolio values must be positive to compute drawdown.")

    running_peak = np.maximum.accumulate(series)
    return series / running_peak - 1.0


@dataclass(frozen=True, slots=True)
class MaxDrawdown:
    """Worst peak-to-trough decline in a value path."""

    # Negative or zero, expressed as a fraction.
    drawdown: float
    peak_index: int
    trough_index: int
    peak_value: float
    trough_value: float


def max_drawdown(values: object) -> MaxDrawdown:
    """Largest peak-to-trough decline, with the indices that produced it."""
    series = as_array(values)
    drawdowns = drawdown_series(series)

    trough_index = int(np.argmin(drawdowns))
    peak_index = int(np.argmax(series[: trough_index + 1]))

    return MaxDrawdown(
        drawdown=float(drawdowns[trough_index]),
        peak_index=peak_index,
        trough_index=trough_index,
        peak_value=float(series[peak_index]),
        trough_value=float(series[trough_index]),
    )


def historical_var(
    returns: object,
    *,
    confidence: float,
    portfolio_value: float,
    minimum_observations: int = MIN_OBSERVATIONS_VAR,
) -> float:
    """Historical-simulation Value at Risk, as a positive loss amount.

        VaR = -quantile(returns, 1 - confidence) * portfolio_value

    This is an estimate of a loss that is exceeded `(1 - confidence)` of the time
    over one period, **not** a maximum possible loss. A profitable tail can make
    the raw quantile positive; the result is then floored at zero, because a
    negative "loss" is not meaningful.
    """
    series = as_array(returns)
    _require(series, minimum=minimum_observations, metric="Historical VaR")
    _check_confidence(confidence)
    _check_value(portfolio_value)

    quantile = float(np.quantile(series, 1.0 - confidence, method="linear"))
    return max(-quantile * portfolio_value, 0.0)


def parametric_var(
    returns: object,
    *,
    confidence: float,
    portfolio_value: float,
    minimum_observations: int = MIN_OBSERVATIONS_VAR,
) -> float:
    """Normal (variance-covariance) Value at Risk, as a positive loss amount.

        VaR = -(mean + z(1 - confidence) * stdev) * portfolio_value

    Assumes returns are normally distributed. Real return distributions have fatter
    tails, so this usually **understates** extreme losses; responses say so.
    """
    series = as_array(returns)
    _require(series, minimum=minimum_observations, metric="Parametric VaR")
    _check_confidence(confidence)
    _check_value(portfolio_value)

    deviation = float(np.std(series, ddof=1))
    if deviation < ZERO_TOLERANCE:
        raise DegenerateDataError(
            "Returns have no variability, so a parametric VaR is not meaningful."
        )

    z_score = float(stats.norm.ppf(1.0 - confidence))
    return max(-(float(np.mean(series)) + z_score * deviation) * portfolio_value, 0.0)


def expected_shortfall(
    returns: object,
    *,
    confidence: float,
    portfolio_value: float,
    minimum_observations: int = MIN_OBSERVATIONS_VAR,
) -> float:
    """Expected Shortfall (conditional VaR), as a positive loss amount.

        threshold = quantile(returns, 1 - confidence)
        ES        = -mean(returns <= threshold) * portfolio_value

    The average loss **given** that the VaR threshold is breached, so it is always
    at least as large as the historical VaR at the same confidence.
    """
    series = as_array(returns)
    _require(series, minimum=minimum_observations, metric="Expected Shortfall")
    _check_confidence(confidence)
    _check_value(portfolio_value)

    threshold = float(np.quantile(series, 1.0 - confidence, method="linear"))
    tail = series[series <= threshold]

    if tail.size == 0:  # pragma: no cover - the quantile is always attained
        raise DegenerateDataError("No observations fall in the loss tail.")

    return max(-float(np.mean(tail)) * portfolio_value, 0.0)


def _check_confidence(confidence: float) -> None:
    if not 0.5 <= confidence < 1.0:
        raise DegenerateDataError("Confidence must be at least 0.5 and below 1.0.")


def _check_value(portfolio_value: float) -> None:
    if portfolio_value <= 0:
        raise DegenerateDataError("Portfolio value must be positive.")


# --- Covariance and risk attribution ------------------------------------------


def covariance_matrix(
    asset_returns: object,
    *,
    annualize: bool = True,
    periods_per_year: int = TRADING_DAYS_PER_YEAR,
    minimum_observations: int = MIN_OBSERVATIONS_COVARIANCE,
) -> FloatArray:
    """Sample covariance matrix of a (periods, assets) return matrix."""
    matrix = np.asarray(asset_returns, dtype=np.float64)
    if matrix.ndim != 2:
        raise DegenerateDataError("Asset returns must be a two-dimensional matrix.")
    if matrix.shape[0] < max(minimum_observations, 2):
        raise InsufficientDataError(
            required=max(minimum_observations, 2),
            available=int(matrix.shape[0]),
            metric="Covariance matrix",
        )

    covariance = np.cov(matrix, rowvar=False, ddof=1)
    covariance = np.atleast_2d(covariance)
    return covariance * periods_per_year if annualize else covariance


def correlation_matrix(
    asset_returns: object,
    *,
    minimum_observations: int = MIN_OBSERVATIONS_COVARIANCE,
) -> FloatArray:
    """Sample correlation matrix.

    An asset with zero variance has no correlation with anything; its row and
    column are `nan` so the caller can report it rather than showing a fake zero.
    """
    matrix = np.asarray(asset_returns, dtype=np.float64)
    covariance = covariance_matrix(
        matrix,
        annualize=False,
        minimum_observations=minimum_observations,
    )

    deviations = np.sqrt(np.diag(covariance))
    with np.errstate(divide="ignore", invalid="ignore"):
        outer = np.outer(deviations, deviations)
        correlation = np.where(outer > ZERO_TOLERANCE, covariance / outer, np.nan)

    # Clip floating-point overshoot past the mathematical bounds.
    return np.clip(correlation, -1.0, 1.0)


def average_pairwise_correlation(correlation: object) -> float:
    """Mean of the off-diagonal entries of a correlation matrix.

    The diagonal is excluded: it is always one and would bias the average upward.
    `nan` entries, from zero-variance assets, are ignored.
    """
    matrix = np.asarray(correlation, dtype=np.float64)
    if matrix.ndim != 2 or matrix.shape[0] != matrix.shape[1]:
        raise DegenerateDataError("A correlation matrix must be square.")
    if matrix.shape[0] < 2:
        raise InsufficientDataError(
            required=2,
            available=int(matrix.shape[0]),
            metric="Average pairwise correlation",
        )

    upper = matrix[np.triu_indices_from(matrix, k=1)]
    usable = upper[np.isfinite(upper)]

    if usable.size == 0:
        raise DegenerateDataError("No asset pair has a defined correlation.")

    return float(np.mean(usable))


def portfolio_volatility_from_covariance(weights: object, covariance: object) -> float:
    """Portfolio volatility from weights and a covariance matrix.

    volatility = sqrt(w' * covariance * w)
    """
    weight_array = as_array(weights)
    matrix = np.asarray(covariance, dtype=np.float64)

    if matrix.shape != (weight_array.size, weight_array.size):
        raise DegenerateDataError("Covariance matrix and weights have different sizes.")

    variance = float(weight_array @ matrix @ weight_array)
    if variance < 0:
        # Only reachable through floating-point error on a near-singular matrix.
        variance = 0.0

    return float(np.sqrt(variance))


@dataclass(frozen=True, slots=True)
class RiskContribution:
    """How one asset contributes to total portfolio volatility."""

    index: int
    weight: float
    # Change in portfolio volatility per unit change in this weight.
    marginal: float
    # weight * marginal. These sum to the total portfolio volatility.
    component: float
    # component / total, a share of risk.
    share: float


def risk_contributions(weights: object, covariance: object) -> list[RiskContribution]:
    """Marginal and component contributions to portfolio volatility.

        MRC(i) = (covariance * w)(i) / portfolio_volatility
        CRC(i) = w(i) * MRC(i)

    By Euler's homogeneous-function theorem the component contributions sum
    exactly to the portfolio volatility, which the service verifies numerically.
    """
    weight_array = as_array(weights)
    matrix = np.asarray(covariance, dtype=np.float64)
    total = portfolio_volatility_from_covariance(weight_array, matrix)

    if total < ZERO_TOLERANCE:
        raise DegenerateDataError(
            "Portfolio volatility is zero, so risk contributions are undefined."
        )

    marginal = (matrix @ weight_array) / total
    component = weight_array * marginal

    return [
        RiskContribution(
            index=index,
            weight=float(weight_array[index]),
            marginal=float(marginal[index]),
            component=float(component[index]),
            share=float(component[index] / total),
        )
        for index in range(weight_array.size)
    ]


# --- Benchmark comparison -----------------------------------------------------


@dataclass(frozen=True, slots=True)
class BenchmarkComparison:
    """Portfolio behaviour relative to a benchmark, over one window."""

    beta: float
    # Annualized excess return over what beta alone would predict (Jensen's alpha).
    alpha_annualized: float
    correlation: float
    # Annualized standard deviation of the return difference.
    tracking_error: float
    # Annualized active return divided by tracking error.
    information_ratio: float | None
    portfolio_annualized_return: float
    benchmark_annualized_return: float


def benchmark_comparison(
    portfolio: object,
    benchmark: object,
    *,
    annual_risk_free_rate: float = 0.0,
    periods_per_year: int = TRADING_DAYS_PER_YEAR,
) -> BenchmarkComparison:
    """Compare a portfolio return series with a benchmark series.

    Both series must already be aligned to the same periods and be the same length.
    """
    portfolio_returns_array = as_array(portfolio)
    benchmark_returns = as_array(benchmark)

    if portfolio_returns_array.size != benchmark_returns.size:
        raise DegenerateDataError("Portfolio and benchmark series must cover the same periods.")
    _require(
        portfolio_returns_array, minimum=MIN_OBSERVATIONS_VOLATILITY, metric="Benchmark comparison"
    )

    benchmark_variance = float(np.var(benchmark_returns, ddof=1))
    if benchmark_variance < ZERO_TOLERANCE:
        raise DegenerateDataError(
            "The benchmark has no variability over this window, so beta is undefined."
        )

    covariance = float(np.cov(portfolio_returns_array, benchmark_returns, ddof=1)[0][1])
    beta = covariance / benchmark_variance

    periodic_rate = deannualize_rate(annual_risk_free_rate, periods_per_year=periods_per_year)
    portfolio_excess = float(np.mean(portfolio_returns_array)) - periodic_rate
    benchmark_excess = float(np.mean(benchmark_returns)) - periodic_rate
    alpha_periodic = portfolio_excess - beta * benchmark_excess

    difference = portfolio_returns_array - benchmark_returns
    tracking_error = float(np.std(difference, ddof=1)) * float(np.sqrt(periods_per_year))
    active_return = float(np.mean(difference)) * periods_per_year

    portfolio_deviation = float(np.std(portfolio_returns_array, ddof=1))
    benchmark_deviation = float(np.std(benchmark_returns, ddof=1))
    correlation = (
        covariance / (portfolio_deviation * benchmark_deviation)
        if portfolio_deviation > ZERO_TOLERANCE and benchmark_deviation > ZERO_TOLERANCE
        else float("nan")
    )

    return BenchmarkComparison(
        beta=beta,
        alpha_annualized=alpha_periodic * periods_per_year,
        correlation=float(np.clip(correlation, -1.0, 1.0)),
        tracking_error=tracking_error,
        information_ratio=(
            active_return / tracking_error if tracking_error > ZERO_TOLERANCE else None
        ),
        portfolio_annualized_return=annualized_return(
            portfolio_returns_array, periods_per_year=periods_per_year
        ),
        benchmark_annualized_return=annualized_return(
            benchmark_returns, periods_per_year=periods_per_year
        ),
    )


# --- Alignment ----------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AlignedReturns:
    """Asset return series aligned to a common set of dates.

    `dates[i]` is the date of return row `i`, so row `i` is the return **from** the
    previous common date **to** `dates[i]`.
    """

    symbols: list[str]
    dates: list[date]
    # Shaped (periods, assets).
    matrix: FloatArray
    # Dates present for some assets but not all, and therefore excluded.
    dropped_dates: list[date]

    @property
    def observation_count(self) -> int:
        """Number of return periods."""
        return int(self.matrix.shape[0]) if self.matrix.ndim == 2 else 0


def align_price_series(
    series: dict[str, list[tuple[date, float]]],
) -> AlignedReturns:
    """Align several price series and convert them to returns.

    Only dates present in **every** series are used, so a return is never computed
    across a gap in one asset while another asset moved. Excluded dates are
    reported rather than hidden, because a large number of them means the analysis
    covers less history than the user asked for.
    """
    if not series:
        raise DegenerateDataError("No price series were supplied.")

    symbols = sorted(series)
    per_symbol_dates = [{observation[0] for observation in series[symbol]} for symbol in symbols]
    common = set.intersection(*per_symbol_dates) if per_symbol_dates else set()
    union = set.union(*per_symbol_dates) if per_symbol_dates else set()

    common_dates = sorted(common)
    if len(common_dates) < MIN_OBSERVATIONS_RETURN:
        raise InsufficientDataError(
            required=MIN_OBSERVATIONS_RETURN,
            available=len(common_dates),
            metric="Overlapping price history",
        )

    prices = np.empty((len(common_dates), len(symbols)), dtype=np.float64)
    for column, symbol in enumerate(symbols):
        lookup = dict(series[symbol])
        prices[:, column] = [lookup[day] for day in common_dates]

    if np.any(prices <= 0):
        raise DegenerateDataError("Prices must be positive to compute returns.")

    matrix = prices[1:, :] / prices[:-1, :] - 1.0

    return AlignedReturns(
        symbols=symbols,
        dates=common_dates[1:],
        matrix=matrix,
        dropped_dates=sorted(union - common),
    )
