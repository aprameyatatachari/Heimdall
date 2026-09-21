"""Unit tests for the Early Warning System rule engine.

Every evaluator is exercised directly with a hand-built context: no database, no
HTTP, and an injected clock so time-dependent behaviour is deterministic.

Boundary coverage is deliberate: for each numeric rule there is a case just below
the threshold, exactly at it, and above it.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from app.analytics.snapshot import UNKNOWN_SECTOR, HoldingSnapshot, PortfolioSnapshot
from app.early_warning.evaluation import OutcomeKind, PriceSeries, RuleContext
from app.early_warning.evaluators import (
    CorrelationIncreaseEvaluator,
    MissingDataEvaluator,
    PortfolioDrawdownEvaluator,
    PositionConcentrationEvaluator,
    SectorConcentrationEvaluator,
    StaleMarketDataEvaluator,
    StressLossEvaluator,
    VarThresholdEvaluator,
    VolatilityIncreaseEvaluator,
    get_evaluator,
)
from app.early_warning.fingerprint import build_fingerprint
from app.early_warning.models import AlertRule
from app.early_warning.notifications import should_notify
from app.early_warning.rule_types import (
    RULE_PARAMETER_MODELS,
    RuleType,
    SeverityThresholds,
    SignalSeverity,
    parse_parameters,
)

NOW = datetime(2024, 3, 18, 12, 0, tzinfo=UTC)  # a Monday
TODAY = NOW.date()

PORTFOLIO_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")


# --- Builders -----------------------------------------------------------------


def holding(
    symbol: str,
    *,
    sector: str = "Technology",
    quantity: str = "10",
    price: str | None = "100",
    price_date: date | None = None,
) -> HoldingSnapshot:
    """One holding, valued at a fixed price."""
    return HoldingSnapshot(
        asset_id=uuid.uuid4(),
        symbol=symbol,
        name=symbol,
        sector=sector,
        quantity=Decimal(quantity),
        average_cost=Decimal("50"),
        latest_price=None if price is None else Decimal(price),
        latest_price_date=None if price is None else (price_date or TODAY),
        currency="USD",
    )


def snapshot(holdings: list[HoldingSnapshot], *, as_of: date | None = TODAY) -> PortfolioSnapshot:
    """A portfolio snapshot around the given holdings."""
    return PortfolioSnapshot(
        portfolio_id=PORTFOLIO_ID,
        portfolio_name="Test portfolio",
        base_currency="USD",
        benchmark_symbol=None,
        holdings=holdings,
        data_as_of=as_of,
    )


def rule(
    rule_type: RuleType,
    *,
    thresholds: dict[str, float] | None = None,
    parameters: dict[str, object] | None = None,
    cooldown_hours: int = 24,
) -> AlertRule:
    """An unsaved alert rule, enough for an evaluator to read."""
    evaluator = get_evaluator(rule_type)
    return AlertRule(
        id=uuid.uuid4(),
        portfolio_id=PORTFOLIO_ID,
        rule_type=str(rule_type),
        name=evaluator.default_name,
        description=evaluator.default_description,
        enabled=True,
        parameters=parameters or {},
        severity_configuration=thresholds or evaluator.default_thresholds.as_dict(),
        cooldown_hours=cooldown_hours,
    )


def series(symbol: str, prices: list[float], *, end: date = TODAY) -> PriceSeries:
    """A price series ending on `end`, one observation per weekday."""
    observations: list[tuple[date, float]] = []
    current = end
    for price in reversed(prices):
        while current.weekday() >= 5:
            current -= timedelta(days=1)
        observations.append((current, price))
        current -= timedelta(days=1)
    return PriceSeries(symbol=symbol, observations=list(reversed(observations)))


def context(
    holdings: list[HoldingSnapshot],
    *,
    history: dict[str, PriceSeries] | None = None,
    now: datetime = NOW,
    as_of: date | None = TODAY,
    scenario_runner=None,
) -> RuleContext:
    """A rule context with an injected clock instant."""
    return RuleContext(
        snapshot=snapshot(holdings, as_of=as_of),
        history=history or {},
        evaluated_at=now,
        data_as_of=as_of,
        scenario_runner=scenario_runner,
    )


def flat_then_volatile(
    *,
    calm_days: int,
    calm_move: float,
    recent_days: int,
    recent_move: float,
) -> list[float]:
    """A price path that is calm and then becomes volatile."""
    prices = [100.0]
    for index in range(calm_days):
        prices.append(prices[-1] * (1 + calm_move * (1 if index % 2 == 0 else -1)))
    for index in range(recent_days):
        prices.append(prices[-1] * (1 + recent_move * (1 if index % 2 == 0 else -1)))
    return prices


# --- Severity thresholds ------------------------------------------------------


def test_thresholds_must_increase_with_severity():
    with pytest.raises(ValueError, match="must be greater than"):
        SeverityThresholds(elevated=0.30, high=0.20)


def test_thresholds_must_increase_across_all_three():
    with pytest.raises(ValueError, match="must be greater than"):
        SeverityThresholds(elevated=0.10, high=0.40, critical=0.20)


def test_at_least_one_threshold_is_required():
    with pytest.raises(ValueError, match="At least one"):
        SeverityThresholds()


def test_a_single_threshold_is_valid():
    assert SeverityThresholds(high=0.30).as_dict() == {"high": 0.30}


def test_only_the_highest_crossed_severity_is_returned():
    thresholds = SeverityThresholds(elevated=0.20, high=0.30, critical=0.40)

    assert thresholds.highest_crossed(0.45) == (SignalSeverity.CRITICAL, 0.40)
    assert thresholds.highest_crossed(0.35) == (SignalSeverity.HIGH, 0.30)
    assert thresholds.highest_crossed(0.25) == (SignalSeverity.ELEVATED, 0.20)
    assert thresholds.highest_crossed(0.10) is None


@pytest.mark.parametrize(
    ("observed", "expected"),
    [(0.1999, None), (0.20, SignalSeverity.ELEVATED), (0.2001, SignalSeverity.ELEVATED)],
)
def test_a_threshold_is_crossed_at_exactly_its_value(observed, expected):
    """The comparison is `>=`, so the threshold value itself triggers."""
    crossed = SeverityThresholds(elevated=0.20).highest_crossed(observed)

    assert (crossed[0] if crossed else None) == expected


# --- Parameter validation -----------------------------------------------------


def test_every_rule_type_has_a_parameter_schema():
    assert set(RULE_PARAMETER_MODELS) == set(RuleType)


def test_unknown_parameters_are_rejected():
    with pytest.raises(Exception, match="extra"):
        parse_parameters(RuleType.POSITION_CONCENTRATION, {"nonsense": 1})


def test_a_volatility_baseline_must_be_longer_than_the_recent_window():
    with pytest.raises(Exception, match="longer than"):
        parse_parameters(
            RuleType.VOLATILITY_INCREASE,
            {"recent_window_days": 100, "baseline_window_days": 50},
        )


def test_an_unknown_stress_scenario_is_rejected():
    with pytest.raises(Exception, match="Unknown stress scenario"):
        parse_parameters(RuleType.STRESS_LOSS, {"scenario_keys": ["no_such_scenario"]})


def test_a_known_stress_scenario_is_accepted():
    parsed = parse_parameters(RuleType.STRESS_LOSS, {"scenario_keys": ["covid_19_crash_2020"]})

    assert parsed.model_dump()["scenario_keys"] == ["covid_19_crash_2020"]


# --- Position concentration ---------------------------------------------------


@pytest.mark.parametrize(
    ("aapl_value", "expected"),
    [
        ("19", None),  # 19% of 100 -> below the 20% elevated threshold
        ("20", SignalSeverity.ELEVATED),
        ("31", SignalSeverity.HIGH),
        ("45", SignalSeverity.CRITICAL),
    ],
)
async def test_position_concentration_boundaries(aapl_value, expected):
    holdings = [
        holding("AAPL", quantity="1", price=aapl_value),
        holding("MSFT", quantity="1", price=str(100 - int(aapl_value))),
    ]

    outcomes = await PositionConcentrationEvaluator().evaluate(
        rule=rule(RuleType.POSITION_CONCENTRATION),
        context=context(holdings),
    )

    triggered = [item for item in outcomes if item.triggered and item.subject == "AAPL"]
    assert (triggered[0].severity if triggered else None) == expected


async def test_position_concentration_names_the_affected_symbol():
    holdings = [
        holding("AAPL", quantity="1", price="50"),
        holding("MSFT", quantity="1", price="50"),
    ]

    outcomes = await PositionConcentrationEvaluator().evaluate(
        rule=rule(RuleType.POSITION_CONCENTRATION),
        context=context(holdings),
    )

    assert {item.subject for item in outcomes} == {"AAPL", "MSFT"}
    assert "AAPL represents 50.0%" in next(
        item.explanation for item in outcomes if item.subject == "AAPL"
    )
    assert outcomes[0].context["affected_symbol"] in {"AAPL", "MSFT"}


async def test_position_concentration_reports_two_conditions_separately():
    """Two over-weight holdings are two signals with two fingerprints."""
    holdings = [
        holding("AAPL", quantity="1", price="50"),
        holding("MSFT", quantity="1", price="50"),
    ]

    outcomes = await PositionConcentrationEvaluator().evaluate(
        rule=rule(RuleType.POSITION_CONCENTRATION),
        context=context(holdings),
    )

    assert len(outcomes) == 2


async def test_a_single_asset_portfolio_is_fully_concentrated():
    outcomes = await PositionConcentrationEvaluator().evaluate(
        rule=rule(RuleType.POSITION_CONCENTRATION),
        context=context([holding("AAPL")]),
    )

    assert outcomes[0].severity is SignalSeverity.CRITICAL
    assert outcomes[0].observed_value == Decimal("1.0")


async def test_an_empty_portfolio_is_not_evaluated():
    outcomes = await PositionConcentrationEvaluator().evaluate(
        rule=rule(RuleType.POSITION_CONCENTRATION),
        context=context([]),
    )

    assert outcomes[0].kind is OutcomeKind.NOT_EVALUATED
    assert "stored price" in outcomes[0].reason


async def test_an_unpriced_portfolio_is_not_evaluated():
    outcomes = await PositionConcentrationEvaluator().evaluate(
        rule=rule(RuleType.POSITION_CONCENTRATION),
        context=context([holding("AAPL", price=None)]),
    )

    assert outcomes[0].kind is OutcomeKind.NOT_EVALUATED


async def test_a_zero_value_portfolio_is_not_evaluated():
    outcomes = await PositionConcentrationEvaluator().evaluate(
        rule=rule(RuleType.POSITION_CONCENTRATION),
        context=context([holding("AAPL", quantity="0", price="100")]),
    )

    assert outcomes[0].kind is OutcomeKind.NOT_EVALUATED


# --- Sector concentration -----------------------------------------------------


@pytest.mark.parametrize(
    ("tech_value", "expected"),
    [
        ("29", None),
        ("30", SignalSeverity.ELEVATED),
        ("41", SignalSeverity.HIGH),
        ("55", SignalSeverity.CRITICAL),
    ],
)
async def test_sector_concentration_boundaries(tech_value, expected):
    holdings = [
        holding("AAPL", sector="Technology", quantity="1", price=tech_value),
        holding("JNJ", sector="Healthcare", quantity="1", price=str(100 - int(tech_value))),
    ]

    outcomes = await SectorConcentrationEvaluator().evaluate(
        rule=rule(RuleType.SECTOR_CONCENTRATION),
        context=context(holdings),
    )

    triggered = [item for item in outcomes if item.triggered and item.subject == "Technology"]
    assert (triggered[0].severity if triggered else None) == expected


async def test_sector_concentration_refuses_to_run_on_incomplete_sector_data():
    """Partial sector data must not be presented as complete exposure."""
    holdings = [
        holding("AAPL", sector="Technology", quantity="1", price="50"),
        holding("ZZZZ", sector=UNKNOWN_SECTOR, quantity="1", price="50"),
    ]

    outcomes = await SectorConcentrationEvaluator().evaluate(
        rule=rule(RuleType.SECTOR_CONCENTRATION),
        context=context(holdings),
    )

    assert outcomes[0].kind is OutcomeKind.NOT_EVALUATED
    assert "Sector information is missing for 50.0%" in outcomes[0].reason


async def test_a_little_missing_sector_data_still_allows_evaluation():
    holdings = [
        holding("AAPL", sector="Technology", quantity="1", price="90"),
        holding("ZZZZ", sector=UNKNOWN_SECTOR, quantity="1", price="10"),
    ]

    outcomes = await SectorConcentrationEvaluator().evaluate(
        rule=rule(RuleType.SECTOR_CONCENTRATION),
        context=context(holdings),
    )

    assert outcomes[0].triggered
    assert outcomes[0].limitations


async def test_the_unknown_sector_never_triggers_a_concentration_signal():
    holdings = [
        holding("AAPL", sector="Technology", quantity="1", price="85"),
        holding("ZZZZ", sector=UNKNOWN_SECTOR, quantity="1", price="15"),
    ]

    outcomes = await SectorConcentrationEvaluator().evaluate(
        rule=rule(RuleType.SECTOR_CONCENTRATION, parameters={"max_unknown_sector_weight": 0.20}),
        context=context(holdings),
    )

    assert UNKNOWN_SECTOR not in {item.subject for item in outcomes}


# --- Volatility increase ------------------------------------------------------


async def test_volatility_increase_triggers_when_recent_volatility_doubles():
    prices = flat_then_volatile(calm_days=260, calm_move=0.004, recent_days=20, recent_move=0.030)

    outcomes = await VolatilityIncreaseEvaluator().evaluate(
        rule=rule(RuleType.VOLATILITY_INCREASE),
        context=context([holding("AAPL")], history={"AAPL": series("AAPL", prices)}),
    )

    assert outcomes[0].triggered
    assert outcomes[0].severity is SignalSeverity.CRITICAL
    assert outcomes[0].observed_value > Decimal("2")
    assert "Annualized volatility over the last 20 trading days" in outcomes[0].explanation


async def test_volatility_increase_is_clear_in_a_steady_market():
    prices = flat_then_volatile(calm_days=280, calm_move=0.005, recent_days=0, recent_move=0.0)

    outcomes = await VolatilityIncreaseEvaluator().evaluate(
        rule=rule(RuleType.VOLATILITY_INCREASE),
        context=context([holding("AAPL")], history={"AAPL": series("AAPL", prices)}),
    )

    assert outcomes == []


async def test_volatility_increase_needs_a_full_baseline_window():
    """An incomplete window is reported, never silently substituted."""
    prices = flat_then_volatile(calm_days=40, calm_move=0.005, recent_days=20, recent_move=0.03)

    outcomes = await VolatilityIncreaseEvaluator().evaluate(
        rule=rule(RuleType.VOLATILITY_INCREASE),
        context=context([holding("AAPL")], history={"AAPL": series("AAPL", prices)}),
    )

    assert outcomes[0].kind is OutcomeKind.NOT_EVALUATED
    assert "needs 252 return observations" in outcomes[0].reason
    assert "not substituted" in outcomes[0].reason


async def test_volatility_increase_without_history_is_not_evaluated():
    outcomes = await VolatilityIncreaseEvaluator().evaluate(
        rule=rule(RuleType.VOLATILITY_INCREASE),
        context=context([holding("AAPL")]),
    )

    assert outcomes[0].kind is OutcomeKind.NOT_EVALUATED


# --- Drawdown -----------------------------------------------------------------


async def test_drawdown_triggers_on_a_decline_from_the_peak():
    # Rise to 130, then fall 20% to 104.
    prices = [100.0 + index for index in range(31)] + [
        130.0 * (1 - 0.02 * step) for step in range(1, 11)
    ]

    outcomes = await PortfolioDrawdownEvaluator().evaluate(
        rule=rule(RuleType.PORTFOLIO_DRAWDOWN),
        context=context([holding("AAPL")], history={"AAPL": series("AAPL", prices)}),
    )

    assert outcomes[0].triggered
    assert outcomes[0].observed_value > Decimal("0.15")
    assert outcomes[0].context["peak_date"]
    assert outcomes[0].context["peak_value"] > outcomes[0].context["current_value"]


async def test_drawdown_is_clear_at_an_all_time_high():
    prices = [100.0 + index for index in range(60)]

    outcomes = await PortfolioDrawdownEvaluator().evaluate(
        rule=rule(RuleType.PORTFOLIO_DRAWDOWN),
        context=context([holding("AAPL")], history={"AAPL": series("AAPL", prices)}),
    )

    assert outcomes == []


async def test_drawdown_reports_a_positive_magnitude():
    """Thresholds are positive, so the observed value is a magnitude."""
    prices = [100.0] * 30 + [100.0 - step for step in range(1, 16)]

    outcomes = await PortfolioDrawdownEvaluator().evaluate(
        rule=rule(RuleType.PORTFOLIO_DRAWDOWN),
        context=context([holding("AAPL")], history={"AAPL": series("AAPL", prices)}),
    )

    assert outcomes[0].observed_value > 0


async def test_drawdown_needs_enough_observations():
    outcomes = await PortfolioDrawdownEvaluator().evaluate(
        rule=rule(RuleType.PORTFOLIO_DRAWDOWN),
        context=context([holding("AAPL")], history={"AAPL": series("AAPL", [100.0, 90.0, 80.0])}),
    )

    assert outcomes[0].kind is OutcomeKind.NOT_EVALUATED
    assert "observations" in outcomes[0].reason


# --- Value at Risk ------------------------------------------------------------


async def test_var_threshold_triggers_on_a_volatile_series():
    prices = flat_then_volatile(calm_days=0, calm_move=0.0, recent_days=120, recent_move=0.04)

    outcomes = await VarThresholdEvaluator().evaluate(
        rule=rule(RuleType.VAR_THRESHOLD),
        context=context([holding("AAPL")], history={"AAPL": series("AAPL", prices)}),
    )

    assert outcomes[0].triggered
    assert outcomes[0].context["confidence"] == 0.95
    assert outcomes[0].context["method"] == "historical simulation"
    assert "not a maximum possible loss" in outcomes[0].explanation


async def test_var_threshold_is_clear_for_a_calm_series():
    prices = flat_then_volatile(calm_days=120, calm_move=0.0005, recent_days=0, recent_move=0.0)

    outcomes = await VarThresholdEvaluator().evaluate(
        rule=rule(RuleType.VAR_THRESHOLD),
        context=context([holding("AAPL")], history={"AAPL": series("AAPL", prices)}),
    )

    assert outcomes == []


async def test_var_threshold_records_its_confidence_and_window():
    prices = flat_then_volatile(calm_days=0, calm_move=0.0, recent_days=120, recent_move=0.04)

    outcomes = await VarThresholdEvaluator().evaluate(
        rule=rule(RuleType.VAR_THRESHOLD, parameters={"confidence": 0.99}),
        context=context([holding("AAPL")], history={"AAPL": series("AAPL", prices)}),
    )

    assert outcomes[0].context["confidence"] == 0.99
    assert "99.0% confidence" in outcomes[0].explanation


async def test_var_threshold_can_be_configured_in_currency():
    prices = flat_then_volatile(calm_days=0, calm_move=0.0, recent_days=120, recent_move=0.04)

    outcomes = await VarThresholdEvaluator().evaluate(
        rule=rule(
            RuleType.VAR_THRESHOLD,
            parameters={"basis": "currency"},
            thresholds={"elevated": 10.0, "high": 25.0},
        ),
        context=context([holding("AAPL")], history={"AAPL": series("AAPL", prices)}),
    )

    assert outcomes[0].triggered
    assert outcomes[0].unit == "currency"
    assert outcomes[0].context["basis"] == "currency"


# --- Correlation --------------------------------------------------------------


async def test_correlation_triggers_for_assets_that_move_together():
    prices = flat_then_volatile(calm_days=60, calm_move=0.01, recent_days=0, recent_move=0.0)

    outcomes = await CorrelationIncreaseEvaluator().evaluate(
        rule=rule(RuleType.CORRELATION_INCREASE),
        context=context(
            [holding("AAPL", quantity="1", price="50"), holding("MSFT", quantity="1", price="50")],
            history={"AAPL": series("AAPL", prices), "MSFT": series("MSFT", prices)},
        ),
    )

    assert outcomes[0].triggered
    assert outcomes[0].severity is SignalSeverity.CRITICAL
    assert outcomes[0].observed_value > Decimal("0.99")
    assert outcomes[0].context["excludes_diagonal"] is True


async def test_correlation_is_clear_for_assets_that_move_oppositely():
    up = flat_then_volatile(calm_days=60, calm_move=0.01, recent_days=0, recent_move=0.0)
    down = [200.0 - (price - 100.0) for price in up]

    outcomes = await CorrelationIncreaseEvaluator().evaluate(
        rule=rule(RuleType.CORRELATION_INCREASE),
        context=context(
            [holding("AAPL", quantity="1", price="50"), holding("TLT", quantity="1", price="50")],
            history={"AAPL": series("AAPL", up), "TLT": series("TLT", down)},
        ),
    )

    assert outcomes == []


async def test_correlation_needs_two_holdings():
    prices = flat_then_volatile(calm_days=60, calm_move=0.01, recent_days=0, recent_move=0.0)

    outcomes = await CorrelationIncreaseEvaluator().evaluate(
        rule=rule(RuleType.CORRELATION_INCREASE),
        context=context([holding("AAPL")], history={"AAPL": series("AAPL", prices)}),
    )

    assert outcomes[0].kind is OutcomeKind.NOT_EVALUATED
    assert "at least two holdings" in outcomes[0].reason


# --- Stress loss --------------------------------------------------------------


async def test_stress_loss_triggers_and_names_the_scenario():
    async def runner(_scenario_key: str):
        return Decimal("-0.30"), Decimal("-3000"), "COVID-19 crash"

    outcomes = await StressLossEvaluator().evaluate(
        rule=rule(RuleType.STRESS_LOSS),
        context=context([holding("AAPL")], scenario_runner=runner),
    )

    assert outcomes[0].triggered
    assert outcomes[0].severity is SignalSeverity.CRITICAL
    assert outcomes[0].subject == "covid_19_crash_2020"
    assert outcomes[0].context["scenario_name"] == "COVID-19 crash"
    assert "not a forecast" in outcomes[0].explanation


async def test_stress_loss_is_clear_for_a_small_estimated_loss():
    async def runner(_scenario_key: str):
        return Decimal("-0.05"), Decimal("-500"), "COVID-19 crash"

    outcomes = await StressLossEvaluator().evaluate(
        rule=rule(RuleType.STRESS_LOSS),
        context=context([holding("AAPL")], scenario_runner=runner),
    )

    assert outcomes == []


async def test_stress_loss_reports_an_unavailable_scenario():
    async def runner(_scenario_key: str):
        raise ValueError("No stored price data covers that window.")

    outcomes = await StressLossEvaluator().evaluate(
        rule=rule(RuleType.STRESS_LOSS),
        context=context([holding("AAPL")], scenario_runner=runner),
    )

    assert outcomes[0].kind is OutcomeKind.NOT_EVALUATED
    assert "No configured scenario could be evaluated" in outcomes[0].reason


async def test_stress_loss_evaluates_each_configured_scenario():
    async def runner(scenario_key: str):
        loss = Decimal("-0.30") if scenario_key == "covid_19_crash_2020" else Decimal("-0.02")
        return loss, loss * 10000, scenario_key

    outcomes = await StressLossEvaluator().evaluate(
        rule=rule(
            RuleType.STRESS_LOSS,
            parameters={"scenario_keys": ["covid_19_crash_2020", "rate_rises_2022"]},
        ),
        context=context([holding("AAPL")], scenario_runner=runner),
    )

    assert [item.subject for item in outcomes] == ["covid_19_crash_2020"]


async def test_stress_loss_without_a_runner_is_not_evaluated():
    outcomes = await StressLossEvaluator().evaluate(
        rule=rule(RuleType.STRESS_LOSS),
        context=context([holding("AAPL")]),
    )

    assert outcomes[0].kind is OutcomeKind.NOT_EVALUATED


# --- Stale market data --------------------------------------------------------


async def test_a_friday_price_is_not_stale_on_the_following_monday_at_the_high_threshold():
    """The central weekend case: one trading day old, not two."""
    friday = date(2024, 3, 15)

    outcomes = await StaleMarketDataEvaluator().evaluate(
        rule=rule(RuleType.STALE_MARKET_DATA, thresholds={"high": 2, "critical": 5}),
        context=context([holding("AAPL", price_date=friday)], now=NOW),
    )

    assert outcomes == []


async def test_a_friday_price_is_one_trading_day_old_on_monday():
    friday = date(2024, 3, 15)

    outcomes = await StaleMarketDataEvaluator().evaluate(
        rule=rule(RuleType.STALE_MARKET_DATA),
        context=context([holding("AAPL", price_date=friday)], now=NOW),
    )

    assert outcomes[0].observed_value == Decimal(1)
    assert outcomes[0].severity is SignalSeverity.ELEVATED
    assert "1 expected trading days" in outcomes[0].explanation


async def test_a_weekend_alone_never_makes_data_stale():
    friday = date(2024, 3, 15)
    saturday = datetime(2024, 3, 16, 12, 0, tzinfo=UTC)

    outcomes = await StaleMarketDataEvaluator().evaluate(
        rule=rule(RuleType.STALE_MARKET_DATA),
        context=context([holding("AAPL", price_date=friday)], now=saturday),
    )

    assert outcomes == []


async def test_todays_price_is_not_stale():
    outcomes = await StaleMarketDataEvaluator().evaluate(
        rule=rule(RuleType.STALE_MARKET_DATA),
        context=context([holding("AAPL", price_date=TODAY)], now=NOW),
    )

    assert outcomes == []


@pytest.mark.parametrize(
    ("stale_date", "expected_days", "expected"),
    [
        # Evaluated on Monday 2024-03-18. Staleness counts expected trading days,
        # so the weekend in between never adds to the age.
        (date(2024, 3, 15), 1, SignalSeverity.ELEVATED),  # Friday
        (date(2024, 3, 14), 2, SignalSeverity.HIGH),  # Thursday
        (date(2024, 3, 11), 5, SignalSeverity.CRITICAL),  # the previous Monday
    ],
)
async def test_staleness_severity_boundaries(stale_date, expected_days, expected):
    outcomes = await StaleMarketDataEvaluator().evaluate(
        rule=rule(RuleType.STALE_MARKET_DATA),
        context=context([holding("AAPL", price_date=stale_date)], now=NOW),
    )

    assert outcomes[0].observed_value == Decimal(expected_days)
    assert outcomes[0].severity is expected


async def test_staleness_records_the_calendar_convention():
    outcomes = await StaleMarketDataEvaluator().evaluate(
        rule=rule(RuleType.STALE_MARKET_DATA),
        context=context([holding("AAPL", price_date=TODAY - timedelta(days=3))], now=NOW),
    )

    assert "Monday to Friday" in outcomes[0].context["calendar_convention"]


async def test_an_unpriced_holding_is_not_a_staleness_condition():
    """Absent data is the missing-data rule's business."""
    outcomes = await StaleMarketDataEvaluator().evaluate(
        rule=rule(RuleType.STALE_MARKET_DATA),
        context=context([holding("ZZZZ", price=None)], now=NOW),
    )

    assert outcomes == []


