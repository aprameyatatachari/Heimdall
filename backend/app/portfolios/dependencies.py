"""Portfolio and position service wiring."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from app.assets.repository import AssetRepository
from app.assets.service import AssetService
from app.common.dependencies import SessionDep
from app.portfolios.import_service import PositionImportService
from app.portfolios.repository import PortfolioRepository, PositionRepository
from app.portfolios.service import PortfolioService, PositionService


def get_portfolio_service(session: SessionDep) -> PortfolioService:
    """Build the portfolio service for this request."""
    return PortfolioService(session=session, portfolios=PortfolioRepository(session))


def get_position_service(session: SessionDep) -> PositionService:
    """Build the position service for this request."""
    return PositionService(
        session=session,
        portfolios=PortfolioRepository(session),
        positions=PositionRepository(session),
        assets=AssetService(session=session, assets=AssetRepository(session)),
    )


def get_position_import_service(session: SessionDep) -> PositionImportService:
    """Build the CSV import service for this request."""
    return PositionImportService(
        session=session,
        portfolios=PortfolioRepository(session),
        positions=PositionRepository(session),
        assets=AssetService(session=session, assets=AssetRepository(session)),
    )


PortfolioServiceDep = Annotated[PortfolioService, Depends(get_portfolio_service)]
PositionImportServiceDep = Annotated[PositionImportService, Depends(get_position_import_service)]
PositionServiceDep = Annotated[PositionService, Depends(get_position_service)]
