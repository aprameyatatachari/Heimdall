"""The nine rule evaluators.

Each one is a small, independently testable class. The message text follows the
Gjallarhorn writing style: calm, factual, specific. Every message describes an
**observed condition** and never predicts an event or recommends a trade.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from app.analytics import calculations as calc
from app.analytics.snapshot import UNKNOWN_SECTOR
from app.early_warning.evaluation import (
    OutcomeKind,
    RuleContext,
    RuleEvaluator,
    RuleOutcome,
    format_currency,
    format_percent,
)
from app.early_warning.models import AlertRule
from app.early_warning.rule_types import (
    SEVERITY_RANK,
    BaseRuleParameters,
    CorrelationIncreaseParameters,
    MissingDataParameters,
    PortfolioDrawdownParameters,
    RuleType,
    SectorConcentrationParameters,
    SeverityThresholds,
    SignalSeverity,
    StressLossParameters,
    VarThresholdParameters,
    VolatilityIncreaseParameters,
    parse_parameters,
)
from app.market_data.calendar import trading_days_between

# Suggested actions are analytical only. None of them tells anyone to trade.
ACTION_REVIEW_CONCENTRATION = "Review position concentration"
ACTION_REVIEW_SECTOR = "Review sector exposure"
ACTION_COMPARE_VOLATILITY = "Compare recent volatility with the historical baseline"
ACTION_REVIEW_DRAWDOWN = "Review the drawdown chart for this period"
ACTION_REVIEW_VAR = "Review the Value at Risk methodology and its assumptions"
ACTION_REVIEW_CORRELATION = "Review the correlation matrix"
ACTION_REVIEW_STRESS = "Inspect the stress-test breakdown"
ACTION_REFRESH_DATA = "Refresh market data"


class _Base(RuleEvaluator):
    """Shared parameter parsing."""

    def parse_parameters(self, payload: dict[str, Any]) -> BaseRuleParameters:
        """Validate the stored parameters against this rule type's schema."""
        return parse_parameters(self.rule_type, payload)


# --- Concentration ------------------------------------------------------------


class PositionConcentrationEvaluator(_Base):
    """One holding above a configured share of portfolio value."""

    rule_type = RuleType.POSITION_CONCENTRATION
    unit = "percent_of_portfolio_value"
    default_name = "Position concentration"
    default_description = (
        "Raises a signal when a single holding exceeds a configured share of total portfolio value."
    )
    default_thresholds = SeverityThresholds(elevated=0.20, high=0.30, critical=0.40)

    async def evaluate(self, *, rule: AlertRule, context: RuleContext) -> list[RuleOutcome]:
        """Check every holding's weight against the thresholds."""
        snapshot = context.snapshot
        if not snapshot.priced_holdings:
            return [RuleOutcome.skipped("No holding has a stored price, so weights are unknown.")]
        if snapshot.total_value <= 0:
            return [
                RuleOutcome.skipped("The portfolio has no market value, so weights are undefined.")
            ]

        thresholds = self.thresholds(rule)
        outcomes: list[RuleOutcome] = []

        for symbol, weight in sorted(snapshot.weights().items()):
            crossed = thresholds.highest_crossed(weight)
            if crossed is None:
                continue

            severity, threshold = crossed
            outcomes.append(
                RuleOutcome(
                    kind=OutcomeKind.TRIGGERED,
                    severity=severity,
                    observed_value=Decimal(repr(weight)),
                    threshold_value=Decimal(repr(threshold)),
                    title="High position concentration",
                    explanation=(
                        f"{symbol} represents {format_percent(weight)} of this portfolio, "
                        f"exceeding your configured {format_percent(threshold)} "
                        f"{severity}-severity threshold."
                    ),
                    suggested_action=ACTION_REVIEW_CONCENTRATION,
                    subject=symbol,
                    unit=self.unit,
                    analysis_period=f"As of {context.data_as_of or 'the latest stored prices'}",
                    context={
                        "affected_symbol": symbol,
                        "weight": weight,
                        "portfolio_value": float(snapshot.total_value),
                        "currency": snapshot.base_currency,
                        "configured_thresholds": thresholds.as_dict(),
                    },
                )
            )

        return outcomes