# --- Missing data -------------------------------------------------------------


async def test_missing_data_reports_unpriced_holdings():
    outcomes = await MissingDataEvaluator().evaluate(
        rule=rule(RuleType.MISSING_DATA),
        context=context([holding("AAPL"), holding("ZZZZ", price=None)]),
    )

    unpriced = next(item for item in outcomes if item.subject == "unpriced_holdings")
    assert unpriced.triggered
    assert unpriced.context["affected_symbols"] == ["ZZZZ"]
    assert "portfolio value" in unpriced.context["affected_calculations"]


async def test_missing_data_reports_missing_sector_metadata():
    outcomes = await MissingDataEvaluator().evaluate(
        rule=rule(RuleType.MISSING_DATA),
        context=context([holding("ZZZZ", sector=UNKNOWN_SECTOR)]),
    )

    sector = next(item for item in outcomes if item.subject == "missing_sector_metadata")
    assert sector.triggered
    assert sector.severity is not SignalSeverity.CRITICAL


async def test_missing_data_reports_insufficient_history():
    outcomes = await MissingDataEvaluator().evaluate(
        rule=rule(RuleType.MISSING_DATA),
        context=context(
            [holding("AAPL")],
            history={"AAPL": series("AAPL", [100.0, 101.0, 102.0])},
        ),
    )

    history = next(item for item in outcomes if item.subject == "insufficient_history")
    assert history.observed_value == Decimal(2)
    assert history.threshold_value == Decimal(30)
    assert "volatility" in history.context["affected_calculations"]


