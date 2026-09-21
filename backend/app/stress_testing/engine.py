"""The stress-testing engine.

Pure functions: given per-holding values and per-holding returns, produce a
position-level impact breakdown that reconciles exactly with the portfolio total.

Decimal arithmetic throughout, because these are monetary amounts.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Final

from app.stress_testing.scenarios import Shock, ShockTargetType

# Impacts are rounded to the cent for presentation; the reconciliation check runs
# on the rounded values, so what a user sees adds up.
MONEY_QUANTUM: Final = Decimal("0.01")
RECONCILIATION_TOLERANCE: Final = Decimal("0.01")


@dataclass(frozen=True, slots=True)
class HoldingInput:
    """One holding, as the engine needs it."""

    symbol: str
    sector: str
    market_value: Decimal


@dataclass(frozen=True, slots=True)
class PositionImpact:
    """The estimated effect of a scenario on one holding."""

    symbol: str
    sector: str
    starting_value: Decimal
    # The return applied, as a fraction.
    applied_return: Decimal
    # How the return was arrived at, for explainability.
    source: str
    ending_value: Decimal
    impact: Decimal
    impact_percent: Decimal
    # Share of the portfolio's total loss. Only meaningful when the total is a loss.
    contribution_to_loss: Decimal | None


@dataclass(frozen=True, slots=True)
class StressTestResult:
    """A complete scenario outcome."""

    starting_value: Decimal
    ending_value: Decimal
    total_impact: Decimal
    total_impact_percent: Decimal
    impacts: list[PositionImpact]
    # Holdings excluded because no return could be determined for them.
    excluded_symbols: list[str]

    @property
    def is_loss(self) -> bool:
        """True when the scenario reduces portfolio value."""
        return self.total_impact < 0

    def reconciles(self) -> bool:
        """True when the position impacts sum to the portfolio impact.

        Checked on the rounded figures that are actually presented, so the table a
        user reads adds up to the headline number.
        """
        summed = sum((impact.impact for impact in self.impacts), Decimal("0"))
        return abs(summed - self.total_impact) <= RECONCILIATION_TOLERANCE


def resolve_shock(
    *,
    symbol: str,
    sector: str,
    shocks: list[Shock],
) -> Shock | None:
    """Pick the shock that applies to one holding.

    Precedence is strict and documented: a shock on the **symbol** overrides one on
    its **sector**, which overrides a **portfolio**-wide shock. When two shocks of
    the same specificity target the same holding, the later one in the list wins,
    so a caller can override an earlier entry predictably.
    """
    best: Shock | None = None

    for shock in shocks:
        if not _applies(shock, symbol=symbol, sector=sector):
            continue
        if best is None or shock.precedence <= best.precedence:
            best = shock

    return best


def _applies(shock: Shock, *, symbol: str, sector: str) -> bool:
    """Whether a shock targets this holding at all."""
    if shock.target_type is ShockTargetType.PORTFOLIO:
        return True
    if shock.target is None:
        return False
    if shock.target_type is ShockTargetType.SYMBOL:
        return shock.target.upper() == symbol.upper()
    return shock.target.casefold() == sector.casefold()


def apply_returns(
    holdings: list[HoldingInput],
    *,
    returns: dict[str, Decimal],
    sources: dict[str, str],
    excluded: list[str] | None = None,
) -> StressTestResult:
    """Apply a per-symbol return to each holding and reconcile the totals.

    A holding with no entry in `returns` is excluded rather than assumed flat: a
    zero would silently understate the scenario's effect.
    """
    impacts: list[PositionImpact] = []
    excluded_symbols = list(excluded or [])

    starting_total = Decimal("0")
    for holding in holdings:
        applied = returns.get(holding.symbol)
        if applied is None:
            if holding.symbol not in excluded_symbols:
                excluded_symbols.append(holding.symbol)
            continue

        starting = holding.market_value.quantize(MONEY_QUANTUM)
        ending = (holding.market_value * (Decimal(1) + applied)).quantize(MONEY_QUANTUM)
        impact = ending - starting
        starting_total += starting

        impacts.append(
            PositionImpact(
                symbol=holding.symbol,
                sector=holding.sector,
                starting_value=starting,
                applied_return=applied,
                source=sources.get(holding.symbol, "unspecified"),
                ending_value=ending,
                impact=impact,
                impact_percent=applied,
                contribution_to_loss=None,
            )
        )

    total_impact = sum((impact.impact for impact in impacts), Decimal("0"))
    ending_total = starting_total + total_impact

    total_impact_percent = (total_impact / starting_total) if starting_total > 0 else Decimal("0")

    # Contribution to loss is only defined when the portfolio actually loses value.
    if total_impact < 0:
        impacts = [_with_contribution(impact, total_loss=total_impact) for impact in impacts]

    return StressTestResult(
        starting_value=starting_total,
        ending_value=ending_total,
        total_impact=total_impact,
        total_impact_percent=total_impact_percent,
        impacts=sorted(impacts, key=lambda item: item.impact),
        excluded_symbols=sorted(excluded_symbols),
    )


def _with_contribution(impact: PositionImpact, *, total_loss: Decimal) -> PositionImpact:
    """Attach this position's share of the portfolio's total loss.

    A position that gained value during a losing scenario gets a negative share:
    it offset part of the loss. Clamping it to zero would break the reconciliation.
    """
    from dataclasses import replace

    return replace(impact, contribution_to_loss=impact.impact / total_loss)


def apply_shocks(
    holdings: list[HoldingInput],
    *,
    shocks: list[Shock],
    excluded: list[str] | None = None,
) -> StressTestResult:
    """Apply a hypothetical shock set, honouring target precedence.

    A holding that no shock targets keeps its value and is reported with a zero
    return, which is correct here: the caller stated exactly what moves, so
    everything else is deliberately unchanged.
    """
    returns: dict[str, Decimal] = {}
    sources: dict[str, str] = {}

    for holding in holdings:
        shock = resolve_shock(symbol=holding.symbol, sector=holding.sector, shocks=shocks)
        if shock is None:
            returns[holding.symbol] = Decimal("0")
            sources[holding.symbol] = "no shock targets this holding"
            continue

        returns[holding.symbol] = shock.value
        sources[holding.symbol] = _describe(shock)

    return apply_returns(holdings, returns=returns, sources=sources, excluded=excluded)


def _describe(shock: Shock) -> str:
    """Explain which shock was applied and why."""
    if shock.target_type is ShockTargetType.PORTFOLIO:
        return "portfolio-wide shock"
    return f"{shock.target_type} shock on {shock.target}"


def window_return(
    prices: list[tuple[object, Decimal]],
) -> Decimal | None:
    """Return over a price window: last / first - 1.

    `prices` must be ascending by date and already clipped to the window. Returns
    None when fewer than two observations exist, or when the first price is not
    positive — both cases mean no return can be determined.
    """
    if len(prices) < 2:
        return None

    first = prices[0][1]
    last = prices[-1][1]

    if first <= 0:
        return None

    return last / first - Decimal(1)