class SectorConcentrationEvaluator(_Base):
    """One sector above a configured share of portfolio value."""

    rule_type = RuleType.SECTOR_CONCENTRATION
    unit = "percent_of_portfolio_value"
    default_name = "Sector concentration"
    default_description = (
        "Raises a signal when one sector exceeds a configured share of total "
        "portfolio value. Does not run when too much sector metadata is missing."
    )
    default_thresholds = SeverityThresholds(elevated=0.30, high=0.40, critical=0.50)

    async def evaluate(self, *, rule: AlertRule, context: RuleContext) -> list[RuleOutcome]:
        """Check sector weights, refusing to run on incomplete sector data."""
        snapshot = context.snapshot
        parameters = self.parse_parameters(rule.parameters)
        assert isinstance(parameters, SectorConcentrationParameters)  # noqa: S101

        if not snapshot.priced_holdings or snapshot.total_value <= 0:
            return [RuleOutcome.skipped("The portfolio has no priced holdings.")]

        unknown_weight = snapshot.unknown_sector_weight
        if unknown_weight > parameters.max_unknown_sector_weight:
            return [
                RuleOutcome.skipped(
                    f"Sector information is missing for {format_percent(unknown_weight)} of "
                    "portfolio value, which is above the rule's "
                    f"{format_percent(parameters.max_unknown_sector_weight)} limit. "
                    "Presenting partial sector data as complete exposure would be "
                    "misleading, so this rule did not run."
                )
            ]

        thresholds = self.thresholds(rule)
        outcomes: list[RuleOutcome] = []

        for sector, weight in sorted(snapshot.sector_weights().items()):
            if sector == UNKNOWN_SECTOR:
                continue

            crossed = thresholds.highest_crossed(weight)
            if crossed is None:
                continue

            severity, threshold = crossed
            outcomes.append(
                RuleOutcome(
                    kind=OutcomeKind.TRIGGERED,
                    severity=severity,
                    observed_value=Decimal(repr(weight)),
                    threshold_value=Decimal(repr(threshold)),
                    title="High sector concentration",
                    explanation=(
                        f"{sector} holdings represent {format_percent(weight)} of portfolio "
                        f"value, exceeding your configured {format_percent(threshold)} "
                        f"{severity}-severity threshold."
                    ),
                    suggested_action=ACTION_REVIEW_SECTOR,
                    subject=sector,
                    unit=self.unit,
                    analysis_period=f"As of {context.data_as_of or 'the latest stored prices'}",
                    context={
                        "affected_sector": sector,
                        "weight": weight,
                        "sector_weights": snapshot.sector_weights(),
                        "unknown_sector_weight": unknown_weight,
                        "configured_thresholds": thresholds.as_dict(),
                    },
                    limitations=(
                        [
                            f"Sector information is missing for "
                            f"{format_percent(unknown_weight)} of portfolio value."
                        ]
                        if unknown_weight > 0
                        else []
                    ),
                )
            )

        return outcomes


# --- Volatility ---------------------------------------------------------------