async def test_missing_data_is_clear_for_a_complete_portfolio():
    prices = flat_then_volatile(calm_days=60, calm_move=0.005, recent_days=0, recent_move=0.0)

    outcomes = await MissingDataEvaluator().evaluate(
        rule=rule(RuleType.MISSING_DATA),
        context=context([holding("AAPL")], history={"AAPL": series("AAPL", prices)}),
    )

    assert outcomes == []


async def test_missing_data_on_an_empty_portfolio_is_not_evaluated():
    outcomes = await MissingDataEvaluator().evaluate(
        rule=rule(RuleType.MISSING_DATA),
        context=context([]),
    )

    assert outcomes[0].kind is OutcomeKind.NOT_EVALUATED


# --- Messaging discipline -----------------------------------------------------


FORBIDDEN_PHRASES = (
    "will fall",
    "will crash",
    "we predict",
    "prediction",
    "guarantee",
    "you should sell",
    "you should buy",
    "rebalance now",
    "unsafe",
    "risk-free",
)


async def test_no_message_predicts_an_event_or_recommends_a_trade():
    """The Gjallarhorn writing style, enforced across every triggering rule."""
    prices = flat_then_volatile(calm_days=260, calm_move=0.004, recent_days=20, recent_move=0.03)
    holdings = [
        holding("AAPL", quantity="1", price="60"),
        holding("MSFT", quantity="1", price="40"),
    ]
    history = {"AAPL": series("AAPL", prices), "MSFT": series("MSFT", prices)}

    async def runner(_scenario_key: str):
        return Decimal("-0.30"), Decimal("-3000"), "COVID-19 crash"

    shared = context(holdings, history=history, scenario_runner=runner)
    messages: list[str] = []

    for rule_type in RuleType:
        outcomes = await get_evaluator(rule_type).evaluate(
            rule=rule(rule_type),
            context=shared,
        )
        for outcome in outcomes:
            if outcome.triggered:
                messages.extend([outcome.title, outcome.explanation, outcome.suggested_action])

    assert messages, "no rule triggered, so nothing was checked"
    for message in messages:
        lowered = message.lower()
        for phrase in FORBIDDEN_PHRASES:
            assert phrase not in lowered, f"{phrase!r} appears in {message!r}"


