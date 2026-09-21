"""Portfolio and position endpoints.

Routes stay thin: they validate input, resolve the authenticated user, call a
service, and map the result into a response schema. Ownership is enforced inside
the services, which scope every query by `user_id`.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi import APIRouter, File, Form, Path, Query, Response, UploadFile, status

from app.auth.dependencies import CurrentUser
from app.common.schemas import DEFAULT_PAGE_LIMIT, MAX_PAGE_LIMIT, Page
from app.portfolios.csv_import import MAX_FILE_BYTES, MAX_ROWS, ImportMode
from app.portfolios.dependencies import (
    PortfolioServiceDep,
    PositionImportServiceDep,
    PositionServiceDep,
)
from app.portfolios.import_service import CsvImportError
from app.portfolios.models import Portfolio, Position
from app.portfolios.schemas import (
    AssetResponse,
    ImportSummaryResponse,
    PortfolioCreateRequest,
    PortfolioDetailResponse,
    PortfolioResponse,
    PortfolioUpdateRequest,
    PositionCreateRequest,
    PositionResponse,
    PositionUpdateRequest,
)
from app.portfolios.service import PortfolioWithCount

router = APIRouter(prefix="/portfolios", tags=["portfolios"])

PortfolioId = Path(description="Portfolio identifier.")
PositionId = Path(description="Position identifier.")
CsvUpload = File(description="UTF-8 CSV file of holdings.")
ImportModeForm = Form(default=ImportMode.MERGE, description="merge, replace, or reject.")


def _position_response(position: Position, *, base_currency: str) -> PositionResponse:
    """Map a position to its API representation."""
    return PositionResponse(
        id=position.id,
        portfolio_id=position.portfolio_id,
        asset=AssetResponse.model_validate(position.asset),
        quantity=position.quantity,
        average_cost=position.average_cost,
        cost_basis=position.quantity * position.average_cost,
        currency=base_currency,
        purchase_date=position.purchase_date,
        created_at=position.created_at,
        updated_at=position.updated_at,
    )


def _portfolio_response(entry: PortfolioWithCount) -> PortfolioResponse:
    portfolio = entry.portfolio
    return PortfolioResponse(
        id=portfolio.id,
        name=portfolio.name,
        description=portfolio.description,
        base_currency=portfolio.base_currency,
        benchmark_symbol=portfolio.benchmark_symbol,
        position_count=entry.position_count,
        created_at=portfolio.created_at,
        updated_at=portfolio.updated_at,
    )


def _portfolio_detail_response(portfolio: Portfolio) -> PortfolioDetailResponse:
    positions = sorted(portfolio.positions, key=lambda p: p.asset.symbol)
    mapped = [_position_response(p, base_currency=portfolio.base_currency) for p in positions]
    return PortfolioDetailResponse(
        id=portfolio.id,
        name=portfolio.name,
        description=portfolio.description,
        base_currency=portfolio.base_currency,
        benchmark_symbol=portfolio.benchmark_symbol,
        position_count=len(mapped),
        created_at=portfolio.created_at,
        updated_at=portfolio.updated_at,
        positions=mapped,
        total_cost_basis=sum((p.cost_basis for p in mapped), Decimal("0")),
    )


# --- Portfolios --------------------------------------------------------------


@router.post(
    "",
    response_model=PortfolioResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a portfolio",
)
async def create_portfolio(
    payload: PortfolioCreateRequest,
    current_user: CurrentUser,
    service: PortfolioServiceDep,
) -> PortfolioResponse:
    """Create a portfolio owned by the authenticated user."""
    portfolio = await service.create(
        user_id=current_user.id,
        name=payload.name,
        description=payload.description,
        base_currency=payload.base_currency,
        benchmark_symbol=payload.benchmark_symbol,
    )
    return _portfolio_response(PortfolioWithCount(portfolio=portfolio, position_count=0))


@router.get(
    "",
    response_model=Page[PortfolioResponse],
    summary="List portfolios",
    description="Returns the authenticated user's portfolios, newest first.",
)
async def list_portfolios(
    current_user: CurrentUser,
    service: PortfolioServiceDep,
    limit: int = Query(default=DEFAULT_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT),
    offset: int = Query(default=0, ge=0),
) -> Page[PortfolioResponse]:
    """List the user's portfolios."""
    page = await service.list_for_user(user_id=current_user.id, limit=limit, offset=offset)
    return Page[PortfolioResponse](
        items=[_portfolio_response(entry) for entry in page.items],
        total=page.total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{portfolio_id}",
    response_model=PortfolioDetailResponse,
    summary="Get a portfolio",
    description=(
        "Returns a portfolio with its holdings. `total_cost_basis` is acquisition "
        "cost, not market value: valuation requires market data."
    ),
)
async def get_portfolio(
    current_user: CurrentUser,
    service: PortfolioServiceDep,
    portfolio_id: uuid.UUID = PortfolioId,
) -> PortfolioDetailResponse:
    """Return one portfolio and its positions."""
    portfolio = await service.get_with_positions(
        portfolio_id=portfolio_id,
        user_id=current_user.id,
    )
    return _portfolio_detail_response(portfolio)


