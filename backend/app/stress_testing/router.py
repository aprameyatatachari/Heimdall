"""Stress-testing endpoints."""

from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi import APIRouter, Path, Query, status

from app.auth.dependencies import CurrentUser
from app.common.disclaimer import DISCLAIMER
from app.common.schemas import DEFAULT_PAGE_LIMIT, MAX_PAGE_LIMIT, Page
from app.stress_testing.dependencies import StressTestingServiceDep
from app.stress_testing.models import StressTestRun
from app.stress_testing.scenarios import Shock, ShockTargetType, ShockType
from app.stress_testing.schemas import (
    PositionImpactResponse,
    ScenarioCatalogueItem,
    ScenarioCatalogueResponse,
    StressTestRequest,
    StressTestRunResponse,
    StressTestRunSummary,
)
from app.stress_testing.service import CustomScenario

scenarios_router = APIRouter(prefix="/stress-scenarios", tags=["stress testing"])
portfolio_router = APIRouter(prefix="/portfolios", tags=["stress testing"])
runs_router = APIRouter(prefix="/stress-tests", tags=["stress testing"])

PortfolioIdPath = Path(description="Portfolio identifier.")
RunIdPath = Path(description="Stress-test run identifier.")
PageLimit = Query(default=DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT)
PageOffset = Query(default=0, ge=0)


@scenarios_router.get(
    "",
    response_model=ScenarioCatalogueResponse,
    summary="List historical stress scenarios",
    description=(
        "Returns the catalogue of historical scenarios with their exact date ranges. "
        "A historical scenario replays each asset's observed return over that window "
        "against the portfolio's current holdings."
    ),
)
async def list_scenarios(
    current_user: CurrentUser,
    service: StressTestingServiceDep,
) -> ScenarioCatalogueResponse:
    """Return the historical scenario catalogue."""
    del current_user
    return ScenarioCatalogueResponse(
        items=[
            ScenarioCatalogueItem(
                key=scenario.key,
                name=scenario.name,
                description=scenario.description,
                start=scenario.start,
                end=scenario.end,
                window=scenario.trading_window,
            )
            for scenario in service.list_scenarios()
        ]
    )


@portfolio_router.post(
    "/{portfolio_id}/stress-tests",
    response_model=StressTestRunResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Run a stress test",
    description=(
        "Runs one scenario against the portfolio's current holdings and stores the "
        "result with its full scenario definition. Provide exactly one of "
        "`scenario_key` (a catalogue entry) or `custom` (an explicit shock set). "
        "**Shock precedence:** a shock on a symbol overrides one on that symbol's "
        "sector, which overrides a portfolio-wide shock. Holdings with no usable "
        "price data are listed under `excluded_symbols` and left out of the estimate "
        "rather than treated as unchanged."
    ),
)
async def run_stress_test(
    payload: StressTestRequest,
    current_user: CurrentUser,
    service: StressTestingServiceDep,
    portfolio_id: uuid.UUID = PortfolioIdPath,
) -> StressTestRunResponse:
    """Run a stress test."""
    if payload.scenario_key is not None:
        run = await service.run_historical(
            portfolio_id=portfolio_id,
            user_id=current_user.id,
            scenario_key=payload.scenario_key,
        )
        return _run_response(run)

    custom = payload.custom
    if custom is None:  # pragma: no cover - the schema guarantees one of the two
        raise ValueError("A scenario is required.")

    run = await service.run_hypothetical(
        portfolio_id=portfolio_id,
        user_id=current_user.id,
        scenario=CustomScenario(
            name=custom.name,
            shocks=[
                Shock(
                    target_type=ShockTargetType(shock.target_type),
                    target=shock.target,
                    shock_type=ShockType(shock.shock_type),
                    value=shock.value,
                )
                for shock in custom.shocks
            ],
        ),
    )
    return _run_response(run)


@portfolio_router.get(
    "/{portfolio_id}/stress-tests",
    response_model=Page[StressTestRunSummary],
    summary="List stress tests",
    description="Returns a portfolio's stored stress tests, newest first.",
)
async def list_stress_tests(
    current_user: CurrentUser,
    service: StressTestingServiceDep,
    portfolio_id: uuid.UUID = PortfolioIdPath,
    limit: int = PageLimit,
    offset: int = PageOffset,
) -> Page[StressTestRunSummary]:
    """List a portfolio's stress tests."""
    runs, total = await service.list_runs(
        portfolio_id=portfolio_id,
        user_id=current_user.id,
        limit=limit,
        offset=offset,
    )
    return Page[StressTestRunSummary](
        items=[StressTestRunSummary.model_validate(run) for run in runs],
        total=total,
        limit=limit,
        offset=offset,
    )


@runs_router.get(
    "/{run_id}",
    response_model=StressTestRunResponse,
    summary="Get a stress test",
    description="Returns a stored stress test with its position-level breakdown.",
)
async def get_stress_test(
    current_user: CurrentUser,
    service: StressTestingServiceDep,
    run_id: uuid.UUID = RunIdPath,
) -> StressTestRunResponse:
    """Return one stored stress test."""
    run = await service.get_run(run_id=run_id, user_id=current_user.id)
    return _run_response(run)


def _run_response(run: StressTestRun) -> StressTestRunResponse:
    """Map a stored run into its API representation."""
    payload = run.result or {}

    return StressTestRunResponse(
        id=run.id,
        portfolio_id=run.portfolio_id,
        scenario_type=run.scenario_type,
        scenario_name=run.scenario_name,
        scenario_definition=run.scenario_definition,
        status=run.status,
        data_as_of=run.data_as_of,
        currency=str(payload.get("currency", "USD")),
        starting_value=run.starting_value or Decimal("0"),
        ending_value=run.ending_value or Decimal("0"),
        total_impact=run.total_impact or Decimal("0"),
        total_impact_percent=run.total_impact_percent or Decimal("0"),
        positions=[
            PositionImpactResponse(
                symbol=position["symbol"],
                sector=position["sector"],
                starting_value=Decimal(position["starting_value"]),
                applied_return=Decimal(position["applied_return"]),
                return_source=position["return_source"],
                ending_value=Decimal(position["ending_value"]),
                impact=Decimal(position["impact"]),
                impact_percent=Decimal(position["impact_percent"]),
                contribution_to_loss=(
                    None
                    if position["contribution_to_loss"] is None
                    else Decimal(position["contribution_to_loss"])
                ),
            )
            for position in payload.get("positions", [])
        ],
        excluded_symbols=list(payload.get("excluded_symbols", [])),
        reconciles=bool(payload.get("reconciles", False)),
        limitations=list(payload.get("limitations", [])),
        disclaimer=DISCLAIMER,
        created_at=run.created_at,
        completed_at=run.completed_at,
    )