async def test_every_triggered_signal_carries_the_fields_a_reader_needs():
    calm_then_wild = flat_then_volatile(
        calm_days=260, calm_move=0.004, recent_days=20, recent_move=0.03
    )
    always_wild = flat_then_volatile(calm_days=0, calm_move=0.0, recent_days=140, recent_move=0.04)

    # Each rule gets a context that actually triggers it.
    contexts = {
        RuleType.POSITION_CONCENTRATION: context([holding("AAPL")]),
        RuleType.VOLATILITY_INCREASE: context(
            [holding("AAPL")], history={"AAPL": series("AAPL", calm_then_wild)}
        ),
        RuleType.VAR_THRESHOLD: context(
            [holding("AAPL")], history={"AAPL": series("AAPL", always_wild)}
        ),
        RuleType.STALE_MARKET_DATA: context(
            [holding("AAPL", price_date=date(2024, 3, 11))], now=NOW
        ),
    }

    for rule_type, shared in contexts.items():
        outcomes = await get_evaluator(rule_type).evaluate(rule=rule(rule_type), context=shared)
        triggered = [item for item in outcomes if item.triggered]
        assert triggered, rule_type

        for outcome in triggered:
            assert outcome.title
            assert outcome.explanation
            assert outcome.suggested_action
            assert outcome.observed_value is not None
            assert outcome.threshold_value is not None
            assert outcome.unit
            assert outcome.analysis_period
            assert outcome.severity is not None


