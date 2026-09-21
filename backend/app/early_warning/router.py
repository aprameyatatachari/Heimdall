"""Early Warning System endpoints.

User-facing copy calls these Gjallarhorn Signals. The API keeps technical names —
`alert-rules`, `monitoring-runs`, `signals` — so the contract stays readable
without knowing the branding.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Path, Query, Response, status

from app.auth.dependencies import CurrentUser
from app.common.dependencies import ClockDep, SettingsDep
from app.common.schemas import DEFAULT_PAGE_LIMIT, MAX_PAGE_LIMIT, Page
from app.early_warning.dependencies import (
    EarlyWarningServiceDep,
    SchedulerGuard,
    SignalRepositoryDep,
)
from app.early_warning.evaluators import EVALUATORS
from app.early_warning.models import AlertRule, MonitoringRun, WarningSignal
from app.early_warning.repository import WarningSignalRepository
from app.early_warning.rule_types import (
    RULE_UNITS,
    MonitoringStatus,
    MonitoringTriggerType,
    RuleType,
    SignalSeverity,
    SignalStatus,
)
from app.early_warning.schemas import (
    SEVERITY_ICONS,
    AlertRuleCatalogueItem,
    AlertRuleCatalogueResponse,
    AlertRuleCreateRequest,
    AlertRuleResponse,
    AlertRuleUpdateRequest,
    MonitoringRuleResult,
    MonitoringRunResponse,
    MonitoringRunSummary,
    ScheduledMonitoringRequest,
    ScheduledMonitoringResponse,
    ScheduledPortfolioResult,
    SignalEventResponse,
    SignalSummaryResponse,
    WarningSignalResponse,
    default_thresholds_for,
)
from app.early_warning.service import MonitoringAlreadyRunningError

portfolio_router = APIRouter(prefix="/portfolios", tags=["early warning"])
signals_router = APIRouter(prefix="/signals", tags=["early warning"])
runs_router = APIRouter(prefix="/monitoring-runs", tags=["early warning"])
internal_router = APIRouter(prefix="/internal", tags=["early warning"])
catalogue_router = APIRouter(prefix="/alert-rule-types", tags=["early warning"])

PortfolioIdPath = Path(description="Portfolio identifier.")
RuleIdPath = Path(description="Alert rule identifier.")
SignalIdPath = Path(description="Signal identifier.")
RunIdPath = Path(description="Monitoring run identifier.")
PageLimit = Query(default=DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT)
PageOffset = Query(default=0, ge=0)
RestoreQuery = Query(
    default=False,
    description="Reset every existing rule to its documented defaults, not just add missing ones.",
)
StatusFilter = Query(default=None, description="Filter by signal status. Repeatable.")
SeverityFilter = Query(default=None, description="Filter by severity. Repeatable.")
TypeFilter = Query(default=None, description="Filter by signal type. Repeatable.")
FromFilter = Query(default=None, description="Only signals created at or after this instant.")
ToFilter = Query(default=None, description="Only signals created at or before this instant.")
AcknowledgedFilter = Query(
    default=None,
    description="True for acknowledged signals only, false for unacknowledged only.",
)
PortfolioFilter = Query(default=None, description="Restrict to one portfolio.")


# --- Rule catalogue ----------------------------------------------------------


@catalogue_router.get(
    "",
    response_model=AlertRuleCatalogueResponse,
    summary="List alert rule types",
    description=(
        "Every condition the Early Warning System can evaluate, with the unit it "
        "measures and its documented default thresholds."
    ),
)
async def list_rule_types(current_user: CurrentUser) -> AlertRuleCatalogueResponse:
    """Return the rule-type catalogue."""
    del current_user
    return AlertRuleCatalogueResponse(
        items=[
            AlertRuleCatalogueItem(
                rule_type=str(rule_type),
                name=evaluator.default_name,
                description=evaluator.default_description,
                unit=RULE_UNITS[rule_type],
                default_severity_configuration=evaluator.default_thresholds.as_dict(),
                default_cooldown_hours=evaluator.default_cooldown_hours,
                default_parameters=_default_parameters(rule_type),
            )
            for rule_type, evaluator in EVALUATORS.items()
        ]
    )


def _default_parameters(rule_type: RuleType) -> dict[str, object]:
    from app.early_warning.defaults import _default_parameters as defaults

    return defaults(rule_type)


# --- Alert rules -------------------------------------------------------------


@portfolio_router.get(
    "/{portfolio_id}/alert-rules",
    response_model=list[AlertRuleResponse],
    summary="List alert rules",
    description="Returns the portfolio's alert rules, ordered by rule type.",
)
async def list_alert_rules(
    current_user: CurrentUser,
    service: EarlyWarningServiceDep,
    portfolio_id: uuid.UUID = PortfolioIdPath,
) -> list[AlertRuleResponse]:
    """List a portfolio's alert rules."""
    rules = await service.list_rules(portfolio_id=portfolio_id, user_id=current_user.id)
    return [AlertRuleResponse.model_validate(rule) for rule in rules]