class VolatilityIncreaseEvaluator(_Base):
    """Recent volatility elevated relative to a longer baseline."""

    rule_type = RuleType.VOLATILITY_INCREASE
    unit = "ratio_to_baseline"
    default_name = "Volatility increase"
    default_description = (
        "Compares annualized volatility over a recent window with a longer baseline "
        "window and raises a signal when the ratio exceeds a configured level."
    )
    # 1.25 means recent volatility is 25% above baseline.
    default_thresholds = SeverityThresholds(elevated=1.25, high=1.50, critical=2.00)

    async def evaluate(self, *, rule: AlertRule, context: RuleContext) -> list[RuleOutcome]:
        """Compare the two windows, requiring enough observations for both."""
        parameters = self.parse_parameters(rule.parameters)
        assert isinstance(parameters, VolatilityIncreaseParameters)  # noqa: S101

        returns = _portfolio_return_series(context)
        if returns is None:
            return [RuleOutcome.skipped("No portfolio return series could be built.")]

        series, observations = returns
        required = parameters.baseline_window_days
        if observations < required:
            return [
                RuleOutcome.skipped(
                    f"The baseline window needs {required} return observations; "
                    f"{observations} are available. Incomplete windows are not "
                    "substituted."
                )
            ]

        recent = series[-parameters.recent_window_days :]
        baseline = series[-parameters.baseline_window_days :]

        try:
            recent_volatility = calc.volatility(
                recent,
                minimum_observations=min(parameters.recent_window_days, 5),
            )
            baseline_volatility = calc.volatility(baseline)
        except calc.CalculationError as exc:
            return [RuleOutcome.skipped(str(exc))]

        if baseline_volatility <= 0:
            return [
                RuleOutcome.skipped("Baseline volatility is zero, so a ratio cannot be computed.")
            ]

        ratio = recent_volatility / baseline_volatility
        crossed = self.thresholds(rule).highest_crossed(ratio)
        if crossed is None:
            return []

        severity, threshold = crossed
        return [
            RuleOutcome(
                kind=OutcomeKind.TRIGGERED,
                severity=severity,
                observed_value=Decimal(repr(ratio)),
                threshold_value=Decimal(repr(threshold)),
                title="Elevated volatility",
                explanation=(
                    f"Annualized volatility over the last {parameters.recent_window_days} "
                    f"trading days is {format_percent(recent_volatility)}, compared with a "
                    f"{format_percent(baseline_volatility)} baseline over the previous "
                    f"{parameters.baseline_window_days} trading days. That is "
                    f"{ratio:.2f} times the baseline, above your configured "
                    f"{threshold:.2f} {severity}-severity threshold."
                ),
                suggested_action=ACTION_COMPARE_VOLATILITY,
                subject="portfolio",
                unit=self.unit,
                analysis_period=(
                    f"{parameters.recent_window_days} trading days against a "
                    f"{parameters.baseline_window_days}-day baseline"
                ),
                context={
                    "recent_volatility_annualized": recent_volatility,
                    "baseline_volatility_annualized": baseline_volatility,
                    "ratio": ratio,
                    "recent_window_days": parameters.recent_window_days,
                    "baseline_window_days": parameters.baseline_window_days,
                    "observations": observations,
                    "configured_thresholds": self.thresholds(rule).as_dict(),
                },
                limitations=[
                    "Portfolio returns are reconstructed from current weights applied to "
                    "historical asset returns."
                ],
            )
        ]


# --- Drawdown -----------------------------------------------------------------


class PortfolioDrawdownEvaluator(_Base):
    """Current decline from the running peak."""

    rule_type = RuleType.PORTFOLIO_DRAWDOWN
    unit = "percent_decline_from_peak"
    default_name = "Portfolio drawdown"
    default_description = (
        "Measures the current decline from the highest portfolio value in the lookback window."
    )
    default_thresholds = SeverityThresholds(elevated=0.05, high=0.10, critical=0.20)

    async def evaluate(self, *, rule: AlertRule, context: RuleContext) -> list[RuleOutcome]:
        """Measure the current drawdown, reported as a positive magnitude."""
        parameters = self.parse_parameters(rule.parameters)
        assert isinstance(parameters, PortfolioDrawdownParameters)  # noqa: S101

        returns = _portfolio_return_series(context)
        if returns is None:
            return [RuleOutcome.skipped("No portfolio return series could be built.")]

        series, observations = returns
        if observations < calc.MIN_OBSERVATIONS_VOLATILITY:
            return [
                RuleOutcome.skipped(
                    f"A drawdown needs at least {calc.MIN_OBSERVATIONS_VOLATILITY} return "
                    f"observations; {observations} are available."
                )
            ]

        dates = _aligned_dates(context)
        try:
            path = calc.value_history(series, starting_value=float(context.snapshot.total_value))
            drawdowns = calc.drawdown_series(path)
            worst = calc.max_drawdown(path)
        except calc.CalculationError as exc:
            return [RuleOutcome.skipped(str(exc))]

        # Reported as a positive magnitude so it compares against positive thresholds.
        current = abs(float(drawdowns[-1]))
        crossed = self.thresholds(rule).highest_crossed(current)
        if crossed is None:
            return []

        severity, threshold = crossed
        peak_date = (
            dates[worst.peak_index - 1].isoformat()
            if dates and 0 < worst.peak_index <= len(dates)
            else None
        )

        return [
            RuleOutcome(
                kind=OutcomeKind.TRIGGERED,
                severity=severity,
                observed_value=Decimal(repr(current)),
                threshold_value=Decimal(repr(threshold)),
                title="Portfolio drawdown",
                explanation=(
                    f"The portfolio is {format_percent(current)} below its highest value in "
                    f"the last {parameters.lookback_days} days, exceeding your configured "
                    f"{format_percent(threshold)} {severity}-severity threshold."
                ),
                suggested_action=ACTION_REVIEW_DRAWDOWN,
                subject="portfolio",
                unit=self.unit,
                analysis_period=f"{parameters.lookback_days} calendar days",
                context={
                    "current_drawdown": current,
                    "peak_value": worst.peak_value,
                    "current_value": float(path[-1]),
                    "peak_date": peak_date,
                    "worst_drawdown_in_window": abs(worst.drawdown),
                    "observations": observations,
                    "currency": context.snapshot.base_currency,
                    "configured_thresholds": self.thresholds(rule).as_dict(),
                },
                limitations=[
                    "The value path is reconstructed from current weights applied to "
                    "historical asset returns."
                ],
            )
        ]