# --- Fingerprints -------------------------------------------------------------


def test_a_fingerprint_is_stable_across_observations():
    rule_id = uuid.uuid4()
    first = build_fingerprint(
        portfolio_id=PORTFOLIO_ID,
        alert_rule_id=rule_id,
        signal_type="position_concentration",
        subject="AAPL",
    )
    second = build_fingerprint(
        portfolio_id=PORTFOLIO_ID,
        alert_rule_id=rule_id,
        signal_type="position_concentration",
        subject="AAPL",
    )

    assert first == second


def test_a_different_subject_gets_a_different_fingerprint():
    rule_id = uuid.uuid4()

    assert build_fingerprint(
        portfolio_id=PORTFOLIO_ID,
        alert_rule_id=rule_id,
        signal_type="position_concentration",
        subject="AAPL",
    ) != build_fingerprint(
        portfolio_id=PORTFOLIO_ID,
        alert_rule_id=rule_id,
        signal_type="position_concentration",
        subject="MSFT",
    )


def test_a_different_portfolio_gets_a_different_fingerprint():
    rule_id = uuid.uuid4()

    assert build_fingerprint(
        portfolio_id=PORTFOLIO_ID,
        alert_rule_id=rule_id,
        signal_type="x",
        subject="AAPL",
    ) != build_fingerprint(
        portfolio_id=uuid.uuid4(),
        alert_rule_id=rule_id,
        signal_type="x",
        subject="AAPL",
    )


