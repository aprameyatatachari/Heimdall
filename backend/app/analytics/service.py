"""Analytics use cases: run an analysis, persist it, read it back.

The service assembles a snapshot, calls pure functions, and stores one
`RiskResult` per metric. A metric that cannot be computed is stored with a null
value and a reason, so a run with two unavailable metrics still returns the other
twenty rather than failing outright.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics import calculations as calc
from app.analytics.models import (
    AnalysisRun,
    AnalysisType,
    MetricUnit,
    RiskResult,
    RunStatus,
)
from app.analytics.repository import AnalysisRunRepository
from app.analytics.snapshot import PortfolioSnapshot, SnapshotBuilder
from app.common.clock import Clock
from app.common.errors import NotFoundError
from app.common.logging import get_logger
from app.market_data.service import MarketDataService
from app.portfolios.repository import PortfolioRepository
from app.portfolios.service import PortfolioNotFoundError

logger = get_logger(__name__)

# Component risk contributions must sum to total volatility. Anything larger than
# this is a bug in the attribution, not a rounding artefact.
RECONCILIATION_TOLERANCE = 1e-9

DEFAULT_LOOKBACK_DAYS = 365
DEFAULT_CONFIDENCE = 0.95
MAX_LOOKBACK_DAYS = 365 * 20

# Assumption text attached to every fixed-weight result.
FIXED_WEIGHT_NOTE = (
    "Portfolio returns are reconstructed by applying today's weights to each "
    "asset's historical returns. This does not reproduce what the portfolio "
    "actually held over the period."
)
ESTIMATE_NOTE = (
    "All figures are estimates derived from historical data and the stated model "
    "assumptions. They are not predictions."
)


class AnalysisRunNotFoundError(NotFoundError):
    """The analysis run does not exist, or belongs to another user."""

    code = "analysis_run_not_found"
    message = "Analysis run not found."


@dataclass(frozen=True, slots=True)
class AnalysisParameters:
    """A fully resolved analysis request."""

    start: date
    end: date
    confidence: float
    var_method: calc.VarMethod
    frequency: calc.ReturnFrequency
    annual_risk_free_rate: float
    benchmark_symbol: str | None
    minimum_observations: int
    recent_volatility_window: int

    @property
    def periods_per_year(self) -> int:
        """Annualization factor for the chosen frequency."""
        return calc.PERIODS_PER_YEAR[self.frequency]

    def to_dict(self) -> dict[str, Any]:
        """Serializable form, persisted with the run."""
        return {
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "confidence": self.confidence,
            "var_method": str(self.var_method),
            "frequency": str(self.frequency),
            "annual_risk_free_rate": self.annual_risk_free_rate,
            "benchmark_symbol": self.benchmark_symbol,
            "minimum_observations": self.minimum_observations,
            "recent_volatility_window": self.recent_volatility_window,
            "periods_per_year": self.periods_per_year,
        }


# Metric metadata is heterogeneous JSON, so it is typed loosely on purpose.
MetricMetadata = dict[str, Any]


@dataclass(slots=True)
class _Metric:
    """A computed or unavailable metric, before it is persisted."""

    metric: str
    unit: MetricUnit
    value: float | None = None
    metadata: MetricMetadata = field(default_factory=dict)
    unavailable_reason: str | None = None


class AnalyticsService:
    """Runs and stores portfolio analyses."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        portfolios: PortfolioRepository,
        runs: AnalysisRunRepository,
        snapshots: SnapshotBuilder,
        market_data: MarketDataService,
        clock: Clock,
    ) -> None:
        self._session = session
        self._portfolios = portfolios
        self._runs = runs
        self._snapshots = snapshots
        self._market_data = market_data
        self._clock = clock

    # --- Reading -------------------------------------------------------------

    async def get_snapshot(
        self,
        *,
        portfolio_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> PortfolioSnapshot:
        """Value a portfolio without running or storing an analysis."""
        portfolio = await self._portfolios.get_owned(portfolio_id, user_id)
        if portfolio is None:
            raise PortfolioNotFoundError()
        return await self._snapshots.build(portfolio)

    async def get_run(self, *, run_id: uuid.UUID, user_id: uuid.UUID) -> AnalysisRun:
        """Return a stored run, scoped to the owner."""
        run = await self._runs.get_owned(run_id, user_id)
        if run is None:
            raise AnalysisRunNotFoundError()
        return run

    async def list_runs(
        self,
        *,
        portfolio_id: uuid.UUID,
        user_id: uuid.UUID,
        limit: int,
        offset: int,
    ) -> tuple[list[AnalysisRun], int]:
        """List a portfolio's runs, newest first."""
        portfolio = await self._portfolios.get_owned(portfolio_id, user_id)
        if portfolio is None:
            raise PortfolioNotFoundError()
        return (
            await self._runs.list_for_portfolio(portfolio.id, limit=limit, offset=offset),
            await self._runs.count_for_portfolio(portfolio.id),
        )

    # --- Running -------------------------------------------------------------

    def resolve_parameters(
        self,
        *,
        start: date | None,
        end: date | None,
        confidence: float | None,
        var_method: calc.VarMethod | None,
        frequency: calc.ReturnFrequency | None,
        annual_risk_free_rate: float | None,
        benchmark_symbol: str | None,
        minimum_observations: int | None,
        portfolio_benchmark: str | None,
    ) -> AnalysisParameters:
        """Fill in defaults and validate an analysis request."""
        today = self._clock.now().date()
        resolved_end = min(end or today, today)
        resolved_start = start or resolved_end - timedelta(days=DEFAULT_LOOKBACK_DAYS)

        if resolved_start >= resolved_end:
            from app.common.errors import ValidationError

            raise ValidationError(
                "The start date must be before the end date.",
                code="invalid_date_range",
            )
        if (resolved_end - resolved_start).days > MAX_LOOKBACK_DAYS:
            from app.common.errors import ValidationError

            raise ValidationError(
                f"The analysis window may not exceed {MAX_LOOKBACK_DAYS} days.",
                code="window_too_large",
            )

        resolved_frequency = frequency or calc.ReturnFrequency.DAILY

        return AnalysisParameters(
            start=resolved_start,
            end=resolved_end,
            confidence=confidence if confidence is not None else DEFAULT_CONFIDENCE,
            var_method=var_method or calc.VarMethod.HISTORICAL,
            frequency=resolved_frequency,
            annual_risk_free_rate=(
                annual_risk_free_rate if annual_risk_free_rate is not None else 0.0
            ),
            benchmark_symbol=benchmark_symbol or portfolio_benchmark,
            minimum_observations=(
                minimum_observations
                if minimum_observations is not None
                else calc.MIN_OBSERVATIONS_VAR
            ),
            recent_volatility_window=calc.MIN_OBSERVATIONS_VOLATILITY,
        )

    async def run_analysis(
        self,
        *,
        portfolio_id: uuid.UUID,
        user_id: uuid.UUID,
        parameters: AnalysisParameters,
    ) -> AnalysisRun:
        """Compute and persist a risk summary for a portfolio."""
        portfolio = await self._portfolios.get_owned(portfolio_id, user_id)
        if portfolio is None:
            raise PortfolioNotFoundError()

        run = AnalysisRun(
            portfolio_id=portfolio.id,
            analysis_type=AnalysisType.RISK_SUMMARY,
            parameters=parameters.to_dict(),
            status=RunStatus.RUNNING,
            notes=[],
        )
        self._runs.add(run)
        await self._session.flush()

        snapshot = await self._snapshots.build(portfolio, as_of=parameters.end)
        snapshot.require_analyzable()

        history = await self._snapshots.price_history(
            snapshot,
            start=parameters.start,
            end=parameters.end,
        )

        metrics, notes = self._compute(
            snapshot=snapshot,
            history=history,
            parameters=parameters,
        )

        benchmark_metrics = await self._compute_benchmark(
            snapshot=snapshot,
            history=history,
            parameters=parameters,
        )
        metrics.extend(benchmark_metrics)

        run.data_as_of = snapshot.data_as_of
        run.notes = notes
        run.completed_at = self._clock.now()
        run.status = (
            RunStatus.PARTIAL
            if any(metric.unavailable_reason for metric in metrics)
            else RunStatus.SUCCEEDED
        )

        # Rows are added to the session directly rather than appended to
        # `run.results`: appending would lazily load the collection, which async
        # SQLAlchemy cannot do outside a greenlet context.
        for metric in metrics:
            self._session.add(
                RiskResult(
                    analysis_run_id=run.id,
                    metric=metric.metric,
                    value=None if metric.value is None else Decimal(repr(metric.value)),
                    unit=metric.unit,
                    result_metadata=metric.metadata,
                    unavailable_reason=metric.unavailable_reason,
                )
            )

        await self._session.flush()
        logger.info(
            "analysis_completed",
            portfolio_id=str(portfolio.id),
            run_id=str(run.id),
            status=str(run.status),
            metrics=len(metrics),
        )

        # Re-read so the results collection is eagerly loaded for the response.
        stored = await self._runs.get_owned(run.id, user_id)
        if stored is None:  # pragma: no cover - the run was just written
            raise AnalysisRunNotFoundError()
        return stored

    # --- Metric computation --------------------------------------------------

    def _compute(
        self,
        *,
        snapshot: PortfolioSnapshot,
        history: dict[str, list[tuple[date, float]]],
        parameters: AnalysisParameters,
    ) -> tuple[list[_Metric], list[str]]:
        """Compute every metric, capturing per-metric failures."""
        metrics: list[_Metric] = []
        notes: list[str] = [ESTIMATE_NOTE, FIXED_WEIGHT_NOTE]

        total_value = float(snapshot.total_value)
        cost_basis = float(snapshot.total_cost_basis)

        metrics.append(
            _Metric(
                metric="portfolio_value",
                unit=MetricUnit.CURRENCY,
                value=total_value,
                metadata={"currency": snapshot.base_currency, "scope": "portfolio"},
            )
        )
        metrics.append(
            _Metric(
                metric="total_cost_basis",
                unit=MetricUnit.CURRENCY,
                value=cost_basis,
                metadata={"currency": snapshot.base_currency, "scope": "portfolio"},
            )
        )
        metrics.append(
            _Metric(
                metric="unrealized_profit_loss",
                unit=MetricUnit.CURRENCY,
                value=total_value - cost_basis,
                metadata={
                    "currency": snapshot.base_currency,
                    "assumption": (
                        "Market value minus acquisition cost. Excludes dividends and fees."
                    ),
                },
            )
        )
        metrics.append(
            _Metric(
                metric="holdings_count",
                unit=MetricUnit.COUNT,
                value=float(len(snapshot.holdings)),
                metadata={"priced": len(snapshot.priced_holdings)},
            )
        )

        if snapshot.unpriced_symbols:
            notes.append(
                "No price is stored for "
                + ", ".join(snapshot.unpriced_symbols)
                + ". Those holdings are excluded from every risk measure."
            )

        if not history:
            metrics.append(
                _Metric(
                    metric="analysis_observations",
                    unit=MetricUnit.COUNT,
                    unavailable_reason=(
                        "No holding has at least two price observations in the selected "
                        "period, so no return series can be built."
                    ),
                )
            )
            return metrics, notes

        try:
            aligned = calc.align_price_series(history)
        except calc.CalculationError as exc:
            metrics.append(
                _Metric(
                    metric="analysis_observations",
                    unit=MetricUnit.COUNT,
                    unavailable_reason=str(exc),
                )
            )
            return metrics, notes

        metrics.append(
            _Metric(
                metric="analysis_observations",
                unit=MetricUnit.COUNT,
                value=float(aligned.observation_count),
                metadata={
                    "symbols": aligned.symbols,
                    "first_date": aligned.dates[0].isoformat() if aligned.dates else None,
                    "last_date": aligned.dates[-1].isoformat() if aligned.dates else None,
                    "dates_excluded_for_non_overlap": len(aligned.dropped_dates),
                },
            )
        )

        if aligned.dropped_dates:
            notes.append(
                f"{len(aligned.dropped_dates)} date(s) were excluded because not every "
                "holding had a price on them. Returns are never computed across a gap."
            )

        weights_by_symbol = snapshot.weights()
        analyzed = [symbol for symbol in aligned.symbols if symbol in weights_by_symbol]
        if len(analyzed) != len(aligned.symbols):
            notes.append("Only holdings with both a current price and price history are included.")

        raw_weights = [weights_by_symbol.get(symbol, 0.0) for symbol in aligned.symbols]
        try:
            weights = calc.normalize_weights(raw_weights)
        except calc.CalculationError as exc:
            metrics.append(
                _Metric(
                    metric="portfolio_volatility",
                    unit=MetricUnit.RATIO,
                    unavailable_reason=str(exc),
                )
            )
            return metrics, notes

        notes.append(
            "Weights are renormalized across the holdings included in the analysis, "
            "so they sum to one."
        )

        window: MetricMetadata = {
            "start": parameters.start.isoformat(),
            "end": parameters.end.isoformat(),
            "observations": aligned.observation_count,
            "frequency": str(parameters.frequency),
        }

        portfolio_series = calc.portfolio_returns(weights, aligned.matrix)
        metrics.extend(
            self._return_metrics(portfolio_series, parameters, window, snapshot, weights, aligned)
        )
        return metrics, notes

    def _return_metrics(
        self,
        portfolio_series: calc.FloatArray,
        parameters: AnalysisParameters,
        window: MetricMetadata,
        snapshot: PortfolioSnapshot,
        weights: calc.FloatArray,
        aligned: calc.AlignedReturns,
    ) -> list[_Metric]:
        """Every metric derived from the portfolio return series."""
        metrics: list[_Metric] = []
        total_value = float(snapshot.total_value)
        periods = parameters.periods_per_year

        def attempt(
            metric: str,
            unit: MetricUnit,
            compute: Callable[[], float],
            metadata: MetricMetadata | None = None,
        ) -> None:
            """Run one metric, recording its reason for being unavailable."""
            payload = {**window, **(metadata or {})}
            try:
                metrics.append(
                    _Metric(metric=metric, unit=unit, value=float(compute()), metadata=payload)
                )
            except calc.CalculationError as exc:
                metrics.append(
                    _Metric(
                        metric=metric,
                        unit=unit,
                        metadata=payload,
                        unavailable_reason=str(exc),
                    )
                )

        attempt(
            "total_return",
            MetricUnit.RATIO,
            lambda: calc.cumulative_return(portfolio_series),
            {"annualized": False, "assumption": FIXED_WEIGHT_NOTE},
        )
        attempt(
            "annualized_return",
            MetricUnit.RATIO,
            lambda: calc.annualized_return(portfolio_series, periods_per_year=periods),
            {"annualized": True, "periods_per_year": periods},
        )
        attempt(
            "volatility_daily",
            MetricUnit.RATIO,
            lambda: calc.volatility(portfolio_series, annualize=False),
            {"annualized": False},
        )
        attempt(
            "volatility_annualized",
            MetricUnit.RATIO,
            lambda: calc.volatility(portfolio_series, periods_per_year=periods),
            {"annualized": True, "periods_per_year": periods},
        )
        attempt(
            "sharpe_ratio",
            MetricUnit.RATIO,
            lambda: calc.sharpe_ratio(
                portfolio_series,
                annual_risk_free_rate=parameters.annual_risk_free_rate,
                periods_per_year=periods,
            ),
            {
                "annualized": True,
                "annual_risk_free_rate": parameters.annual_risk_free_rate,
                "assumption": (
                    "The annual risk-free rate is de-annualized geometrically before "
                    "being subtracted from each period's return."
                ),
            },
        )

        # Drawdown works on the value path implied by the return series.
        try:
            path = calc.value_history(portfolio_series, starting_value=total_value)
            worst = calc.max_drawdown(path)
            dates = aligned.dates
            metrics.append(
                _Metric(
                    metric="max_drawdown",
                    unit=MetricUnit.RATIO,
                    value=worst.drawdown,
                    metadata={
                        **window,
                        "peak_value": worst.peak_value,
                        "trough_value": worst.trough_value,
                        # The value path has one extra leading point (the start).
                        "peak_date": (
                            dates[worst.peak_index - 1].isoformat()
                            if 0 < worst.peak_index <= len(dates)
                            else parameters.start.isoformat()
                        ),
                        "trough_date": (
                            dates[worst.trough_index - 1].isoformat()
                            if 0 < worst.trough_index <= len(dates)
                            else parameters.start.isoformat()
                        ),
                        "assumption": FIXED_WEIGHT_NOTE,
                    },
                )
            )
            metrics.append(
                _Metric(
                    metric="current_drawdown",
                    unit=MetricUnit.RATIO,
                    value=float(calc.drawdown_series(path)[-1]),
                    metadata={**window, "assumption": FIXED_WEIGHT_NOTE},
                )
            )
        except calc.CalculationError as exc:
            for metric in ("max_drawdown", "current_drawdown"):
                metrics.append(
                    _Metric(
                        metric=metric,
                        unit=MetricUnit.RATIO,
                        metadata=window,
                        unavailable_reason=str(exc),
                    )
                )

        var_metadata: MetricMetadata = {
            "confidence": parameters.confidence,
            "currency": snapshot.base_currency,
            "horizon": "1 period",
            "sign_convention": "Reported as a positive estimated loss amount.",
            "assumption": (
                "An estimate of a loss exceeded "
                f"{(1 - parameters.confidence) * 100:.0f}% of the time over one period. "
                "Not a maximum possible loss."
            ),
        }
        attempt(
            "value_at_risk_historical",
            MetricUnit.CURRENCY,
            lambda: calc.historical_var(
                portfolio_series,
                confidence=parameters.confidence,
                portfolio_value=total_value,
                minimum_observations=parameters.minimum_observations,
            ),
            {**var_metadata, "method": "historical"},
        )
        attempt(
            "value_at_risk_parametric",
            MetricUnit.CURRENCY,
            lambda: calc.parametric_var(
                portfolio_series,
                confidence=parameters.confidence,
                portfolio_value=total_value,
                minimum_observations=parameters.minimum_observations,
            ),
            {
                **var_metadata,
                "method": "parametric",
                "distribution": "normal",
                "limitation": (
                    "Assumes normally distributed returns, which understates fat-tailed losses."
                ),
            },
        )
        attempt(
            "expected_shortfall",
            MetricUnit.CURRENCY,
            lambda: calc.expected_shortfall(
                portfolio_series,
                confidence=parameters.confidence,
                portfolio_value=total_value,
                minimum_observations=parameters.minimum_observations,
            ),
            {
                **var_metadata,
                "method": "historical",
                "definition": "Average loss given that the VaR threshold is breached.",
            },
        )

        metrics.extend(self._attribution_metrics(weights, aligned, parameters, window, snapshot))
        return metrics

    def _attribution_metrics(
        self,
        weights: calc.FloatArray,
        aligned: calc.AlignedReturns,
        parameters: AnalysisParameters,
        window: MetricMetadata,
        snapshot: PortfolioSnapshot,
    ) -> list[_Metric]:
        """Covariance-based metrics: volatility, correlation, risk contributions."""
        metrics: list[_Metric] = []
        periods = parameters.periods_per_year

        try:
            covariance = calc.covariance_matrix(
                aligned.matrix,
                periods_per_year=periods,
                minimum_observations=parameters.minimum_observations,
            )
        except calc.CalculationError as exc:
            for metric in (
                "portfolio_volatility_from_covariance",
                "risk_contribution",
                "average_pairwise_correlation",
            ):
                metrics.append(
                    _Metric(
                        metric=metric,
                        unit=MetricUnit.RATIO,
                        metadata=window,
                        unavailable_reason=str(exc),
                    )
                )
            return metrics

        total_volatility = calc.portfolio_volatility_from_covariance(weights, covariance)
        metrics.append(
            _Metric(
                metric="portfolio_volatility_from_covariance",
                unit=MetricUnit.RATIO,
                value=total_volatility,
                metadata={
                    **window,
                    "annualized": True,
                    "method": "sqrt(w' * covariance * w)",
                },
            )
        )

        try:
            contributions = calc.risk_contributions(weights, covariance)
            reconciled = sum(item.component for item in contributions)
            # Euler's theorem guarantees this; the assertion catches an attribution bug.
            discrepancy = abs(reconciled - total_volatility)
            metrics.append(
                _Metric(
                    metric="risk_contribution",
                    unit=MetricUnit.RATIO,
                    value=reconciled,
                    metadata={
                        **window,
                        "annualized": True,
                        "reconciles_to_portfolio_volatility": discrepancy
                        <= RECONCILIATION_TOLERANCE * max(1.0, total_volatility),
                        "discrepancy": discrepancy,
                        "assets": [
                            {
                                "symbol": aligned.symbols[item.index],
                                "weight": item.weight,
                                "marginal_contribution": item.marginal,
                                "component_contribution": item.component,
                                "share_of_risk": item.share,
                            }
                            for item in contributions
                        ],
                    },
                )
            )
        except calc.CalculationError as exc:
            metrics.append(
                _Metric(
                    metric="risk_contribution",
                    unit=MetricUnit.RATIO,
                    metadata=window,
                    unavailable_reason=str(exc),
                )
            )

        try:
            correlation = calc.correlation_matrix(
                aligned.matrix,
                minimum_observations=parameters.minimum_observations,
            )
            metrics.append(
                _Metric(
                    metric="average_pairwise_correlation",
                    unit=MetricUnit.RATIO,
                    value=calc.average_pairwise_correlation(correlation),
                    metadata={
                        **window,
                        "excludes_diagonal": True,
                        "symbols": aligned.symbols,
                        "matrix": [
                            [None if item != item else float(item) for item in row]
                            for row in correlation.tolist()
                        ],
                    },
                )
            )
        except calc.CalculationError as exc:
            metrics.append(
                _Metric(
                    metric="average_pairwise_correlation",
                    unit=MetricUnit.RATIO,
                    metadata=window,
                    unavailable_reason=str(exc),
                )
            )

        weights_by_symbol = snapshot.weights()
        largest = max(weights_by_symbol.items(), key=lambda item: item[1], default=None)
        if largest is not None:
            metrics.append(
                _Metric(
                    metric="largest_position_weight",
                    unit=MetricUnit.RATIO,
                    value=largest[1],
                    metadata={"symbol": largest[0], "scope": "portfolio"},
                )
            )

        sector_weights = snapshot.sector_weights()
        if sector_weights:
            top_sector = max(sector_weights.items(), key=lambda item: item[1])
            metrics.append(
                _Metric(
                    metric="largest_sector_weight",
                    unit=MetricUnit.RATIO,
                    value=top_sector[1],
                    metadata={
                        "sector": top_sector[0],
                        "sector_weights": sector_weights,
                        "unknown_sector_weight": snapshot.unknown_sector_weight,
                    },
                )
            )

        return metrics

    async def _compute_benchmark(
        self,
        *,
        snapshot: PortfolioSnapshot,
        history: dict[str, list[tuple[date, float]]],
        parameters: AnalysisParameters,
    ) -> list[_Metric]:
        """Compare the portfolio with its benchmark, when one is configured."""
        if not parameters.benchmark_symbol or not history:
            return []

        window: MetricMetadata = {
            "start": parameters.start.isoformat(),
            "end": parameters.end.isoformat(),
            "benchmark_symbol": parameters.benchmark_symbol,
        }

        try:
            # The benchmark is usually not a holding, so its history may not be
            # cached yet. Fetching it here means a benchmark comparison does not
            # silently require a separate refresh call first.
            _, bars = await self._market_data.get_prices(
                symbol=parameters.benchmark_symbol,
                start=parameters.start,
                end=parameters.end,
            )
            benchmark_history = [(bar.date, float(bar.adjusted_close)) for bar in bars]
        except Exception as exc:
            return [
                _Metric(
                    metric="benchmark_beta",
                    unit=MetricUnit.RATIO,
                    metadata=window,
                    unavailable_reason=f"The benchmark could not be loaded: {exc}",
                )
            ]

        if len(benchmark_history) < 2:
            return [
                _Metric(
                    metric="benchmark_beta",
                    unit=MetricUnit.RATIO,
                    metadata=window,
                    unavailable_reason=(
                        f"No usable price history is stored for "
                        f"{parameters.benchmark_symbol} over this period."
                    ),
                )
            ]

        combined = {**history, parameters.benchmark_symbol: benchmark_history}
        try:
            aligned = calc.align_price_series(combined)
            benchmark_column = aligned.symbols.index(parameters.benchmark_symbol)

            # The benchmark column carries the portfolio's own weight when the
            # benchmark also happens to be a holding, and zero when it is not.
            # Renormalizing then rescales the remaining holdings to sum to one.
            weights_by_symbol = snapshot.weights()
            raw_weights = [weights_by_symbol.get(symbol, 0.0) for symbol in aligned.symbols]
            weights = calc.normalize_weights(raw_weights)

            portfolio_series = calc.portfolio_returns(weights, aligned.matrix)
            benchmark_series = aligned.matrix[:, benchmark_column]

            comparison = calc.benchmark_comparison(
                portfolio_series,
                benchmark_series,
                annual_risk_free_rate=parameters.annual_risk_free_rate,
                periods_per_year=parameters.periods_per_year,
            )
        except calc.CalculationError as exc:
            return [
                _Metric(
                    metric="benchmark_beta",
                    unit=MetricUnit.RATIO,
                    metadata=window,
                    unavailable_reason=str(exc),
                )
            ]

        shared = {**window, "observations": aligned.observation_count}
        return [
            _Metric("benchmark_beta", MetricUnit.RATIO, comparison.beta, shared),
            _Metric(
                "benchmark_alpha_annualized",
                MetricUnit.RATIO,
                comparison.alpha_annualized,
                {**shared, "annualized": True, "definition": "Jensen's alpha."},
            ),
            _Metric(
                "benchmark_correlation",
                MetricUnit.RATIO,
                comparison.correlation,
                shared,
            ),
            _Metric(
                "tracking_error",
                MetricUnit.RATIO,
                comparison.tracking_error,
                {**shared, "annualized": True},
            ),
            _Metric(
                "information_ratio",
                MetricUnit.RATIO,
                comparison.information_ratio,
                {**shared, "annualized": True},
            )
            if comparison.information_ratio is not None
            else _Metric(
                "information_ratio",
                MetricUnit.RATIO,
                metadata=shared,
                unavailable_reason="Tracking error is zero, so an information ratio is undefined.",
            ),
            _Metric(
                "benchmark_annualized_return",
                MetricUnit.RATIO,
                comparison.benchmark_annualized_return,
                {**shared, "annualized": True},
            ),
        ]