# --- Value at Risk ------------------------------------------------------------


class VarThresholdEvaluator(_Base):
    """One-day historical Value at Risk above a configured limit."""

    rule_type = RuleType.VAR_THRESHOLD
    unit = "percent_of_portfolio_value"
    default_name = "Value at Risk threshold"
    default_description = (
        "Estimates one-day historical Value at Risk and raises a signal when it "
        "exceeds a configured share of portfolio value."
    )
    default_thresholds = SeverityThresholds(elevated=0.02, high=0.03, critical=0.05)

    async def evaluate(self, *, rule: AlertRule, context: RuleContext) -> list[RuleOutcome]:
        """Compute one-day VaR and compare it against the configured basis."""
        parameters = self.parse_parameters(rule.parameters)
        assert isinstance(parameters, VarThresholdParameters)  # noqa: S101

        returns = _portfolio_return_series(context)
        if returns is None:
            return [RuleOutcome.skipped("No portfolio return series could be built.")]

        series, observations = returns
        portfolio_value = float(context.snapshot.total_value)

        try:
            amount = calc.historical_var(
                series,
                confidence=parameters.confidence,
                portfolio_value=portfolio_value,
            )
        except calc.CalculationError as exc:
            return [RuleOutcome.skipped(str(exc))]

        fraction = amount / portfolio_value if portfolio_value > 0 else 0.0
        observed = amount if parameters.basis == "currency" else fraction

        crossed = self.thresholds(rule).highest_crossed(observed)
        if crossed is None:
            return []

        severity, threshold = crossed
        currency = context.snapshot.base_currency
        observed_text = (
            format_currency(observed, currency)
            if parameters.basis == "currency"
            else format_percent(observed)
        )
        threshold_text = (
            format_currency(threshold, currency)
            if parameters.basis == "currency"
            else format_percent(threshold)
        )

        return [
            RuleOutcome(
                kind=OutcomeKind.TRIGGERED,
                severity=severity,
                observed_value=Decimal(repr(observed)),
                threshold_value=Decimal(repr(threshold)),
                title="Value at Risk above threshold",
                explanation=(
                    f"One-day historical Value at Risk at "
                    f"{format_percent(parameters.confidence)} confidence is "
                    f"{observed_text}, exceeding your configured {threshold_text} "
                    f"{severity}-severity threshold. This is an estimate of a loss "
                    f"exceeded {format_percent(1 - parameters.confidence)} of the time "
                    "over one day, not a maximum possible loss."
                ),
                suggested_action=ACTION_REVIEW_VAR,
                subject="portfolio",
                unit=(
                    "currency" if parameters.basis == "currency" else "percent_of_portfolio_value"
                ),
                analysis_period=(
                    f"{observations} daily observations over the last "
                    f"{parameters.lookback_days} days"
                ),
                context={
                    "confidence": parameters.confidence,
                    "lookback_days": parameters.lookback_days,
                    "observations": observations,
                    "var_amount": amount,
                    "var_percent_of_value": fraction,
                    "portfolio_value": portfolio_value,
                    "currency": currency,
                    "method": "historical simulation",
                    "basis": parameters.basis,
                    "configured_thresholds": self.thresholds(rule).as_dict(),
                },
                limitations=[
                    "Historical simulation assumes the return distribution of the window "
                    "is representative. It is not a maximum possible loss."
                ],
            )
        ]