@portfolio_router.post(
    "/{portfolio_id}/alert-rules",
    response_model=AlertRuleResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an alert rule",
    description=(
        "Creates one rule. `parameters` is validated against the rule type's own "
        "schema, and `severity_configuration` must increase with severity. A "
        "portfolio holds at most one rule per type."
    ),
)
async def create_alert_rule(
    payload: AlertRuleCreateRequest,
    current_user: CurrentUser,
    service: EarlyWarningServiceDep,
    portfolio_id: uuid.UUID = PortfolioIdPath,
) -> AlertRuleResponse:
    """Create an alert rule."""
    evaluator = EVALUATORS[payload.rule_type]
    rule = await service.create_rule(
        portfolio_id=portfolio_id,
        user_id=current_user.id,
        rule_type=payload.rule_type,
        name=payload.name or evaluator.default_name,
        description=payload.description,
        enabled=payload.enabled,
        parameters=payload.parameters,
        thresholds=payload.severity_configuration or default_thresholds_for(payload.rule_type),
        cooldown_hours=payload.cooldown_hours,
    )
    return AlertRuleResponse.model_validate(rule)


@portfolio_router.post(
    "/{portfolio_id}/alert-rules/defaults",
    response_model=list[AlertRuleResponse],
    summary="Provision or restore default rules",
    description=(
        "Creates the documented default rule set. Idempotent: rule types that "
        "already exist are left alone unless `restore=true`, which resets every "
        "rule to its documented defaults.\n\n"
        "Default rules are provisioned by this call, not automatically at portfolio "
        "creation, so an empty portfolio is never evaluated before it has holdings."
    ),
)
async def provision_default_rules(
    current_user: CurrentUser,
    service: EarlyWarningServiceDep,
    portfolio_id: uuid.UUID = PortfolioIdPath,
    restore: bool = RestoreQuery,
) -> list[AlertRuleResponse]:
    """Provision or restore the default rule set."""
    rules = await service.provision_defaults(
        portfolio_id=portfolio_id,
        user_id=current_user.id,
        restore=restore,
    )
    return [AlertRuleResponse.model_validate(rule) for rule in rules]


@portfolio_router.get(
    "/{portfolio_id}/alert-rules/{rule_id}",
    response_model=AlertRuleResponse,
    summary="Get an alert rule",
)
async def get_alert_rule(
    current_user: CurrentUser,
    service: EarlyWarningServiceDep,
    portfolio_id: uuid.UUID = PortfolioIdPath,
    rule_id: uuid.UUID = RuleIdPath,
) -> AlertRuleResponse:
    """Return one alert rule."""
    rule = await service.get_rule(rule_id=rule_id, user_id=current_user.id)
    _require_same_portfolio(rule, portfolio_id)
    return AlertRuleResponse.model_validate(rule)


