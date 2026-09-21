"""Report generation.

A report is assembled from **stored** analysis inputs — an analysis run, stress
tests, and signals — so the same report can be regenerated from the same
identifiers later. Nothing is recomputed on the fly except the layout.

A failure while rendering marks the report `failed` and leaves every analysis,
stress test, and signal untouched: the report is a separate record, and the
request's transaction rolls back only the report row.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.models import AnalysisRun, MetricUnit, RiskResult
from app.analytics.repository import AnalysisRunRepository
from app.analytics.service import AnalysisParameters, AnalyticsService
from app.analytics.snapshot import PortfolioSnapshot, SnapshotBuilder
from app.common.clock import Clock
from app.common.errors import NotFoundError, ValidationError
from app.common.logging import get_logger
from app.early_warning.models import WarningSignal
from app.portfolios.models import Portfolio
from app.portfolios.repository import PortfolioRepository
from app.portfolios.service import PortfolioNotFoundError
from app.reports.models import Report, ReportFormat, ReportStatus
from app.reports.renderer import (
    MetricRow,
    ReportData,
    TableBlock,
    format_money,
    format_percent,
    format_ratio,
    render_report,
)
from app.stress_testing.models import StressTestRun
from app.stress_testing.scenarios import STRESS_TEST_LIMITATIONS

logger = get_logger(__name__)

# How many stress tests and signals a report includes, newest first. Bounded so a
# report stays a readable document and its generation stays fast.
MAX_STRESS_TESTS = 5
MAX_SIGNALS = 25

DATA_SOURCES = (
    "Daily price history from Heimdall's configured market-data provider, stored "
    "locally and identified by source on every observation.",
    "Positions entered manually or imported from CSV by the portfolio owner.",
    "Instrument metadata, including sector, from the market-data provider.",
)

# Metrics promoted into each report section, in the order they are presented.
SUMMARY_METRICS = (
    ("portfolio_value", "Portfolio market value"),
    ("total_cost_basis", "Total acquisition cost"),
    ("unrealized_profit_loss", "Unrealized profit or loss"),
    ("holdings_count", "Holdings"),
    ("largest_position_weight", "Largest position weight"),
    ("largest_sector_weight", "Largest sector weight"),
)
PERFORMANCE_METRICS = (
    ("total_return", "Total return"),
    ("annualized_return", "Annualized return"),
    ("benchmark_annualized_return", "Benchmark annualized return"),
    ("benchmark_beta", "Beta to benchmark"),
    ("benchmark_alpha_annualized", "Alpha (annualized)"),
    ("benchmark_correlation", "Correlation with benchmark"),
    ("tracking_error", "Tracking error (annualized)"),
    ("information_ratio", "Information ratio"),
)
RISK_METRICS = (
    ("volatility_daily", "Volatility (daily)"),
    ("volatility_annualized", "Volatility (annualized)"),
    ("sharpe_ratio", "Sharpe ratio (annualized)"),
    ("max_drawdown", "Maximum drawdown"),
    ("current_drawdown", "Current drawdown"),
    ("value_at_risk_historical", "Value at Risk (historical)"),
    ("value_at_risk_parametric", "Value at Risk (parametric)"),
    ("expected_shortfall", "Expected Shortfall"),
    ("portfolio_volatility_from_covariance", "Volatility from covariance"),
    ("average_pairwise_correlation", "Average pairwise correlation"),
)


class ReportNotFoundError(NotFoundError):
    """The report does not exist, or belongs to another user."""

    code = "report_not_found"
    message = "Report not found."


class ReportNotReadyError(ValidationError):
    """The report exists but has no downloadable content."""

    code = "report_not_ready"
    message = "This report is not available for download."


class ReportGenerationError(ValidationError):
    """The report could not be rendered."""

    code = "report_generation_failed"
    message = "The report could not be generated."


@dataclass(frozen=True, slots=True)
class ReportRequest:
    """What to include in a report."""

    analysis_run_id: uuid.UUID | None = None
    include_stress_tests: bool = True
    include_signals: bool = True
    title: str | None = None


class ReportService:
    """Builds, stores, and serves Heimdall Risk Reports."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        portfolios: PortfolioRepository,
        runs: AnalysisRunRepository,
        snapshots: SnapshotBuilder,
        analytics: AnalyticsService,
        clock: Clock,
    ) -> None:
        self._session = session
        self._portfolios = portfolios
        self._runs = runs
        self._snapshots = snapshots
        self._analytics = analytics
        self._clock = clock

    # --- Reading -------------------------------------------------------------

    async def get(self, *, report_id: uuid.UUID, user_id: uuid.UUID) -> Report:
        """Return a report the caller owns."""
        result = await self._session.execute(
            select(Report).where(Report.id == report_id, Report.user_id == user_id)
        )
        report = result.scalar_one_or_none()
        if report is None:
            raise ReportNotFoundError()
        return report

    async def get_downloadable(self, *, report_id: uuid.UUID, user_id: uuid.UUID) -> Report:
        """Return a report that has rendered content."""
        report = await self.get(report_id=report_id, user_id=user_id)
        if not report.is_downloadable:
            raise ReportNotReadyError(
                f"This report has status {report.status} and cannot be downloaded."
            )
        return report

    async def list_for_portfolio(
        self,
        *,
        portfolio_id: uuid.UUID,
        user_id: uuid.UUID,
        limit: int,
        offset: int,
    ) -> tuple[list[Report], int]:
        """A portfolio's reports, newest first."""
        portfolio = await self._portfolios.get_owned(portfolio_id, user_id)
        if portfolio is None:
            raise PortfolioNotFoundError()

        rows = await self._session.execute(
            select(Report)
            .where(Report.portfolio_id == portfolio_id, Report.user_id == user_id)
            .order_by(Report.created_at.desc(), Report.id.desc())
            .limit(limit)
            .offset(offset)
        )
        total = await self._session.execute(
            select(func.count())
            .select_from(Report)
            .where(Report.portfolio_id == portfolio_id, Report.user_id == user_id)
        )
        return list(rows.scalars()), int(total.scalar_one())

    # --- Generating ----------------------------------------------------------

    async def generate(
        self,
        *,
        portfolio_id: uuid.UUID,
        user_id: uuid.UUID,
        request: ReportRequest,
    ) -> Report:
        """Generate a report and store its bytes."""
        portfolio = await self._portfolios.get_owned(portfolio_id, user_id)
        if portfolio is None:
            raise PortfolioNotFoundError()

        run = await self._resolve_run(portfolio=portfolio, user_id=user_id, request=request)
        snapshot = await self._snapshots.build(portfolio)

        report = Report(
            portfolio_id=portfolio.id,
            user_id=user_id,
            analysis_run_id=run.id if run is not None else None,
            title=request.title or f"Heimdall Risk Report — {portfolio.name}",
            format=ReportFormat.PDF,
            status=ReportStatus.GENERATING,
            inputs={
                "portfolio_id": str(portfolio.id),
                "analysis_run_id": str(run.id) if run is not None else None,
                "analysis_parameters": run.parameters if run is not None else None,
                "data_as_of": snapshot.data_as_of.isoformat() if snapshot.data_as_of else None,
                "include_stress_tests": request.include_stress_tests,
                "include_signals": request.include_signals,
                "generated_by_version": "0.1.0",
            },
        )
        self._session.add(report)
        await self._session.flush()

        try:
            data = await self._assemble(
                portfolio=portfolio,
                snapshot=snapshot,
                run=run,
                request=request,
            )
            content = render_report(data)
        except Exception as exc:
            # The report row records the failure. Analysis data is untouched.
            report.status = ReportStatus.FAILED
            report.error_message = f"{type(exc).__name__}: {exc}"
            report.completed_at = self._clock.now()
            await self._session.flush()
            logger.exception("report_generation_failed", report_id=str(report.id))
            raise ReportGenerationError(
                "The report could not be generated. No analysis data was changed."
            ) from exc

        report.content = content
        report.size_bytes = len(content)
        report.filename = _filename(portfolio.name, self._clock.now().date())
        report.status = ReportStatus.SUCCEEDED
        report.completed_at = self._clock.now()
        await self._session.flush()

        logger.info(
            "report_generated",
            report_id=str(report.id),
            portfolio_id=str(portfolio.id),
            size_bytes=report.size_bytes,
        )
        return report

    # --- Internals -----------------------------------------------------------

    async def _resolve_run(
        self,
        *,
        portfolio: Portfolio,
        user_id: uuid.UUID,
        request: ReportRequest,
    ) -> AnalysisRun | None:
        """Find the analysis run a report is built from.

        An explicit id is used when given. Otherwise the portfolio's most recent
        run is reused, and a fresh one is computed only when none exists — so a
        report reflects stored analysis rather than silently producing new numbers.
        """
        if request.analysis_run_id is not None:
            run = await self._runs.get_owned(request.analysis_run_id, user_id)
            if run is None:
                raise ReportNotFoundError(
                    "The requested analysis run does not exist for this account.",
                    code="analysis_run_not_found",
                )
            if run.portfolio_id != portfolio.id:
                raise ReportNotFoundError(
                    "That analysis run belongs to a different portfolio.",
                    code="analysis_run_not_found",
                )
            return run

        latest = await self._runs.latest_for_portfolio(portfolio.id)
        if latest is not None:
            return latest

        parameters: AnalysisParameters = self._analytics.resolve_parameters(
            start=None,
            end=None,
            confidence=None,
            var_method=None,
            frequency=None,
            annual_risk_free_rate=None,
            benchmark_symbol=None,
            minimum_observations=None,
            portfolio_benchmark=portfolio.benchmark_symbol,
        )
        return await self._analytics.run_analysis(
            portfolio_id=portfolio.id,
            user_id=user_id,
            parameters=parameters,
        )

    async def _assemble(
        self,
        *,
        portfolio: Portfolio,
        snapshot: PortfolioSnapshot,
        run: AnalysisRun | None,
        request: ReportRequest,
    ) -> ReportData:
        """Turn stored records into the renderer's plain-data input."""
        currency = snapshot.base_currency
        results = {result.metric: result for result in (run.results if run is not None else [])}

        data = ReportData(
            portfolio_name=portfolio.name,
            base_currency=currency,
            generated_at=self._clock.now(),
            data_as_of=snapshot.data_as_of,
            analysis_period=_period(run),
            summary=_metric_rows(SUMMARY_METRICS, results, currency),
            performance=_metric_rows(PERFORMANCE_METRICS, results, currency),
            risk=_metric_rows(RISK_METRICS, results, currency),
            holdings=_holdings_block(snapshot, currency),
            allocation=_allocation_block(snapshot),
            risk_contribution=_risk_contribution_block(results),
            assumptions=list(run.notes) if run is not None else [],
            data_sources=list(DATA_SOURCES),
            limitations=list(STRESS_TEST_LIMITATIONS),
            unavailable=[
                f"{result.metric}: {result.unavailable_reason}"
                for result in results.values()
                if result.unavailable_reason
            ],
        )

        if request.include_stress_tests:
            data.stress_tests = await self._stress_blocks(portfolio.id, currency)

        if request.include_signals:
            data.signals = await self._signal_block(portfolio.id)

        return data

    async def _stress_blocks(self, portfolio_id: uuid.UUID, currency: str) -> list[TableBlock]:
        """One table per recent stress test."""
        result = await self._session.execute(
            select(StressTestRun)
            .where(StressTestRun.portfolio_id == portfolio_id)
            .order_by(StressTestRun.created_at.desc())
            .limit(MAX_STRESS_TESTS)
        )
        runs = list(result.scalars())

        if not runs:
            return [
                TableBlock(
                    title="Stress tests",
                    columns=["Scenario", "Result"],
                    rows=[],
                    empty_note="No stress test has been run for this portfolio.",
                )
            ]

        blocks: list[TableBlock] = []
        for run in runs:
            payload: dict[str, Any] = run.result or {}
            rows = [
                [
                    position["symbol"],
                    format_money(Decimal(position["starting_value"]), currency),
                    format_percent(Decimal(position["applied_return"]), signed=True),
                    format_money(Decimal(position["impact"]), currency, signed=True),
                    format_percent(
                        Decimal(position["contribution_to_loss"])
                        if position.get("contribution_to_loss") is not None
                        else None
                    ),
                ]
                for position in payload.get("positions", [])
            ]
            header = (
                f"{run.scenario_name} — "
                f"{format_money(run.starting_value, currency)} to "
                f"{format_money(run.ending_value, currency)}, "
                f"{format_money(run.total_impact, currency, signed=True)} "
                f"({format_percent(run.total_impact_percent, signed=True)})"
            )
            blocks.append(
                TableBlock(
                    title=header,
                    columns=[
                        "Holding",
                        "Starting value",
                        "Applied return",
                        "Impact",
                        "Share of loss",
                    ],
                    rows=rows,
                    signed_column=3,
                )
            )

        return blocks

    async def _signal_block(self, portfolio_id: uuid.UUID) -> TableBlock:
        """Recent Gjallarhorn Signals, open ones first."""
        result = await self._session.execute(
            select(WarningSignal)
            .where(WarningSignal.portfolio_id == portfolio_id)
            .order_by(WarningSignal.created_at.desc())
            .limit(MAX_SIGNALS)
        )
        signals = list(result.scalars())

        rows = [
            [
                signal.severity,
                signal.title,
                _signal_metric(signal),
                signal.status,
                signal.data_as_of.isoformat() if signal.data_as_of else "unknown",
            ]
            for signal in signals
        ]

        return TableBlock(
            title="Signals",
            columns=["Severity", "Condition", "Observed vs threshold", "Status", "Data as of"],
            rows=rows,
            empty_note=(
                "No signals have been recorded. Either no monitoring run has taken "
                "place, or no configured threshold was crossed."
            ),
        )