# --- Correlation --------------------------------------------------------------


class CorrelationIncreaseEvaluator(_Base):
    """Average pairwise correlation above a configured level."""

    rule_type = RuleType.CORRELATION_INCREASE
    unit = "correlation_coefficient"
    default_name = "Correlation increase"
    default_description = (
        "Measures the average pairwise correlation between holdings, excluding the "
        "diagonal, and raises a signal when diversification falls below a "
        "configured level."
    )
    default_thresholds = SeverityThresholds(elevated=0.65, high=0.75, critical=0.85)

    async def evaluate(self, *, rule: AlertRule, context: RuleContext) -> list[RuleOutcome]:
        """Average the off-diagonal correlations, needing at least two assets."""
        parameters = self.parse_parameters(rule.parameters)
        assert isinstance(parameters, CorrelationIncreaseParameters)  # noqa: S101

        aligned = _aligned_returns(context)
        if aligned is None:
            return [RuleOutcome.skipped("No overlapping return history could be built.")]

        if len(aligned.symbols) < 2:
            return [
                RuleOutcome.skipped(
                    "A correlation needs at least two holdings with overlapping price "
                    "history. This portfolio has one."
                )
            ]

        try:
            matrix = calc.correlation_matrix(aligned.matrix)
            average = calc.average_pairwise_correlation(matrix)
        except calc.CalculationError as exc:
            return [RuleOutcome.skipped(str(exc))]

        crossed = self.thresholds(rule).highest_crossed(average)
        if crossed is None:
            return []

        severity, threshold = crossed
        return [
            RuleOutcome(
                kind=OutcomeKind.TRIGGERED,
                severity=severity,
                observed_value=Decimal(repr(average)),
                threshold_value=Decimal(repr(threshold)),
                title="Reduced diversification",
                explanation=(
                    f"Average pairwise correlation between holdings is {average:.2f} over "
                    f"{aligned.observation_count} trading days, above your configured "
                    f"{threshold:.2f} {severity}-severity threshold. Holdings that move "
                    "together provide less diversification than holdings that do not."
                ),
                suggested_action=ACTION_REVIEW_CORRELATION,
                subject="portfolio",
                unit=self.unit,
                analysis_period=(
                    f"{aligned.observation_count} daily observations over the last "
                    f"{parameters.lookback_days} days"
                ),
                context={
                    "average_pairwise_correlation": average,
                    "symbols": aligned.symbols,
                    "observations": aligned.observation_count,
                    "excludes_diagonal": True,
                    "configured_thresholds": self.thresholds(rule).as_dict(),
                },
            )
        ]


# --- Stress loss --------------------------------------------------------------


