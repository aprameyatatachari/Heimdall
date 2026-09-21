"""CSV import use case.

The whole import runs inside the request's single transaction. Validation happens
before any write, so a rejected file leaves the database untouched.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.service import AssetService
from app.common.errors import ErrorDetail, ValidationError
from app.common.logging import get_logger
from app.portfolios.csv_import import (
    CsvStructureError,
    ImportMode,
    ParsedRow,
    RowError,
    parse_positions_csv,
)
from app.portfolios.models import Portfolio, Position
from app.portfolios.repository import PortfolioRepository, PositionRepository
from app.portfolios.service import (
    COST_QUANTIZE,
    MAX_POSITIONS_PER_PORTFOLIO,
    PortfolioNotFoundError,
)

logger = get_logger(__name__)


class CsvImportError(ValidationError):
    """The uploaded file was rejected. Nothing was written."""

    code = "csv_import_failed"
    message = "The uploaded file could not be imported. No changes were made."


class CsvImportConflictError(ValidationError):
    """The file conflicts with holdings the portfolio already has."""

    code = "csv_import_conflict"
    message = "The uploaded file conflicts with existing holdings. No changes were made."


@dataclass(frozen=True, slots=True)
class ImportSummary:
    """What an import did."""

    mode: ImportMode
    rows_read: int
    positions_created: int
    positions_merged: int
    positions_removed: int
    portfolio: Portfolio


class PositionImportService:
    """Imports holdings from a CSV file into one portfolio."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        portfolios: PortfolioRepository,
        positions: PositionRepository,
        assets: AssetService,
    ) -> None:
        self._session = session
        self._portfolios = portfolios
        self._positions = positions
        self._assets = assets

    async def import_csv(
        self,
        *,
        portfolio_id: uuid.UUID,
        user_id: uuid.UUID,
        payload: bytes,
        mode: ImportMode,
    ) -> ImportSummary:
        """Validate a file completely, then apply it in one transaction."""
        portfolio = await self._portfolios.get_owned(portfolio_id, user_id)
        if portfolio is None:
            raise PortfolioNotFoundError()

        try:
            parsed = parse_positions_csv(payload)
        except CsvStructureError as exc:
            raise CsvImportError(exc.message, code=exc.code) from exc

        if not parsed.ok:
            raise CsvImportError(
                "The uploaded file contains errors. No changes were made.",
                details=_to_error_details(parsed.errors),
            )

        existing = {
            position.asset_id: position
            for position in await self._positions.list_for_portfolio(portfolio.id)
        }

        # Resolve every symbol before writing, so an unknown currency or an
        # invalid symbol aborts the import before it changes anything.
        resolved: list[tuple[ParsedRow, uuid.UUID]] = []
        for row in parsed.rows:
            asset = await self._assets.resolve_or_create(
                raw_symbol=row.symbol,
                currency=portfolio.base_currency,
            )
            resolved.append((row, asset.id))

        if mode is ImportMode.REJECT:
            self._reject_on_conflict(resolved, existing)

        # Check the resulting size before writing anything.
        if mode is ImportMode.REPLACE:
            prospective = len(resolved)
        else:
            prospective = len(existing) + sum(
                1 for _, asset_id in resolved if asset_id not in existing
            )
        if prospective > MAX_POSITIONS_PER_PORTFOLIO:
            raise CsvImportError(
                f"The import would leave {prospective} holdings in this portfolio, more "
                f"than the maximum of {MAX_POSITIONS_PER_PORTFOLIO}. No changes were made.",
                code="csv_position_limit_exceeded",
            )

        removed = 0
        if mode is ImportMode.REPLACE:
            removed = await self._remove_all(portfolio.id)
            existing = {}

        created, merged = await self._apply(
            portfolio=portfolio,
            resolved=resolved,
            existing=existing,
            mode=mode,
        )

        await self._session.flush()

        logger.info(
            "csv_import_completed",
            portfolio_id=str(portfolio.id),
            mode=str(mode),
            rows=len(parsed.rows),
            created=created,
            merged=merged,
            removed=removed,
        )

        return ImportSummary(
            mode=mode,
            rows_read=len(parsed.rows),
            positions_created=created,
            positions_merged=merged,
            positions_removed=removed,
            portfolio=portfolio,
        )

    # --- Internals -----------------------------------------------------------

    def _reject_on_conflict(
        self,
        resolved: list[tuple[ParsedRow, uuid.UUID]],
        existing: dict[uuid.UUID, Position],
    ) -> None:
        """Fail when any imported symbol is already held."""
        conflicts = [
            ErrorDetail(
                field="symbol",
                row=row.line,
                message=(
                    f"{row.symbol} is already held in this portfolio. "
                    "Retry with mode=merge to combine, or mode=replace to overwrite."
                ),
                code="already_held",
            )
            for row, asset_id in resolved
            if asset_id in existing
        ]
        if conflicts:
            raise CsvImportConflictError(details=conflicts)

    async def _remove_all(self, portfolio_id: uuid.UUID) -> int:
        """Delete every position in the portfolio, for replace mode."""
        positions = await self._positions.list_for_portfolio(portfolio_id)
        for position in positions:
            await self._positions.delete(position)
        # Flush the deletes before inserting, so the unique constraint on
        # (portfolio_id, asset_id) cannot fire against rows that are on their way out.
        await self._session.flush()
        return len(positions)

    async def _apply(
        self,
        *,
        portfolio: Portfolio,
        resolved: list[tuple[ParsedRow, uuid.UUID]],
        existing: dict[uuid.UUID, Position],
        mode: ImportMode,
    ) -> tuple[int, int]:
        """Insert or merge each row. Returns (created, merged)."""
        created = 0
        merged = 0

        for row, asset_id in resolved:
            current = existing.get(asset_id)

            if current is None:
                self._positions.add(
                    Position(
                        portfolio_id=portfolio.id,
                        asset_id=asset_id,
                        quantity=row.quantity,
                        average_cost=row.average_cost,
                        purchase_date=row.purchase_date,
                    )
                )
                created += 1
                continue

            if mode is ImportMode.MERGE:
                _merge_into(current, row)
                merged += 1

        return created, merged


def _merge_into(position: Position, row: ParsedRow) -> None:
    """Combine an imported row into an existing holding.

    Quantities add. The new average cost is the cost-weighted mean:

        (q_old * c_old + q_new * c_new) / (q_old + q_new)

    The earlier of the two purchase dates is kept, because that is when the
    holding began.
    """
    total_quantity = position.quantity + row.quantity
    total_cost = position.quantity * position.average_cost + row.quantity * row.average_cost

    position.quantity = total_quantity
    position.average_cost = (total_cost / total_quantity).quantize(COST_QUANTIZE)

    if row.purchase_date is not None:
        position.purchase_date = (
            row.purchase_date
            if position.purchase_date is None
            else min(position.purchase_date, row.purchase_date)
        )


def _to_error_details(errors: list[RowError]) -> list[ErrorDetail]:
    """Map row errors onto the API's error-detail shape."""
    return [
        ErrorDetail(
            field=error.column,
            row=error.line,
            message=error.message,
            code=error.code,
        )
        for error in errors
    ]


__all__ = [
    "CsvImportConflictError",
    "CsvImportError",
    "ImportSummary",
    "PositionImportService",
]