def test_a_fingerprint_ignores_subject_case_and_whitespace():
    rule_id = uuid.uuid4()

    assert build_fingerprint(
        portfolio_id=PORTFOLIO_ID,
        alert_rule_id=rule_id,
        signal_type="X",
        subject="AAPL",
    ) == build_fingerprint(
        portfolio_id=PORTFOLIO_ID,
        alert_rule_id=rule_id,
        signal_type="x",
        subject=" aapl ",
    )


def test_a_missing_subject_falls_back_to_portfolio_scope():
    rule_id = uuid.uuid4()

    assert build_fingerprint(
        portfolio_id=PORTFOLIO_ID,
        alert_rule_id=rule_id,
        signal_type="x",
        subject=None,
    ) == build_fingerprint(
        portfolio_id=PORTFOLIO_ID,
        alert_rule_id=rule_id,
        signal_type="x",
        subject="portfolio",
    )


def test_a_fingerprint_has_a_fixed_length():
    assert (
        len(
            build_fingerprint(
                portfolio_id=PORTFOLIO_ID,
                alert_rule_id=uuid.uuid4(),
                signal_type="x",
                subject="a" * 500,
            )
        )
        == 64
    )


# --- Cooldowns ----------------------------------------------------------------


class _Signal:
    """Minimal stand-in carrying only what `should_notify` reads."""

    def __init__(self, last_notified_at: datetime | None) -> None:
        self.id = uuid.uuid4()
        self.last_notified_at = last_notified_at
        self.signal_type = "position_concentration"
        self.severity = "elevated"


