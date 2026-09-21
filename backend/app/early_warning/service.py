"""Early Warning System use cases: rules, monitoring runs, and signal lifecycle.

The lifecycle implemented here, exactly as documented:

```text
new condition       -> active
active viewed       -> acknowledged
condition persists  -> stays active or acknowledged, values updated
condition clears    -> resolved
condition returns   -> a NEW active occurrence
user hides signal   -> dismissed
severity increases  -> the existing occurrence is updated
```

Acknowledgement never implies resolution, and a user can never mark an active
condition resolved: only the rule engine resolves a signal, when its condition is
no longer observed.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal

from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.snapshot import PortfolioSnapshot, SnapshotBuilder
from app.common.clock import Clock
from app.common.errors import ConflictError, ErrorDetail, NotFoundError, ValidationError
from app.common.logging import get_logger
from app.early_warning.defaults import build_default_rules
from app.early_warning.evaluation import (
    OutcomeKind,
    PriceSeries,
    RuleContext,
    RuleOutcome,
    ScenarioRunner,
)
from app.early_warning.evaluators import get_evaluator
from app.early_warning.fingerprint import build_fingerprint
from app.early_warning.models import (
    AlertRule,
    MonitoringRun,
    SignalEvent,
    SignalEventType,
    WarningSignal,
)
from app.early_warning.notifications import Notifier, should_notify
from app.early_warning.repository import (
    AlertRuleRepository,
    MonitoringRunRepository,
    WarningSignalRepository,
)
from app.early_warning.rule_types import (
    SEVERITY_RANK,
    MonitoringStatus,
    MonitoringTriggerType,
    RuleType,
    SeverityThresholds,
    SignalSeverity,
    SignalStatus,
    parse_parameters,
)
from app.portfolios.models import Portfolio
from app.portfolios.repository import PortfolioRepository
from app.portfolios.service import PortfolioNotFoundError
from app.stress_testing.engine import HoldingInput, apply_returns, window_return
from app.stress_testing.service import StressTestingService

logger = get_logger(__name__)

# History loaded once per run. Long enough for the longest default window plus a
# margin for weekends and holidays.
HISTORY_LOOKBACK_DAYS = 500


class AlertRuleNotFoundError(NotFoundError):
    """The rule does not exist, or belongs to another user's portfolio."""

    code = "alert_rule_not_found"
    message = "Alert rule not found."


class SignalNotFoundError(NotFoundError):
    """The signal does not exist, or belongs to another user's portfolio."""

    code = "signal_not_found"
    message = "Signal not found."


class MonitoringRunNotFoundError(NotFoundError):
    """The monitoring run does not exist, or belongs to another user's portfolio."""

    code = "monitoring_run_not_found"
    message = "Monitoring run not found."


class DuplicateAlertRuleError(ConflictError):
    """The portfolio already has a rule of this type."""

    code = "alert_rule_exists"
    message = "This portfolio already has a rule of that type. Update the existing rule instead."


class MonitoringAlreadyRunningError(ConflictError):
    """A monitoring run for this portfolio is already in progress."""

    code = "monitoring_already_running"
    message = "A monitoring run for this portfolio is already in progress."


class SignalNotOpenError(ConflictError):
    """The signal is already resolved or dismissed."""

    code = "signal_not_open"
    message = "This signal is already closed, so its status cannot be changed."


class InvalidRuleParametersError(ValidationError):
    """The rule's parameters or thresholds are not valid for its type."""

    code = "invalid_rule_configuration"


@dataclass(slots=True)
class RuleResult:
    """What one rule did during a monitoring run."""

    rule_id: uuid.UUID
    rule_type: str
    status: str
    signals_created: int = 0
    signals_updated: int = 0
    signals_resolved: int = 0
    skipped_reason: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, object]:
        """Serializable form, stored on the run."""
        return {
            "rule_id": str(self.rule_id),
            "rule_type": self.rule_type,
            "status": self.status,
            "signals_created": self.signals_created,
            "signals_updated": self.signals_updated,
            "signals_resolved": self.signals_resolved,
            "skipped_reason": self.skipped_reason,
            "error": self.error,
        }