def _signal_metric(signal: WarningSignal) -> str:
    """Observed value against its threshold, with the unit."""
    return f"{signal.observed_value:.4f} vs {signal.threshold_value:.4f} ({signal.unit})"


def _period(run: AnalysisRun | None) -> str:
    """The analysis window a report covers."""
    if run is None:
        return "no analysis available"
    parameters = run.parameters or {}
    start, end = parameters.get("start"), parameters.get("end")
    if start and end:
        return f"{start} to {end}"
    return "unspecified"


def _metric_rows(
    wanted: tuple[tuple[str, str], ...],
    results: dict[str, RiskResult],
    currency: str,
) -> list[MetricRow]:
    """Map stored metrics onto report rows, in presentation order."""
    rows: list[MetricRow] = []

    for metric, label in wanted:
        result = results.get(metric)
        if result is None:
            continue

        if result.value is None:
            rows.append(
                MetricRow(
                    label=label, value="unavailable", unit="", note=result.unavailable_reason or ""
                )
            )
            continue

        metadata = result.result_metadata or {}
        annualized = metadata.get("annualized")
        note_parts: list[str] = []
        if annualized is True:
            note_parts.append("annualized")
        elif annualized is False:
            note_parts.append("per period, not annualized")
        if metadata.get("confidence") is not None:
            note_parts.append(f"{float(metadata['confidence']) * 100:.0f}% confidence")
        if metadata.get("assumption"):
            note_parts.append(str(metadata["assumption"]))

        if result.unit is MetricUnit.CURRENCY:
            value, unit = format_money(result.value, currency), currency
        elif result.unit is MetricUnit.COUNT:
            value, unit = f"{int(result.value)}", "count"
        elif metric in {
            "benchmark_beta",
            "sharpe_ratio",
            "information_ratio",
            "average_pairwise_correlation",
            "benchmark_correlation",
        }:
            value, unit = format_ratio(result.value), "ratio"
        else:
            signed = metric in {
                "total_return",
                "annualized_return",
                "benchmark_alpha_annualized",
                "benchmark_annualized_return",
                "max_drawdown",
                "current_drawdown",
            }
            value, unit = format_percent(result.value, signed=signed), "percent"

        rows.append(MetricRow(label=label, value=value, unit=unit, note="; ".join(note_parts)))

    return rows