@router.patch(
    "/{portfolio_id}",
    response_model=PortfolioResponse,
    summary="Update a portfolio",
    description=(
        "Partial update. Only the fields present in the request body are changed. "
        "`base_currency` cannot be changed, because stored positions depend on it."
    ),
)
async def update_portfolio(
    payload: PortfolioUpdateRequest,
    current_user: CurrentUser,
    service: PortfolioServiceDep,
    portfolio_id: uuid.UUID = PortfolioId,
) -> PortfolioResponse:
    """Update a portfolio's mutable fields."""
    entry = await service.update(
        portfolio_id=portfolio_id,
        user_id=current_user.id,
        fields=payload.model_dump(exclude_unset=True),
    )
    return _portfolio_response(entry)


@router.delete(
    "/{portfolio_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a portfolio",
    description="Deletes the portfolio and every position it contains. Not reversible.",
)
async def delete_portfolio(
    current_user: CurrentUser,
    service: PortfolioServiceDep,
    portfolio_id: uuid.UUID = PortfolioId,
) -> Response:
    """Delete a portfolio."""
    await service.delete(portfolio_id=portfolio_id, user_id=current_user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Positions ---------------------------------------------------------------


@router.get(
    "/{portfolio_id}/positions",
    response_model=list[PositionResponse],
    summary="List holdings",
)
async def list_positions(
    current_user: CurrentUser,
    portfolio_service: PortfolioServiceDep,
    position_service: PositionServiceDep,
    portfolio_id: uuid.UUID = PortfolioId,
) -> list[PositionResponse]:
    """List every holding in a portfolio."""
    entry = await portfolio_service.get(portfolio_id=portfolio_id, user_id=current_user.id)
    positions = await position_service.list_for_portfolio(
        portfolio_id=portfolio_id,
        user_id=current_user.id,
    )
    return [_position_response(p, base_currency=entry.portfolio.base_currency) for p in positions]


@router.post(
    "/{portfolio_id}/positions",
    response_model=PositionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a holding",
    description=(
        "Adds a position. A portfolio holds at most one position per asset: "
        "`on_duplicate=reject` (the default) fails with 409, while "
        "`on_duplicate=merge` adds the quantities and recomputes the "
        "weighted-average cost."
    ),
)
async def add_position(
    payload: PositionCreateRequest,
    current_user: CurrentUser,
    portfolio_service: PortfolioServiceDep,
    position_service: PositionServiceDep,
    portfolio_id: uuid.UUID = PortfolioId,
) -> PositionResponse:
    """Add a holding to a portfolio."""
    position = await position_service.add(
        portfolio_id=portfolio_id,
        user_id=current_user.id,
        symbol=payload.symbol,
        quantity=payload.quantity,
        average_cost=payload.average_cost,
        purchase_date=payload.purchase_date,
        on_duplicate=payload.on_duplicate,
    )
    entry = await portfolio_service.get(portfolio_id=portfolio_id, user_id=current_user.id)
    return _position_response(position, base_currency=entry.portfolio.base_currency)


@router.patch(
    "/{portfolio_id}/positions/{position_id}",
    response_model=PositionResponse,
    summary="Update a holding",
    description=(
        "Partial update of quantity, average cost, or purchase date. The asset "
        "cannot be changed; delete the position and add the correct one instead."
    ),
)
async def update_position(
    payload: PositionUpdateRequest,
    current_user: CurrentUser,
    portfolio_service: PortfolioServiceDep,
    position_service: PositionServiceDep,
    portfolio_id: uuid.UUID = PortfolioId,
    position_id: uuid.UUID = PositionId,
) -> PositionResponse:
    """Update a holding."""
    position = await position_service.update(
        portfolio_id=portfolio_id,
        position_id=position_id,
        user_id=current_user.id,
        fields=payload.model_dump(exclude_unset=True),
    )
    entry = await portfolio_service.get(portfolio_id=portfolio_id, user_id=current_user.id)
    return _position_response(position, base_currency=entry.portfolio.base_currency)


@router.delete(
    "/{portfolio_id}/positions/{position_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a holding",
)
async def delete_position(
    current_user: CurrentUser,
    service: PositionServiceDep,
    portfolio_id: uuid.UUID = PortfolioId,
    position_id: uuid.UUID = PositionId,
) -> Response:
    """Remove a holding from a portfolio."""
    await service.delete(
        portfolio_id=portfolio_id,
        position_id=position_id,
        user_id=current_user.id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- CSV import --------------------------------------------------------------


@router.post(
    "/{portfolio_id}/positions/import",
    response_model=ImportSummaryResponse,
    summary="Import holdings from a CSV file",
    description=(
        "Uploads a CSV file of holdings as `multipart/form-data`. "
        "Expected header: `symbol,quantity,average_cost,purchase_date`. "
        "`purchase_date` is optional, as a column and as a value. "
        "The file is validated in full before anything is written, and the whole "
        "import runs in one transaction: a rejected file leaves the portfolio "
        "exactly as it was. Errors identify the line and column at fault. "
        "Modes: `merge` (default) combines each row with a matching holding; "
        "`replace` deletes every existing holding first; `reject` fails if any "
        "imported symbol is already held."
    ),
)
async def import_positions(
    current_user: CurrentUser,
    portfolio_service: PortfolioServiceDep,
    import_service: PositionImportServiceDep,
    portfolio_id: uuid.UUID = PortfolioId,
    file: UploadFile = CsvUpload,
    mode: ImportMode = ImportModeForm,
) -> ImportSummaryResponse:
    """Import holdings from an uploaded CSV file."""
    payload = await _read_upload(file)

    summary = await import_service.import_csv(
        portfolio_id=portfolio_id,
        user_id=current_user.id,
        payload=payload,
        mode=mode,
    )

    portfolio = await portfolio_service.get_with_positions(
        portfolio_id=portfolio_id,
        user_id=current_user.id,
    )
    detail = _portfolio_detail_response(portfolio)

    return ImportSummaryResponse(
        mode=str(summary.mode),
        rows_read=summary.rows_read,
        positions_created=summary.positions_created,
        positions_merged=summary.positions_merged,
        positions_removed=summary.positions_removed,
        position_count=detail.position_count,
        positions=detail.positions,
        total_cost_basis=detail.total_cost_basis,
    )


async def _read_upload(file: UploadFile) -> bytes:
    """Read an upload, refusing to buffer more than the documented limit.

    `Content-Length` can be absent or wrong, so the bytes are counted as they
    arrive rather than trusted from a header.
    """
    chunks: list[bytes] = []
    total = 0
    while chunk := await file.read(64 * 1024):
        total += len(chunk)
        if total > MAX_FILE_BYTES:
            raise CsvImportError(
                f"The uploaded file exceeds the maximum size of {MAX_FILE_BYTES} bytes. "
                f"A file may contain at most {MAX_ROWS} holdings.",
                code="csv_file_too_large",
            )
        chunks.append(chunk)
    return b"".join(chunks)
