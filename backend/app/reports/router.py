"""Report endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Path, Query, Response, status

from app.auth.dependencies import CurrentUser
from app.common.schemas import DEFAULT_PAGE_LIMIT, MAX_PAGE_LIMIT, Page
from app.config import API_V1_PREFIX
from app.reports.dependencies import ReportServiceDep
from app.reports.models import Report, ReportStatus
from app.reports.schemas import ReportCreateRequest, ReportResponse
from app.reports.service import ReportRequest

portfolio_router = APIRouter(prefix="/portfolios", tags=["reports"])
reports_router = APIRouter(prefix="/reports", tags=["reports"])

PortfolioIdPath = Path(description="Portfolio identifier.")
ReportIdPath = Path(description="Report identifier.")
PageLimit = Query(default=DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT)
PageOffset = Query(default=0, ge=0)


@portfolio_router.post(
    "/{portfolio_id}/reports",
    response_model=ReportResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generate a risk report",
    description=(
        "Generates a Heimdall Risk Report as a PDF and stores it.\n\n"
        "The report is assembled from **stored** analysis inputs — an analysis run, "
        "recent stress tests, and recent signals — and records those identifiers in "
        "`inputs`, so the same document can be reproduced later.\n\n"
        "Omitting `analysis_run_id` reuses the portfolio's most recent analysis, and "
        "computes one only if none exists. A failure marks the report `failed` and "
        "leaves every analysis, stress test, and signal untouched."
    ),
)
async def create_report(
    payload: ReportCreateRequest,
    current_user: CurrentUser,
    service: ReportServiceDep,
    portfolio_id: uuid.UUID = PortfolioIdPath,
) -> ReportResponse:
    """Generate a report."""
    report = await service.generate(
        portfolio_id=portfolio_id,
        user_id=current_user.id,
        request=ReportRequest(
            analysis_run_id=payload.analysis_run_id,
            include_stress_tests=payload.include_stress_tests,
            include_signals=payload.include_signals,
            title=payload.title,
        ),
    )
    return _report_response(report)


@portfolio_router.get(
    "/{portfolio_id}/reports",
    response_model=Page[ReportResponse],
    summary="List reports",
    description="Returns the portfolio's generated reports, newest first.",
)
async def list_reports(
    current_user: CurrentUser,
    service: ReportServiceDep,
    portfolio_id: uuid.UUID = PortfolioIdPath,
    limit: int = PageLimit,
    offset: int = PageOffset,
) -> Page[ReportResponse]:
    """List a portfolio's reports."""
    reports, total = await service.list_for_portfolio(
        portfolio_id=portfolio_id,
        user_id=current_user.id,
        limit=limit,
        offset=offset,
    )
    return Page[ReportResponse](
        items=[_report_response(report) for report in reports],
        total=total,
        limit=limit,
        offset=offset,
    )


@reports_router.get(
    "/{report_id}",
    response_model=ReportResponse,
    summary="Get report metadata",
    description="Returns a report's status and the inputs it was built from.",
)
async def get_report(
    current_user: CurrentUser,
    service: ReportServiceDep,
    report_id: uuid.UUID = ReportIdPath,
) -> ReportResponse:
    """Return one report's metadata."""
    report = await service.get(report_id=report_id, user_id=current_user.id)
    return _report_response(report)


@reports_router.get(
    "/{report_id}/download",
    summary="Download a report",
    description=(
        "Returns the rendered PDF. Only the account that generated the report can download it."
    ),
    responses={
        200: {
            "content": {"application/pdf": {}},
            "description": "The rendered report.",
        }
    },
)
async def download_report(
    current_user: CurrentUser,
    service: ReportServiceDep,
    report_id: uuid.UUID = ReportIdPath,
) -> Response:
    """Download a report's rendered bytes."""
    report = await service.get_downloadable(report_id=report_id, user_id=current_user.id)

    return Response(
        content=report.content,
        media_type=report.content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{report.filename}"',
            # Reports contain portfolio data, so no shared cache may retain them.
            "Cache-Control": "private, no-store",
        },
    )


def _report_response(report: Report) -> ReportResponse:
    """Map a report into its API representation."""
    return ReportResponse(
        id=report.id,
        portfolio_id=report.portfolio_id,
        analysis_run_id=report.analysis_run_id,
        title=report.title,
        format=report.format,
        status=report.status,
        error_message=report.error_message,
        inputs=report.inputs,
        size_bytes=report.size_bytes,
        filename=report.filename,
        download_url=(
            f"{API_V1_PREFIX}/reports/{report.id}/download"
            if report.status == ReportStatus.SUCCEEDED
            else None
        ),
        created_at=report.created_at,
        completed_at=report.completed_at,
    )