@portfolio_router.patch(
    "/{portfolio_id}/alert-rules/{rule_id}",
    response_model=AlertRuleResponse,
    summary="Update an alert rule",
    description=(
        "Partial update. Enabling, disabling, and threshold changes all go through "
        "this endpoint. The rule type cannot be changed."
    ),
)
async def update_alert_rule(
    payload: AlertRuleUpdateRequest,
    current_user: CurrentUser,
    service: EarlyWarningServiceDep,
    portfolio_id: uuid.UUID = PortfolioIdPath,
    rule_id: uuid.UUID = RuleIdPath,
) -> AlertRuleResponse:
    """Update an alert rule."""
    rule = await service.get_rule(rule_id=rule_id, user_id=current_user.id)
    _require_same_portfolio(rule, portfolio_id)

    updated = await service.update_rule(
        rule_id=rule_id,
        user_id=current_user.id,
        fields=payload.model_dump(exclude_unset=True),
    )
    return AlertRuleResponse.model_validate(updated)


@portfolio_router.delete(
    "/{portfolio_id}/alert-rules/{rule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an alert rule",
    description=(
        "Deletes the rule and its signal history. To stop a rule from firing while "
        "keeping its history, disable it instead."
    ),
)
async def delete_alert_rule(
    current_user: CurrentUser,
    service: EarlyWarningServiceDep,
    portfolio_id: uuid.UUID = PortfolioIdPath,
    rule_id: uuid.UUID = RuleIdPath,
) -> Response:
    """Delete an alert rule."""
    rule = await service.get_rule(rule_id=rule_id, user_id=current_user.id)
    _require_same_portfolio(rule, portfolio_id)

    await service.delete_rule(rule_id=rule_id, user_id=current_user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _require_same_portfolio(rule: AlertRule, portfolio_id: uuid.UUID) -> None:
    """A rule reached through the wrong portfolio is reported as not found."""
    if rule.portfolio_id != portfolio_id:
        from app.early_warning.service import AlertRuleNotFoundError

        raise AlertRuleNotFoundError()


# --- Monitoring runs ---------------------------------------------------------


@portfolio_router.post(
    "/{portfolio_id}/monitoring-runs",
    response_model=MonitoringRunResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Run monitoring now",
    description=(
        "Evaluates every enabled rule for the portfolio and reconciles its signals: "
        "new conditions create signals, persisting conditions update them, and "
        "conditions that cleared are resolved.\n\n"
        "A rule that fails is recorded and the run continues, so one broken rule "
        "never discards the results of the others; the run's status becomes "
        "`partial`. A rule that could not be evaluated resolves nothing, because "
        "not being able to check a condition is not evidence that it cleared."
    ),
)
async def run_monitoring(
    current_user: CurrentUser,
    service: EarlyWarningServiceDep,
    portfolio_id: uuid.UUID = PortfolioIdPath,
) -> MonitoringRunResponse:
    """Trigger a manual monitoring run."""
    outcome = await service.run_monitoring(
        portfolio_id=portfolio_id,
        user_id=current_user.id,
        trigger_type=MonitoringTriggerType.MANUAL,
    )
    return _run_response(outcome.run)


@portfolio_router.get(
    "/{portfolio_id}/monitoring-runs",
    response_model=Page[MonitoringRunSummary],
    summary="List monitoring runs",
    description="Returns the portfolio's monitoring history, newest first.",
)
async def list_monitoring_runs(
    current_user: CurrentUser,
    service: EarlyWarningServiceDep,
    portfolio_id: uuid.UUID = PortfolioIdPath,
    limit: int = PageLimit,
    offset: int = PageOffset,
) -> Page[MonitoringRunSummary]:
    """List a portfolio's monitoring runs."""
    runs, total = await service.list_runs(
        portfolio_id=portfolio_id,
        user_id=current_user.id,
        limit=limit,
        offset=offset,
    )
    return Page[MonitoringRunSummary](
        items=[MonitoringRunSummary.model_validate(run) for run in runs],
        total=total,
        limit=limit,
        offset=offset,
    )


@runs_router.get(
    "/{run_id}",
    response_model=MonitoringRunResponse,
    summary="Get a monitoring run",
    description="Returns one run with its per-rule outcome, including any failures.",
)
async def get_monitoring_run(
    current_user: CurrentUser,
    service: EarlyWarningServiceDep,
    run_id: uuid.UUID = RunIdPath,
) -> MonitoringRunResponse:
    """Return one monitoring run."""
    run = await service.get_run(run_id=run_id, user_id=current_user.id)
    return _run_response(run)


def _run_response(run: MonitoringRun) -> MonitoringRunResponse:
    """Map a monitoring run into its API representation."""
    return MonitoringRunResponse(
        id=run.id,
        portfolio_id=run.portfolio_id,
        trigger_type=MonitoringTriggerType(run.trigger_type),
        status=MonitoringStatus(run.status),
        data_as_of=run.data_as_of,
        rules_evaluated=run.rules_evaluated,
        rules_failed=run.rules_failed,
        signals_created=run.signals_created,
        signals_updated=run.signals_updated,
        signals_resolved=run.signals_resolved,
        error_summary=run.error_summary,
        rule_results=[MonitoringRuleResult.model_validate(item) for item in run.rule_results],
        started_at=run.started_at,
        completed_at=run.completed_at,
    )


# --- Signals -----------------------------------------------------------------


@portfolio_router.get(
    "/{portfolio_id}/signals",
    response_model=Page[WarningSignalResponse],
    summary="List a portfolio's signals",
    description=(
        "Returns Gjallarhorn Signals for one portfolio, newest first. Filter by "
        "status, severity, type, creation date, and acknowledgement state. Resolved "
        "and dismissed signals are preserved and remain queryable."
    ),
)
async def list_portfolio_signals(
    current_user: CurrentUser,
    service: EarlyWarningServiceDep,
    session_signals: SignalRepositoryDep,
    portfolio_id: uuid.UUID = PortfolioIdPath,
    signal_status: list[SignalStatus] | None = StatusFilter,
    severity: list[SignalSeverity] | None = SeverityFilter,
    signal_type: list[RuleType] | None = TypeFilter,
    created_from: datetime | None = FromFilter,
    created_to: datetime | None = ToFilter,
    acknowledged: bool | None = AcknowledgedFilter,
    limit: int = PageLimit,
    offset: int = PageOffset,
) -> Page[WarningSignalResponse]:
    """List one portfolio's signals."""
    # Ownership is checked here and again in the query predicate.
    await service.severity_counts(portfolio_id=portfolio_id, user_id=current_user.id)

    return await _list_signals(
        signals=session_signals,
        user_id=current_user.id,
        portfolio_id=portfolio_id,
        signal_status=signal_status,
        severity=severity,
        signal_type=signal_type,
        created_from=created_from,
        created_to=created_to,
        acknowledged=acknowledged,
        limit=limit,
        offset=offset,
    )


@signals_router.get(
    "",
    response_model=Page[WarningSignalResponse],
    summary="List signals across portfolios",
    description="Returns the caller's signals across every portfolio they own.",
)
async def list_signals(
    current_user: CurrentUser,
    session_signals: SignalRepositoryDep,
    portfolio_id: uuid.UUID | None = PortfolioFilter,
    signal_status: list[SignalStatus] | None = StatusFilter,
    severity: list[SignalSeverity] | None = SeverityFilter,
    signal_type: list[RuleType] | None = TypeFilter,
    created_from: datetime | None = FromFilter,
    created_to: datetime | None = ToFilter,
    acknowledged: bool | None = AcknowledgedFilter,
    limit: int = PageLimit,
    offset: int = PageOffset,
) -> Page[WarningSignalResponse]:
    """List signals across the caller's portfolios."""
    return await _list_signals(
        signals=session_signals,
        user_id=current_user.id,
        portfolio_id=portfolio_id,
        signal_status=signal_status,
        severity=severity,
        signal_type=signal_type,
        created_from=created_from,
        created_to=created_to,
        acknowledged=acknowledged,
        limit=limit,
        offset=offset,
    )


async def _list_signals(
    *,
    signals: WarningSignalRepository,
    user_id: uuid.UUID,
    portfolio_id: uuid.UUID | None,
    signal_status: list[SignalStatus] | None,
    severity: list[SignalSeverity] | None,
    signal_type: list[RuleType] | None,
    created_from: datetime | None,
    created_to: datetime | None,
    acknowledged: bool | None,
    limit: int,
    offset: int,
) -> Page[WarningSignalResponse]:
    """Shared filtering, paging, and mapping for both signal listings."""
    statement = signals.filtered(
        user_id=user_id,
        portfolio_id=portfolio_id,
        statuses=[str(item) for item in signal_status] if signal_status else None,
        severities=[str(item) for item in severity] if severity else None,
        signal_types=[str(item) for item in signal_type] if signal_type else None,
        created_from=created_from,
        created_to=created_to,
        acknowledged=acknowledged,
    )

    rows = await signals.list_filtered(statement, limit=limit, offset=offset)
    total = await signals.count_filtered(statement)

    return Page[WarningSignalResponse](
        items=[_signal_response(signal, include_events=False) for signal in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@portfolio_router.get(
    "/{portfolio_id}/signals/summary",
    response_model=SignalSummaryResponse,
    summary="Open signal counts by severity",
    description="Counts of currently open signals, for the dashboard summary panel.",
)
async def signal_summary(
    current_user: CurrentUser,
    service: EarlyWarningServiceDep,
    portfolio_id: uuid.UUID = PortfolioIdPath,
) -> SignalSummaryResponse:
    """Return open signal counts by severity."""
    counts = await service.severity_counts(portfolio_id=portfolio_id, user_id=current_user.id)
    return SignalSummaryResponse(
        portfolio_id=portfolio_id,
        total_open=sum(counts.values()),
        by_severity=counts,
    )


@signals_router.get(
    "/{signal_id}",
    response_model=WarningSignalResponse,
    summary="Get a signal",
    description="Returns one signal with its append-only lifecycle audit trail.",
)
async def get_signal(
    current_user: CurrentUser,
    service: EarlyWarningServiceDep,
    signal_id: uuid.UUID = SignalIdPath,
) -> WarningSignalResponse:
    """Return one signal."""
    signal = await service.get_signal(signal_id=signal_id, user_id=current_user.id)
    return _signal_response(signal, include_events=True)


@signals_router.post(
    "/{signal_id}/acknowledge",
    response_model=WarningSignalResponse,
    summary="Acknowledge a signal",
    description=(
        "Records that the user has seen the signal. **Acknowledgement does not "
        "resolve it**: the condition is still present, and only the rule engine "
        "resolves a signal when its condition is no longer observed."
    ),
)
async def acknowledge_signal(
    current_user: CurrentUser,
    service: EarlyWarningServiceDep,
    signal_id: uuid.UUID = SignalIdPath,
) -> WarningSignalResponse:
    """Acknowledge a signal."""
    signal = await service.acknowledge(signal_id=signal_id, user_id=current_user.id)
    return _signal_response(signal, include_events=True)


@signals_router.post(
    "/{signal_id}/dismiss",
    response_model=WarningSignalResponse,
    summary="Dismiss a signal",
    description=(
        "Hides the signal without claiming its condition has cleared. If the same "
        "condition is observed again later, a new occurrence is created."
    ),
)
async def dismiss_signal(
    current_user: CurrentUser,
    service: EarlyWarningServiceDep,
    signal_id: uuid.UUID = SignalIdPath,
) -> WarningSignalResponse:
    """Dismiss a signal."""
    signal = await service.dismiss(signal_id=signal_id, user_id=current_user.id)
    return _signal_response(signal, include_events=True)


def _signal_response(signal: WarningSignal, *, include_events: bool) -> WarningSignalResponse:
    """Map a signal into its API representation."""
    context = dict(signal.context or {})
    limitations = context.pop("limitations", []) or []

    return WarningSignalResponse(
        id=signal.id,
        portfolio_id=signal.portfolio_id,
        alert_rule_id=signal.alert_rule_id,
        monitoring_run_id=signal.monitoring_run_id,
        signal_type=signal.signal_type,
        severity=SignalSeverity(signal.severity),
        severity_icon=SEVERITY_ICONS.get(signal.severity, "info-circle"),
        status=SignalStatus(signal.status),
        title=signal.title,
        explanation=signal.explanation,
        suggested_action=signal.suggested_action,
        metric_name=signal.metric_name,
        observed_value=signal.observed_value,
        threshold_value=signal.threshold_value,
        unit=signal.unit,
        analysis_period=signal.analysis_period,
        data_as_of=signal.data_as_of,
        context=context,
        limitations=list(limitations),
        first_triggered_at=signal.first_triggered_at,
        last_triggered_at=signal.last_triggered_at,
        acknowledged_at=signal.acknowledged_at,
        resolved_at=signal.resolved_at,
        dismissed_at=signal.dismissed_at,
        created_at=signal.created_at,
        events=(
            [SignalEventResponse.model_validate(event) for event in signal.events]
            if include_events
            else []
        ),
    )


# --- Scheduled monitoring ----------------------------------------------------


@internal_router.post(
    "/monitoring/run",
    response_model=ScheduledMonitoringResponse,
    summary="Run scheduled monitoring (protected)",
    description=(
        "Evaluates portfolios that have at least one enabled rule. Intended for a "
        "scheduler, not for users.\n\n"
        "Requires the configured scheduler secret in `X-Cron-Secret` or as a bearer "
        "token; the comparison is constant-time. The endpoint refuses to run when no "
        "secret is configured.\n\n"
        "**Idempotent** for one UTC evaluation period: a repeat call for the same "
        "portfolio and period returns the existing run instead of evaluating again. "
        "Work is **bounded** by `batch_size` and resumable through `cursor`, so it "
        "fits inside a serverless function's duration. A portfolio that fails is "
        "recorded and the batch continues.\n\n"
        "The response carries operational counts only — never portfolio names, "
        "holdings, or signal content."
    ),
    dependencies=[SchedulerGuard],
)
async def run_scheduled_monitoring(
    payload: ScheduledMonitoringRequest,
    service: EarlyWarningServiceDep,
    settings: SettingsDep,
    clock: ClockDep,
) -> ScheduledMonitoringResponse:
    """Run monitoring for a bounded batch of portfolios."""
    now = clock.now()
    # One evaluation period per UTC day: a retry on the same day is deduplicated.
    period = now.strftime("%Y-%m-%d")
    batch_size = payload.batch_size or settings.monitoring_batch_size

    portfolio_ids = await service.eligible_portfolio_ids(limit=batch_size, after=payload.cursor)

    results: list[ScheduledPortfolioResult] = []
    failed = 0
    skipped = 0

    for portfolio_id in portfolio_ids:
        try:
            outcome = await service.run_monitoring(
                portfolio_id=portfolio_id,
                user_id=None,
                trigger_type=MonitoringTriggerType.SCHEDULED,
                idempotency_key=f"scheduled:{period}",
            )
        except MonitoringAlreadyRunningError:
            skipped += 1
            results.append(
                ScheduledPortfolioResult(portfolio_id=portfolio_id, status="already_running")
            )
            continue
        except Exception:
            failed += 1
            results.append(ScheduledPortfolioResult(portfolio_id=portfolio_id, status="failed"))
            continue

        if outcome.deduplicated:
            # An equivalent run already covered this period, so this invocation did
            # no work. Reporting the stored run's counts here would double-count
            # them across retries.
            skipped += 1
            results.append(
                ScheduledPortfolioResult(portfolio_id=portfolio_id, status="deduplicated")
            )
            continue

        results.append(
            ScheduledPortfolioResult(
                portfolio_id=portfolio_id,
                status=outcome.run.status,
                signals_created=outcome.run.signals_created,
                signals_updated=outcome.run.signals_updated,
                signals_resolved=outcome.run.signals_resolved,
            )
        )

    return ScheduledMonitoringResponse(
        evaluated_at=now,
        evaluation_period=period,
        portfolios_processed=len(results) - failed - skipped,
        portfolios_failed=failed,
        portfolios_skipped=skipped,
        signals_created=sum(item.signals_created for item in results),
        signals_updated=sum(item.signals_updated for item in results),
        signals_resolved=sum(item.signals_resolved for item in results),
        next_cursor=portfolio_ids[-1] if len(portfolio_ids) == batch_size else None,
        results=results,
    )