class StressLossEvaluator(_Base):
    """Estimated loss under a stored stress scenario above a configured level."""

    rule_type = RuleType.STRESS_LOSS
    unit = "percent_of_portfolio_value"
    default_name = "Stress-test loss"
    default_description = (
        "Runs selected stored stress scenarios and raises a signal when the estimated "
        "loss exceeds a configured share of portfolio value."
    )
    default_thresholds = SeverityThresholds(elevated=0.10, high=0.15, critical=0.25)

    async def evaluate(self, *, rule: AlertRule, context: RuleContext) -> list[RuleOutcome]:
        """Evaluate each configured scenario, naming the one that triggered."""
        parameters = self.parse_parameters(rule.parameters)
        assert isinstance(parameters, StressLossParameters)  # noqa: S101

        if context.scenario_runner is None:
            return [RuleOutcome.skipped("Stress scenarios are not available in this run.")]

        thresholds = self.thresholds(rule)
        outcomes: list[RuleOutcome] = []
        unavailable: list[str] = []

        for key in parameters.scenario_keys:
            try:
                loss_fraction, loss_amount, scenario_name = await context.scenario_runner(key)
            except Exception as exc:
                unavailable.append(f"{key}: {exc}")
                continue

            magnitude = abs(float(loss_fraction))
            crossed = thresholds.highest_crossed(magnitude)
            if crossed is None:
                continue

            severity, threshold = crossed
            amount_text = format_currency(abs(float(loss_amount)), context.snapshot.base_currency)
            outcomes.append(
                RuleOutcome(
                    kind=OutcomeKind.TRIGGERED,
                    severity=severity,
                    observed_value=Decimal(repr(magnitude)),
                    threshold_value=Decimal(repr(threshold)),
                    title="Large estimated stress loss",
                    explanation=(
                        f"Under the {scenario_name} scenario the estimated portfolio loss is "
                        f"{format_percent(magnitude)} ({amount_text}), exceeding your "
                        f"configured {format_percent(threshold)} {severity}-severity "
                        "threshold. This is a sensitivity estimate, not a forecast."
                    ),
                    suggested_action=ACTION_REVIEW_STRESS,
                    subject=key,
                    unit=self.unit,
                    analysis_period=f"Scenario {key}",
                    context={
                        "affected_scenario": key,
                        "scenario_name": scenario_name,
                        "estimated_loss_percent": magnitude,
                        "estimated_loss_amount": abs(float(loss_amount)),
                        "currency": context.snapshot.base_currency,
                        "configured_thresholds": thresholds.as_dict(),
                    },
                    limitations=[
                        "A stress test applies price changes to current holdings. It is an "
                        "estimate of sensitivity, not a forecast."
                    ],
                )
            )

        if not outcomes and unavailable and len(unavailable) == len(parameters.scenario_keys):
            return [
                RuleOutcome.skipped(
                    "No configured scenario could be evaluated: " + "; ".join(unavailable)
                )
            ]

        return outcomes


# --- Data quality -------------------------------------------------------------


class StaleMarketDataEvaluator(_Base):
    """Prices older than a configured number of expected trading days."""

    rule_type = RuleType.STALE_MARKET_DATA
    unit = "expected_trading_days"
    default_name = "Stale market data"
    default_description = (
        "Raises a signal when a holding's newest stored price is older than a "
        "configured number of expected trading days. Weekends are never counted as "
        "stale under Heimdall's weekday trading-calendar convention."
    )
    default_thresholds = SeverityThresholds(elevated=1, high=2, critical=5)
    default_cooldown_hours = 12

    async def evaluate(self, *, rule: AlertRule, context: RuleContext) -> list[RuleOutcome]:
        """Measure staleness per holding in expected trading days."""
        self.parse_parameters(rule.parameters)
        snapshot = context.snapshot

        if not snapshot.holdings:
            return [RuleOutcome.skipped("The portfolio has no holdings.")]

        today = context.evaluated_at.date()
        thresholds = self.thresholds(rule)
        outcomes: list[RuleOutcome] = []

        for holding in snapshot.holdings:
            if holding.latest_price_date is None:
                # Absent data is the missing-data rule's business, not staleness.
                continue

            age = trading_days_between(holding.latest_price_date, today)
            crossed = thresholds.highest_crossed(float(age))
            if crossed is None:
                continue

            severity, threshold = crossed
            outcomes.append(
                RuleOutcome(
                    kind=OutcomeKind.TRIGGERED,
                    severity=severity,
                    observed_value=Decimal(age),
                    threshold_value=Decimal(repr(threshold)),
                    title="Stale market data",
                    explanation=(
                        f"{holding.symbol} has not received a new closing price for "
                        f"{age} expected trading days; its newest stored price is from "
                        f"{holding.latest_price_date.isoformat()}. That is above your "
                        f"configured {threshold:g}-day {severity}-severity threshold. "
                        "Current risk estimates for this holding may be incomplete."
                    ),
                    suggested_action=ACTION_REFRESH_DATA,
                    subject=holding.symbol,
                    unit=self.unit,
                    analysis_period=f"Measured against {today.isoformat()}",
                    context={
                        "affected_symbol": holding.symbol,
                        "latest_price_date": holding.latest_price_date.isoformat(),
                        "expected_trading_days_stale": age,
                        "evaluated_against": today.isoformat(),
                        "calendar_convention": (
                            "Monday to Friday are expected trading days. Exchange holidays "
                            "are not modelled."
                        ),
                        "configured_thresholds": thresholds.as_dict(),
                    },
                    limitations=[
                        "Every metric that depends on this holding's price may be affected."
                    ],
                )
            )

        return outcomes