def _holdings_block(snapshot: PortfolioSnapshot, currency: str) -> TableBlock:
    """Holdings, with market value, cost, and profit or loss."""
    weights = snapshot.weights()
    rows = []

    for holding in sorted(snapshot.holdings, key=lambda item: item.symbol):
        value = holding.market_value
        profit = None if value is None else value - holding.cost_basis
        rows.append(
            [
                holding.symbol,
                f"{holding.quantity:,.8f}".rstrip("0").rstrip("."),
                format_money(holding.average_cost, currency),
                format_money(value, currency),
                format_percent(weights.get(holding.symbol)),
                format_money(profit, currency, signed=True),
            ]
        )

    return TableBlock(
        title="Positions",
        columns=["Symbol", "Quantity", "Average cost", "Market value", "Weight", "Profit / loss"],
        rows=rows,
        signed_column=5,
        empty_note="This portfolio has no holdings.",
    )


def _allocation_block(snapshot: PortfolioSnapshot) -> TableBlock:
    """Allocation by sector."""
    weights = snapshot.sector_weights()
    rows = [
        [sector, format_percent(weight)]
        for sector, weight in sorted(weights.items(), key=lambda item: -item[1])
    ]

    return TableBlock(
        title="Allocation by sector",
        columns=["Sector", "Weight"],
        rows=rows,
        empty_note="Allocation requires at least one priced holding.",
    )


def _risk_contribution_block(results: dict[str, RiskResult]) -> TableBlock:
    """Per-asset contribution to portfolio volatility."""
    result = results.get("risk_contribution")
    assets = (result.result_metadata or {}).get("assets", []) if result is not None else []

    rows = [
        [
            asset["symbol"],
            format_percent(asset["weight"]),
            format_ratio(asset["marginal_contribution"]),
            format_ratio(asset["component_contribution"]),
            format_percent(asset["share_of_risk"]),
        ]
        for asset in assets
    ]

    return TableBlock(
        title="Contribution to portfolio volatility",
        columns=["Symbol", "Weight", "Marginal", "Component", "Share of risk"],
        rows=rows,
        empty_note=(
            "Risk attribution was not available for this analysis. Component "
            "contributions sum to total portfolio volatility when it is."
        ),
    )


def _filename(portfolio_name: str, today: date) -> str:
    """A safe download filename."""
    safe = "".join(
        character if character.isalnum() or character in "-_" else "-"
        for character in portfolio_name.strip()
    ).strip("-")
    return f"heimdall-risk-report-{safe or 'portfolio'}-{today.isoformat()}.pdf"