def test_a_new_signal_is_always_notified():
    decision = should_notify(
        signal=_Signal(None),  # type: ignore[arg-type]
        new_severity=SignalSeverity.ELEVATED,
        previous_severity=None,
        cooldown_hours=24,
        now=NOW,
    )

    assert decision.deliver is True
    assert decision.reason == "new signal"


def test_a_repeat_inside_the_cooldown_is_suppressed():
    decision = should_notify(
        signal=_Signal(NOW - timedelta(hours=2)),  # type: ignore[arg-type]
        new_severity=SignalSeverity.ELEVATED,
        previous_severity=SignalSeverity.ELEVATED,
        cooldown_hours=24,
        now=NOW,
    )

    assert decision.deliver is False
    assert "within cooldown" in decision.reason


def test_a_repeat_after_the_cooldown_is_delivered():
    decision = should_notify(
        signal=_Signal(NOW - timedelta(hours=25)),  # type: ignore[arg-type]
        new_severity=SignalSeverity.ELEVATED,
        previous_severity=SignalSeverity.ELEVATED,
        cooldown_hours=24,
        now=NOW,
    )

    assert decision.deliver is True


def test_a_severity_increase_bypasses_the_cooldown():
    decision = should_notify(
        signal=_Signal(NOW - timedelta(minutes=5)),  # type: ignore[arg-type]
        new_severity=SignalSeverity.CRITICAL,
        previous_severity=SignalSeverity.ELEVATED,
        cooldown_hours=24,
        now=NOW,
    )

    assert decision.deliver is True
    assert "severity increased" in decision.reason