class MissingDataEvaluator(_Base):
    """Gaps that prevent reliable analysis."""

    rule_type = RuleType.MISSING_DATA
    unit = "count"
    default_name = "Missing data"
    default_description = (
        "Raises a signal when holdings have no stored prices, no sector metadata, or "
        "too little history for dependable risk measures."
    )
    default_thresholds = SeverityThresholds(elevated=1, high=3, critical=5)
    default_cooldown_hours = 12

    async def evaluate(self, *, rule: AlertRule, context: RuleContext) -> list[RuleOutcome]:
        """Report distinct kinds of data gap as separate conditions."""
        parameters = self.parse_parameters(rule.parameters)
        assert isinstance(parameters, MissingDataParameters)  # noqa: S101

        snapshot = context.snapshot
        if not snapshot.holdings:
            return [RuleOutcome.skipped("The portfolio has no holdings.")]

        thresholds = self.thresholds(rule)
        outcomes: list[RuleOutcome] = []

        unpriced = snapshot.unpriced_symbols
        if unpriced:
            crossed = thresholds.highest_crossed(float(len(unpriced)))
            severity, threshold = crossed or (SignalSeverity.INFORMATIONAL, 1.0)
            outcomes.append(
                RuleOutcome(
                    kind=OutcomeKind.TRIGGERED,
                    severity=severity,
                    observed_value=Decimal(len(unpriced)),
                    threshold_value=Decimal(repr(threshold)),
                    title="Missing market data",
                    explanation=(
                        f"{len(unpriced)} holding(s) have no stored price: "
                        f"{', '.join(unpriced)}. They are excluded from portfolio value, "
                        "weights, volatility, Value at Risk, and every stress test."
                    ),
                    suggested_action=ACTION_REFRESH_DATA,
                    subject="unpriced_holdings",
                    unit=self.unit,
                    analysis_period=f"As of {context.data_as_of or 'no stored data'}",
                    context={
                        "affected_symbols": unpriced,
                        "count": len(unpriced),
                        "affected_calculations": [
                            "portfolio value",
                            "weights",
                            "volatility",
                            "Value at Risk",
                            "stress tests",
                        ],
                        "configured_thresholds": thresholds.as_dict(),
                    },
                )
            )

        missing_sector = [
            holding.symbol for holding in snapshot.holdings if holding.sector == UNKNOWN_SECTOR
        ]
        if missing_sector:
            crossed = thresholds.highest_crossed(float(len(missing_sector)))
            severity, threshold = crossed or (SignalSeverity.INFORMATIONAL, 1.0)
            outcomes.append(
                RuleOutcome(
                    kind=OutcomeKind.TRIGGERED,
                    # Missing sector metadata is a data-quality gap, never critical.
                    severity=_cap(severity, SignalSeverity.HIGH),
                    observed_value=Decimal(len(missing_sector)),
                    threshold_value=Decimal(repr(threshold)),
                    title="Missing sector information",
                    explanation=(
                        f"{len(missing_sector)} holding(s) have no sector information: "
                        f"{', '.join(missing_sector)}. Sector exposure is therefore "
                        "incomplete, and the sector-concentration rule may not run."
                    ),
                    suggested_action=ACTION_REFRESH_DATA,
                    subject="missing_sector_metadata",
                    unit=self.unit,
                    analysis_period=f"As of {context.data_as_of or 'no stored data'}",
                    context={
                        "affected_symbols": missing_sector,
                        "count": len(missing_sector),
                        "affected_calculations": ["sector exposure", "sector concentration"],
                        "configured_thresholds": thresholds.as_dict(),
                    },
                )
            )

        aligned = _aligned_returns(context)
        observations = aligned.observation_count if aligned is not None else 0
        if snapshot.priced_holdings and observations < parameters.minimum_observations:
            outcomes.append(
                RuleOutcome(
                    kind=OutcomeKind.TRIGGERED,
                    severity=SignalSeverity.ELEVATED,
                    observed_value=Decimal(observations),
                    threshold_value=Decimal(parameters.minimum_observations),
                    title="Insufficient price history",
                    explanation=(
                        f"Only {observations} overlapping daily observations are stored for "
                        f"this portfolio's holdings, below the {parameters.minimum_observations} "
                        "needed for dependable volatility, Value at Risk, and correlation "
                        "estimates. Those measures are reported as unavailable rather than "
                        "estimated from too little data."
                    ),
                    suggested_action=ACTION_REFRESH_DATA,
                    subject="insufficient_history",
                    unit=self.unit,
                    analysis_period=f"Last {parameters.lookback_days} days",
                    context={
                        "observations": observations,
                        "minimum_observations": parameters.minimum_observations,
                        "lookback_days": parameters.lookback_days,
                        "affected_calculations": [
                            "volatility",
                            "Sharpe ratio",
                            "Value at Risk",
                            "Expected Shortfall",
                            "correlation",
                            "risk contribution",
                        ],
                    },
                )
            )

        return outcomes