@dataclass(slots=True)
class MonitoringOutcome:
    """Aggregate outcome of one monitoring run.

    `deduplicated` marks a run that was **not** performed because an equivalent one
    already exists for this evaluation period. The stored run is returned so the
    caller sees the outcome, but no new work happened, which matters for counting.
    """

    run: MonitoringRun
    results: list[RuleResult] = field(default_factory=list)
    deduplicated: bool = False


class EarlyWarningService:
    """Manages alert rules, runs monitoring, and drives the signal lifecycle."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        portfolios: PortfolioRepository,
        rules: AlertRuleRepository,
        runs: MonitoringRunRepository,
        signals: WarningSignalRepository,
        snapshots: SnapshotBuilder,
        stress_testing: StressTestingService,
        notifier: Notifier,
        clock: Clock,
    ) -> None:
        self._session = session
        self._portfolios = portfolios
        self._rules = rules
        self._runs = runs
        self._signals = signals
        self._snapshots = snapshots
        self._stress_testing = stress_testing
        self._notifier = notifier
        self._clock = clock

    # --- Rules ---------------------------------------------------------------

    async def list_rules(
        self,
        *,
        portfolio_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> list[AlertRule]:
        """A portfolio's alert rules."""
        await self._require_portfolio(portfolio_id, user_id)
        return await self._rules.list_for_portfolio(portfolio_id)

    async def get_rule(self, *, rule_id: uuid.UUID, user_id: uuid.UUID) -> AlertRule:
        """One alert rule, scoped to the owner."""
        rule = await self._rules.get_owned(rule_id, user_id)
        if rule is None:
            raise AlertRuleNotFoundError()
        return rule

    async def create_rule(
        self,
        *,
        portfolio_id: uuid.UUID,
        user_id: uuid.UUID,
        rule_type: RuleType,
        name: str,
        description: str | None,
        enabled: bool,
        parameters: dict[str, object],
        thresholds: dict[str, float],
        cooldown_hours: int,
    ) -> AlertRule:
        """Create a rule after validating it against its own schema."""
        await self._require_portfolio(portfolio_id, user_id)

        evaluator = get_evaluator(rule_type)
        validated_parameters = self._validate_parameters(rule_type, parameters)
        validated_thresholds = self._validate_thresholds(thresholds)

        rule = AlertRule(
            portfolio_id=portfolio_id,
            rule_type=str(rule_type),
            name=name,
            description=description or evaluator.default_description,
            enabled=enabled,
            parameters=validated_parameters,
            severity_configuration=validated_thresholds,
            cooldown_hours=cooldown_hours,
        )
        self._rules.add(rule)

        try:
            await self._session.flush()
        except IntegrityError as exc:
            raise DuplicateAlertRuleError() from exc

        logger.info("alert_rule_created", rule_id=str(rule.id), rule_type=str(rule_type))
        return rule

    async def update_rule(
        self,
        *,
        rule_id: uuid.UUID,
        user_id: uuid.UUID,
        fields: dict[str, object],
    ) -> AlertRule:
        """Apply a partial update to a rule, revalidating whatever changed."""
        rule = await self.get_rule(rule_id=rule_id, user_id=user_id)
        if not fields:
            raise ValidationError(
                "Provide at least one field to update.",
                code="no_fields_to_update",
            )

        rule_type = RuleType(rule.rule_type)

        if "parameters" in fields:
            payload = fields["parameters"]
            rule.parameters = self._validate_parameters(
                rule_type,
                payload if isinstance(payload, dict) else {},
            )
        if "severity_configuration" in fields:
            payload = fields["severity_configuration"]
            rule.severity_configuration = self._validate_thresholds(
                payload if isinstance(payload, dict) else {}
            )
        for key in ("name", "description", "enabled", "cooldown_hours"):
            if key in fields:
                setattr(rule, key, fields[key])

        await self._session.flush()
        logger.info("alert_rule_updated", rule_id=str(rule.id))
        return rule

    async def delete_rule(self, *, rule_id: uuid.UUID, user_id: uuid.UUID) -> None:
        """Delete a rule and, by cascade, its signal history."""
        rule = await self.get_rule(rule_id=rule_id, user_id=user_id)
        await self._rules.delete(rule)
        await self._session.flush()
        logger.info("alert_rule_deleted", rule_id=str(rule_id))

    async def provision_defaults(
        self,
        *,
        portfolio_id: uuid.UUID,
        user_id: uuid.UUID,
        restore: bool = False,
    ) -> list[AlertRule]:
        """Create the default rule set, or restore it to documented values.

        Idempotent. With `restore=False`, existing rules are left exactly as they
        are and only missing types are added. With `restore=True`, every rule is
        reset to its documented defaults.
        """
        await self._require_portfolio(portfolio_id, user_id)

        existing = {
            rule.rule_type: rule for rule in await self._rules.list_for_portfolio(portfolio_id)
        }

        for candidate in build_default_rules(portfolio_id):
            current = existing.get(candidate.rule_type)

            if current is None:
                self._rules.add(candidate)
                continue

            if restore:
                current.name = candidate.name
                current.description = candidate.description
                current.enabled = True
                current.parameters = candidate.parameters
                current.severity_configuration = candidate.severity_configuration
                current.cooldown_hours = candidate.cooldown_hours

        await self._session.flush()
        logger.info(
            "alert_rules_provisioned",
            portfolio_id=str(portfolio_id),
            restore=restore,
        )
        return await self._rules.list_for_portfolio(portfolio_id)

    # --- Monitoring ----------------------------------------------------------

    async def run_monitoring(
        self,
        *,
        portfolio_id: uuid.UUID,
        user_id: uuid.UUID | None,
        trigger_type: MonitoringTriggerType,
        idempotency_key: str | None = None,
    ) -> MonitoringOutcome:
        """Evaluate every enabled rule for a portfolio and reconcile its signals.

        A failing rule is recorded and the run continues, so one broken rule never
        discards the results of the others. `user_id` is None for scheduled runs,
        which are not performed on behalf of a signed-in user.
        """
        if user_id is not None:
            await self._require_portfolio(portfolio_id, user_id)
        else:
            await self._portfolios_any(portfolio_id)

        if idempotency_key is not None:
            existing = await self._runs.find_by_idempotency_key(portfolio_id, idempotency_key)
            if existing is not None:
                logger.info(
                    "monitoring_run_deduplicated",
                    portfolio_id=str(portfolio_id),
                    run_id=str(existing.id),
                )
                return MonitoringOutcome(run=existing, deduplicated=True)

        if await self._runs.has_running(portfolio_id):
            raise MonitoringAlreadyRunningError()

        started = self._clock.now()
        run = MonitoringRun(
            portfolio_id=portfolio_id,
            trigger_type=str(trigger_type),
            status=str(MonitoringStatus.RUNNING),
            idempotency_key=idempotency_key,
            rule_results=[],
        )
        self._runs.add(run)

        try:
            await self._session.flush()
        except IntegrityError as exc:
            # A concurrent scheduled run claimed the same period first.
            raise MonitoringAlreadyRunningError() from exc

        rules = await self._rules.list_for_portfolio(portfolio_id, enabled_only=True)
        if not rules:
            run.status = str(MonitoringStatus.SKIPPED)
            run.completed_at = self._clock.now()
            run.error_summary = "No enabled alert rules are configured for this portfolio."
            await self._session.flush()
            return MonitoringOutcome(run=run)

        context = await self._build_context(portfolio_id)
        run.data_as_of = context.data_as_of

        results: list[RuleResult] = []
        seen_fingerprints: set[str] = set()

        for rule in rules:
            result = await self._evaluate_rule(
                rule=rule,
                context=context,
                run=run,
                seen_fingerprints=seen_fingerprints,
            )
            results.append(result)

        resolved = await self._resolve_cleared(
            portfolio_id=portfolio_id,
            rules=rules,
            results=results,
            seen_fingerprints=seen_fingerprints,
            run=run,
        )

        run.rules_evaluated = len(results)
        run.rules_failed = sum(1 for item in results if item.status == "failed")
        run.signals_created = sum(item.signals_created for item in results)
        run.signals_updated = sum(item.signals_updated for item in results)
        run.signals_resolved = resolved
        run.rule_results = [item.to_dict() for item in results]
        run.completed_at = self._clock.now()
        run.status = str(
            MonitoringStatus.PARTIAL if run.rules_failed else MonitoringStatus.SUCCEEDED
        )
        if run.rules_failed:
            run.error_summary = (
                f"{run.rules_failed} of {run.rules_evaluated} rules failed. "
                "Results from the remaining rules are complete."
            )

        await self._session.flush()
        logger.info(
            "monitoring_run_completed",
            portfolio_id=str(portfolio_id),
            run_id=str(run.id),
            status=run.status,
            created=run.signals_created,
            updated=run.signals_updated,
            resolved=run.signals_resolved,
            failed=run.rules_failed,
            duration_seconds=(run.completed_at - started).total_seconds(),
        )
        return MonitoringOutcome(run=run, results=results)

    async def list_runs(
        self,
        *,
        portfolio_id: uuid.UUID,
        user_id: uuid.UUID,
        limit: int,
        offset: int,
    ) -> tuple[list[MonitoringRun], int]:
        """A portfolio's monitoring runs, newest first."""
        await self._require_portfolio(portfolio_id, user_id)
        return (
            await self._runs.list_for_portfolio(portfolio_id, limit=limit, offset=offset),
            await self._runs.count_for_portfolio(portfolio_id),
        )

    async def get_run(self, *, run_id: uuid.UUID, user_id: uuid.UUID) -> MonitoringRun:
        """One monitoring run, scoped to the owner."""
        run = await self._runs.get_owned(run_id, user_id)
        if run is None:
            raise MonitoringRunNotFoundError()
        return run

    async def eligible_portfolio_ids(
        self, *, limit: int, after: uuid.UUID | None
    ) -> list[uuid.UUID]:
        """Portfolios with at least one enabled rule, for scheduled batches.

        Paged by id so a scheduled job can resume with a cursor instead of looping
        over everything in one invocation.
        """
        statement = (
            select(AlertRule.portfolio_id)
            .where(AlertRule.enabled.is_(True))
            .group_by(AlertRule.portfolio_id)
            .order_by(AlertRule.portfolio_id.asc())
            .limit(limit)
        )
        if after is not None:
            statement = statement.where(AlertRule.portfolio_id > after)

        result = await self._session.execute(statement)
        return list(result.scalars())

    # --- Signal lifecycle ----------------------------------------------------

    async def get_signal(self, *, signal_id: uuid.UUID, user_id: uuid.UUID) -> WarningSignal:
        """One signal with its audit trail, scoped to the owner."""
        signal = await self._signals.get_owned(signal_id, user_id)
        if signal is None:
            raise SignalNotFoundError()
        return signal

    async def acknowledge(self, *, signal_id: uuid.UUID, user_id: uuid.UUID) -> WarningSignal:
        """Record that the user has seen a signal.

        Acknowledgement does **not** resolve the signal: the condition is still
        present, and only the rule engine may resolve it.
        """
        signal = await self.get_signal(signal_id=signal_id, user_id=user_id)
        if not signal.is_open:
            raise SignalNotOpenError()

        if signal.acknowledged_at is None:
            now = self._clock.now()
            previous_status = signal.status
            signal.acknowledged_at = now
            signal.acknowledged_by = user_id
            signal.status = str(SignalStatus.ACKNOWLEDGED)
            self._record_event(
                signal,
                event_type=SignalEventType.ACKNOWLEDGED,
                from_status=previous_status,
                to_status=signal.status,
                actor_user_id=user_id,
                note="The user acknowledged the signal. The condition is still present.",
            )
            await self._session.flush()
            logger.info("signal_acknowledged", signal_id=str(signal.id))

        return signal

    async def dismiss(self, *, signal_id: uuid.UUID, user_id: uuid.UUID) -> WarningSignal:
        """Hide a signal without claiming its condition has cleared.

        A dismissed signal leaves the default view. If the same condition is later
        observed again, a new occurrence is created, so dismissing is not a way to
        silence a rule permanently.
        """
        signal = await self.get_signal(signal_id=signal_id, user_id=user_id)
        if not signal.is_open:
            raise SignalNotOpenError()

        now = self._clock.now()
        previous_status = signal.status
        signal.dismissed_at = now
        signal.status = str(SignalStatus.DISMISSED)
        self._record_event(
            signal,
            event_type=SignalEventType.DISMISSED,
            from_status=previous_status,
            to_status=signal.status,
            actor_user_id=user_id,
            note="The user hid the signal. The underlying condition was not changed.",
        )
        await self._session.flush()
        logger.info("signal_dismissed", signal_id=str(signal.id))
        return signal

    async def severity_counts(
        self,
        *,
        portfolio_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> dict[str, int]:
        """Open signal counts by severity, for the summary panel."""
        await self._require_portfolio(portfolio_id, user_id)
        return await self._signals.severity_counts(portfolio_id)

    # --- Internals -----------------------------------------------------------

    async def _require_portfolio(
        self,
        portfolio_id: uuid.UUID,
        user_id: uuid.UUID | None,
    ) -> Portfolio:
        """Load a portfolio the caller owns, or raise."""
        if user_id is None:
            return await self._portfolios_any(portfolio_id)
        portfolio = await self._portfolios.get_owned(portfolio_id, user_id)
        if portfolio is None:
            raise PortfolioNotFoundError()
        return portfolio

    async def _portfolios_any(self, portfolio_id: uuid.UUID) -> Portfolio:
        """Load a portfolio without an ownership check, for scheduled runs."""
        result = await self._session.execute(select(Portfolio).where(Portfolio.id == portfolio_id))
        portfolio: Portfolio | None = result.scalar_one_or_none()
        if portfolio is None:
            raise PortfolioNotFoundError()
        return portfolio

    @staticmethod
    def _validate_parameters(rule_type: RuleType, payload: dict[str, object]) -> dict[str, object]:
        """Validate parameters against the rule type's schema."""
        try:
            parsed = parse_parameters(rule_type, payload)
        except PydanticValidationError as exc:
            raise InvalidRuleParametersError(
                "The rule parameters are not valid for this rule type.",
                details=_pydantic_details(exc, prefix="parameters"),
            ) from exc

        result = parsed.model_dump(mode="json")
        result.pop("rule_type", None)
        return result

    @staticmethod
    def _validate_thresholds(payload: dict[str, float]) -> dict[str, float]:
        """Validate severity thresholds, including their ordering."""
        try:
            thresholds = SeverityThresholds.model_validate(payload)
        except PydanticValidationError as exc:
            raise InvalidRuleParametersError(
                "The severity thresholds are not valid.",
                details=_pydantic_details(exc, prefix="severity_configuration"),
            ) from exc
        return thresholds.as_dict()

    async def _build_context(self, portfolio_id: uuid.UUID) -> RuleContext:
        """Assemble everything the rules need, once per run."""
        portfolio = await self._portfolios_any(portfolio_id)
        snapshot = await self._snapshots.build(portfolio)

        now = self._clock.now()
        start = now.date() - timedelta(days=HISTORY_LOOKBACK_DAYS)
        history: dict[str, PriceSeries] = {}

        for holding in snapshot.priced_holdings:
            observations = await self._snapshots.symbol_history(
                holding.asset_id,
                start=start,
                end=now.date(),
            )
            if observations:
                history[holding.symbol] = PriceSeries(
                    symbol=holding.symbol,
                    observations=observations,
                )

        return RuleContext(
            snapshot=snapshot,
            history=history,
            evaluated_at=now,
            data_as_of=snapshot.data_as_of,
            scenario_runner=self._make_scenario_runner(snapshot),
        )

    def _make_scenario_runner(self, snapshot: PortfolioSnapshot) -> ScenarioRunner:
        """A callable the stress-loss rule uses, without importing the service."""

        async def run(scenario_key: str) -> tuple[Decimal, Decimal, str]:
            scenario = self._stress_testing.get_scenario(scenario_key)
            returns: dict[str, Decimal] = {}
            sources: dict[str, str] = {}

            for holding in snapshot.priced_holdings:
                observations = await self._snapshots.symbol_history(
                    holding.asset_id,
                    start=scenario.start,
                    end=scenario.end,
                )
                observed = window_return(
                    [(day, Decimal(str(price))) for day, price in observations]
                )
                if observed is not None:
                    returns[holding.symbol] = observed
                    sources[holding.symbol] = f"observed return during {scenario.trading_window}"

            if not returns:
                raise ValueError(f"No stored price data covers {scenario.trading_window}.")

            result = apply_returns(
                [
                    HoldingInput(
                        symbol=holding.symbol,
                        sector=holding.sector,
                        market_value=holding.market_value or Decimal("0"),
                    )
                    for holding in snapshot.priced_holdings
                ],
                returns=returns,
                sources=sources,
            )
            return result.total_impact_percent, result.total_impact, scenario.name

        return run

    async def _evaluate_rule(
        self,
        *,
        rule: AlertRule,
        context: RuleContext,
        run: MonitoringRun,
        seen_fingerprints: set[str],
    ) -> RuleResult:
        """Evaluate one rule and apply its outcomes to the signal lifecycle."""
        result = RuleResult(rule_id=rule.id, rule_type=rule.rule_type, status="evaluated")

        try:
            evaluator = get_evaluator(rule.rule_type)
            outcomes = await evaluator.evaluate(rule=rule, context=context)
        except Exception as exc:
            logger.warning(
                "alert_rule_failed",
                rule_id=str(rule.id),
                rule_type=rule.rule_type,
                error=repr(exc),
            )
            result.status = "failed"
            result.error = f"{type(exc).__name__}: {exc}"
            return result

        skipped = [item for item in outcomes if item.kind is OutcomeKind.NOT_EVALUATED]
        if skipped:
            result.status = "skipped"
            result.skipped_reason = skipped[0].reason

        for outcome in outcomes:
            if not outcome.triggered:
                continue

            fingerprint = build_fingerprint(
                portfolio_id=rule.portfolio_id,
                alert_rule_id=rule.id,
                signal_type=rule.rule_type,
                subject=outcome.subject,
            )
            seen_fingerprints.add(fingerprint)

            created = await self._upsert_signal(
                rule=rule,
                run=run,
                outcome=outcome,
                fingerprint=fingerprint,
            )
            if created:
                result.signals_created += 1
            else:
                result.signals_updated += 1

        if result.status == "evaluated" and not any(item.triggered for item in outcomes):
            result.status = "clear"

        return result

    async def _upsert_signal(
        self,
        *,
        rule: AlertRule,
        run: MonitoringRun,
        outcome: RuleOutcome,
        fingerprint: str,
    ) -> bool:
        """Create or update the signal for one condition. Returns True when created."""
        now = self._clock.now()
        severity = outcome.severity or SignalSeverity.INFORMATIONAL
        existing = await self._signals.find_open(rule.portfolio_id, fingerprint)

        context_payload = {
            **outcome.context,
            "limitations": outcome.limitations,
            "rule_name": rule.name,
        }

        if existing is None:
            signal = WarningSignal(
                portfolio_id=rule.portfolio_id,
                alert_rule_id=rule.id,
                monitoring_run_id=run.id,
                fingerprint=fingerprint,
                signal_type=rule.rule_type,
                severity=str(severity),
                status=str(SignalStatus.ACTIVE),
                title=outcome.title,
                explanation=outcome.explanation,
                suggested_action=outcome.suggested_action,
                metric_name=outcome.context.get("metric_name", rule.rule_type),
                observed_value=outcome.observed_value or Decimal(0),
                threshold_value=outcome.threshold_value or Decimal(0),
                unit=outcome.unit,
                analysis_period=outcome.analysis_period,
                data_as_of=run.data_as_of,
                context=context_payload,
                first_triggered_at=now,
                last_triggered_at=now,
            )
            self._signals.add(signal)
            await self._session.flush()

            self._record_event(
                signal,
                event_type=SignalEventType.CREATED,
                to_severity=str(severity),
                to_status=signal.status,
                observed_value=outcome.observed_value,
                monitoring_run_id=run.id,
                note="The condition was observed for the first time in this occurrence.",
            )
            await self._notify(signal, new_severity=severity, previous_severity=None, rule=rule)
            await self._session.flush()
            return True

        previous_severity = SignalSeverity(existing.severity)
        previous_rank = SEVERITY_RANK[previous_severity]
        new_rank = SEVERITY_RANK[severity]

        # The current state is always recorded, cooldown or not.
        # Both are always set on a triggered outcome; the guard keeps mypy honest.
        existing.observed_value = outcome.observed_value or Decimal(0)
        existing.threshold_value = outcome.threshold_value or Decimal(0)
        existing.explanation = outcome.explanation
        existing.title = outcome.title
        existing.analysis_period = outcome.analysis_period
        existing.data_as_of = run.data_as_of
        existing.context = context_payload
        existing.last_triggered_at = now
        existing.monitoring_run_id = run.id
        existing.severity = str(severity)

        if new_rank > previous_rank:
            event_type = SignalEventType.SEVERITY_INCREASED
            note = f"Severity increased from {previous_severity} to {severity}."
        elif new_rank < previous_rank:
            event_type = SignalEventType.SEVERITY_DECREASED
            note = (
                f"Severity decreased from {previous_severity} to {severity}. "
                "The condition is still present."
            )
        else:
            event_type = SignalEventType.REOBSERVED
            note = "The condition was observed again with the same severity."

        self._record_event(
            existing,
            event_type=event_type,
            from_severity=str(previous_severity),
            to_severity=str(severity),
            observed_value=outcome.observed_value,
            monitoring_run_id=run.id,
            note=note,
        )
        await self._notify(
            existing,
            new_severity=severity,
            previous_severity=previous_severity,
            rule=rule,
        )
        await self._session.flush()
        return False

    async def _resolve_cleared(
        self,
        *,
        portfolio_id: uuid.UUID,
        rules: list[AlertRule],
        results: list[RuleResult],
        seen_fingerprints: set[str],
        run: MonitoringRun,
    ) -> int:
        """Resolve open signals whose condition was not observed this run.

        A rule that failed or was skipped is excluded: not being able to check a
        condition is not evidence that it cleared.
        """
        inconclusive = {
            result.rule_id for result in results if result.status in {"failed", "skipped"}
        }
        conclusive_rule_ids = [rule.id for rule in rules if rule.id not in inconclusive]

        open_signals = await self._signals.list_open_for_rules(portfolio_id, conclusive_rule_ids)
        now = self._clock.now()
        resolved = 0

        for signal in open_signals:
            if signal.fingerprint in seen_fingerprints:
                continue

            previous_status = signal.status
            signal.resolved_at = now
            signal.status = str(SignalStatus.RESOLVED)
            self._record_event(
                signal,
                event_type=SignalEventType.RESOLVED,
                from_status=previous_status,
                to_status=signal.status,
                monitoring_run_id=run.id,
                note="The triggering condition was no longer observed.",
            )
            resolved += 1
            logger.info("signal_resolved", signal_id=str(signal.id))

        if resolved:
            await self._session.flush()

        return resolved

    def _record_event(
        self,
        signal: WarningSignal,
        *,
        event_type: SignalEventType,
        from_severity: str | None = None,
        to_severity: str | None = None,
        from_status: str | None = None,
        to_status: str | None = None,
        observed_value: Decimal | None = None,
        monitoring_run_id: uuid.UUID | None = None,
        actor_user_id: uuid.UUID | None = None,
        note: str | None = None,
    ) -> None:
        """Append an audit entry. The trail is never updated or deleted."""
        self._signals.add_event(
            SignalEvent(
                signal_id=signal.id,
                monitoring_run_id=monitoring_run_id,
                event_type=str(event_type),
                from_severity=from_severity,
                to_severity=to_severity,
                from_status=from_status,
                to_status=to_status,
                observed_value=observed_value,
                actor_user_id=actor_user_id,
                note=note,
            )
        )

    async def _notify(
        self,
        signal: WarningSignal,
        *,
        new_severity: SignalSeverity,
        previous_severity: SignalSeverity | None,
        rule: AlertRule,
    ) -> None:
        """Deliver a notification if the cooldown rules allow it."""
        decision = should_notify(
            signal=signal,
            new_severity=new_severity,
            previous_severity=previous_severity,
            cooldown_hours=rule.cooldown_hours,
            now=self._clock.now(),
        )
        if not decision.deliver:
            logger.debug(
                "notification_skipped",
                signal_id=str(signal.id),
                reason=decision.reason,
            )
            return

        delivered = await self._notifier.deliver(signal, reason=decision.reason)
        if delivered:
            signal.last_notified_at = self._clock.now()


def _pydantic_details(
    exc: PydanticValidationError,
    *,
    prefix: str,
) -> list[ErrorDetail]:
    """Map pydantic errors onto the API's error-detail shape."""
    return [
        ErrorDetail(
            field=".".join([prefix, *(str(part) for part in error["loc"])]),
            message=str(error["msg"]),
            code=str(error["type"]),
        )
        for error in exc.errors()
    ]


__all__ = [
    "AlertRuleNotFoundError",
    "DuplicateAlertRuleError",
    "EarlyWarningService",
    "InvalidRuleParametersError",
    "MonitoringAlreadyRunningError",
    "MonitoringOutcome",
    "MonitoringRunNotFoundError",
    "RuleResult",
    "SignalNotFoundError",
    "SignalNotOpenError",
]