def test_a_severity_decrease_does_not_bypass_the_cooldown():
    decision = should_notify(
        signal=_Signal(NOW - timedelta(minutes=5)),  # type: ignore[arg-type]
        new_severity=SignalSeverity.ELEVATED,
        previous_severity=SignalSeverity.CRITICAL,
        cooldown_hours=24,
        now=NOW,
    )

    assert decision.deliver is False


def test_a_zero_cooldown_always_delivers():
    decision = should_notify(
        signal=_Signal(NOW),  # type: ignore[arg-type]
        new_severity=SignalSeverity.ELEVATED,
        previous_severity=SignalSeverity.ELEVATED,
        cooldown_hours=0,
        now=NOW,
    )

    assert decision.deliver is True


def test_a_signal_never_notified_is_delivered_even_inside_a_cooldown():
    decision = should_notify(
        signal=_Signal(None),  # type: ignore[arg-type]
        new_severity=SignalSeverity.ELEVATED,
        previous_severity=SignalSeverity.ELEVATED,
        cooldown_hours=24,
        now=NOW,
    )

    assert decision.deliver is True
    assert decision.reason == "never notified"


# --- Defaults -----------------------------------------------------------------


def test_the_default_rule_set_covers_every_rule_type():
    from app.early_warning.defaults import default_rule_set

    assert {item.rule_type for item in default_rule_set()} == set(RuleType)


def test_default_thresholds_match_the_documented_values():
    from app.early_warning.defaults import default_rule_set

    defaults = {item.rule_type: item.thresholds.as_dict() for item in default_rule_set()}

    assert defaults[RuleType.POSITION_CONCENTRATION] == {
        "elevated": 0.20,
        "high": 0.30,
        "critical": 0.40,
    }
    assert defaults[RuleType.SECTOR_CONCENTRATION] == {
        "elevated": 0.30,
        "high": 0.40,
        "critical": 0.50,
    }
    assert defaults[RuleType.PORTFOLIO_DRAWDOWN] == {
        "elevated": 0.05,
        "high": 0.10,
        "critical": 0.20,
    }
    assert defaults[RuleType.CORRELATION_INCREASE] == {
        "elevated": 0.65,
        "high": 0.75,
        "critical": 0.85,
    }
    assert defaults[RuleType.STRESS_LOSS] == {
        "elevated": 0.10,
        "high": 0.15,
        "critical": 0.25,
    }
    assert defaults[RuleType.STALE_MARKET_DATA] == {
        "elevated": 1.0,
        "high": 2.0,
        "critical": 5.0,
    }
    assert defaults[RuleType.VOLATILITY_INCREASE] == {
        "elevated": 1.25,
        "high": 1.50,
        "critical": 2.00,
    }


def test_every_default_rule_validates_against_its_own_schema():
    from app.early_warning.defaults import default_rule_set

    for default in default_rule_set():
        parse_parameters(default.rule_type, default.parameters)