# --- Shared helpers -----------------------------------------------------------


def _cap(severity: SignalSeverity, ceiling: SignalSeverity) -> SignalSeverity:
    """Limit a severity to a ceiling."""
    return severity if SEVERITY_RANK[severity] <= SEVERITY_RANK[ceiling] else ceiling


def _aligned_returns(context: RuleContext) -> calc.AlignedReturns | None:
    """Align the portfolio's loaded price history into a return matrix."""
    series = {
        symbol: item.observations
        for symbol, item in context.history.items()
        if len(item.observations) >= 2
    }
    if not series:
        return None

    try:
        return calc.align_price_series(series)
    except calc.CalculationError:
        return None


def _portfolio_return_series(context: RuleContext) -> tuple[list[float], int] | None:
    """Build the fixed-weight portfolio return series from loaded history."""
    aligned = _aligned_returns(context)
    if aligned is None:
        return None

    weights_by_symbol = context.snapshot.weights()
    raw = [weights_by_symbol.get(symbol, 0.0) for symbol in aligned.symbols]

    try:
        weights = calc.normalize_weights(raw)
        series = calc.portfolio_returns(weights, aligned.matrix)
    except calc.CalculationError:
        return None

    return list(series), aligned.observation_count


def _aligned_dates(context: RuleContext) -> list[Any]:
    """Dates of the aligned return series, for reporting peaks and troughs."""
    aligned = _aligned_returns(context)
    return list(aligned.dates) if aligned is not None else []


EVALUATORS: dict[RuleType, RuleEvaluator] = {
    RuleType.POSITION_CONCENTRATION: PositionConcentrationEvaluator(),
    RuleType.SECTOR_CONCENTRATION: SectorConcentrationEvaluator(),
    RuleType.VOLATILITY_INCREASE: VolatilityIncreaseEvaluator(),
    RuleType.PORTFOLIO_DRAWDOWN: PortfolioDrawdownEvaluator(),
    RuleType.VAR_THRESHOLD: VarThresholdEvaluator(),
    RuleType.CORRELATION_INCREASE: CorrelationIncreaseEvaluator(),
    RuleType.STRESS_LOSS: StressLossEvaluator(),
    RuleType.STALE_MARKET_DATA: StaleMarketDataEvaluator(),
    RuleType.MISSING_DATA: MissingDataEvaluator(),
}


def get_evaluator(rule_type: RuleType | str) -> RuleEvaluator:
    """Look up the evaluator for a rule type."""
    resolved = RuleType(rule_type)
    return EVALUATORS[resolved]


__all__ = [
    "EVALUATORS",
    "CorrelationIncreaseEvaluator",
    "MissingDataEvaluator",
    "PortfolioDrawdownEvaluator",
    "PositionConcentrationEvaluator",
    "SectorConcentrationEvaluator",
    "StaleMarketDataEvaluator",
    "StressLossEvaluator",
    "VarThresholdEvaluator",
    "VolatilityIncreaseEvaluator",
    "get_evaluator",
]
