"""Scenario definitions.

The historical catalogue lives here and nowhere else, so a date or a label is
corrected in one place. Every entry states a factual, verifiable market episode
and its exact date range; nothing is described as a prediction.

**What a historical scenario is.** Each asset's *observed* return over the stated
window is applied to the portfolio's *current* holdings. It answers "if those
exact moves happened again to what I hold today, what would the change be?" — it
does not reconstruct what the portfolio was worth at the time.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Final


class ScenarioType(StrEnum):
    """How a scenario's asset returns are obtained."""

    HISTORICAL = "historical"
    HYPOTHETICAL = "hypothetical"


class ShockTargetType(StrEnum):
    """What a hypothetical shock applies to.

    Precedence, most specific first: `symbol`, then `sector`, then `portfolio`.
    """

    SYMBOL = "symbol"
    SECTOR = "sector"
    PORTFOLIO = "portfolio"


# Precedence rank. A lower number wins.
TARGET_PRECEDENCE: Final[dict[ShockTargetType, int]] = {
    ShockTargetType.SYMBOL: 0,
    ShockTargetType.SECTOR: 1,
    ShockTargetType.PORTFOLIO: 2,
}


class ShockType(StrEnum):
    """The kind of change a shock represents.

    Only `relative_price` exists. A relative price change is the only shock that
    can be applied to an equity position without modelling anything Heimdall does
    not model — rate curves, credit spreads, or implied volatility.
    """

    RELATIVE_PRICE = "relative_price"


# A shock may not wipe out more than 99% of a position, and may not exceed +500%.
MIN_SHOCK_VALUE: Final = Decimal("-0.99")
MAX_SHOCK_VALUE: Final = Decimal("5.00")


@dataclass(frozen=True, slots=True)
class Shock:
    """One shock within a hypothetical scenario."""

    target_type: ShockTargetType
    # The symbol or sector affected. Ignored, and normally empty, for `portfolio`.
    target: str | None
    shock_type: ShockType
    value: Decimal

    @property
    def precedence(self) -> int:
        """Lower wins when two shocks could apply to the same holding."""
        return TARGET_PRECEDENCE[self.target_type]

    def to_dict(self) -> dict[str, object]:
        """Serializable form, persisted with the run."""
        return {
            "target_type": str(self.target_type),
            "target": self.target,
            "shock_type": str(self.shock_type),
            "value": str(self.value),
        }


@dataclass(frozen=True, slots=True)
class HistoricalScenario:
    """A real market episode, defined by an exact date range."""

    key: str
    name: str
    description: str
    start: date
    end: date

    @property
    def trading_window(self) -> str:
        """Human-readable window, for responses and reports."""
        return f"{self.start.isoformat()} to {self.end.isoformat()}"

    def to_dict(self) -> dict[str, object]:
        """Serializable form, persisted with the run."""
        return {
            "scenario_type": str(ScenarioType.HISTORICAL),
            "key": self.key,
            "name": self.name,
            "description": self.description,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
        }


# The catalogue. Dates are the widely cited peak-to-trough windows for each
# episode; they are stated so a reader can check them. Windows for global
# episodes follow the S&P 500, and those marked (India) follow the Nifty 50; a
# holding listed elsewhere is measured over the same dates, which may not be its
# own peak or trough.
HISTORICAL_SCENARIOS: Final[tuple[HistoricalScenario, ...]] = (
    HistoricalScenario(
        key="global_financial_crisis_2007_2009",
        name="Global financial crisis",
        description=(
            "Peak-to-trough decline in global equities between the October 2007 high "
            "and the March 2009 low, driven by the collapse of the US mortgage market "
            "and the ensuing banking crisis."
        ),
        start=date(2007, 10, 9),
        end=date(2009, 3, 9),
    ),
    HistoricalScenario(
        key="covid_19_crash_2020",
        name="COVID-19 crash",
        description=(
            "The rapid equity sell-off between the February 2020 high and the March "
            "2020 low as the scale of the pandemic became clear."
        ),
        start=date(2020, 2, 19),
        end=date(2020, 3, 23),
    ),
    HistoricalScenario(
        key="rate_rises_2022",
        name="Rapid interest-rate increases",
        description=(
            "The 2022 drawdown in equities and long-duration bonds during the fastest "
            "sequence of policy-rate increases in four decades."
        ),
        start=date(2022, 1, 3),
        end=date(2022, 10, 14),
    ),
    HistoricalScenario(
        key="q4_2018_selloff",
        name="Late-2018 technology sell-off",
        description=(
            "The fourth-quarter 2018 decline, concentrated in technology shares, amid "
            "tightening policy and trade-policy uncertainty."
        ),
        start=date(2018, 9, 20),
        end=date(2018, 12, 24),
    ),
    HistoricalScenario(
        key="china_devaluation_2015",
        name="August 2015 volatility shock",
        description=(
            "The sharp two-week global sell-off following China's currency "
            "devaluation in August 2015."
        ),
        start=date(2015, 8, 10),
        end=date(2015, 8, 25),
    ),
    HistoricalScenario(
        key="dot_com_bust_2000_2002",
        name="Dot-com bust",
        description=(
            "The decline in US equities between the March 2000 high and the October 2002 low, "
            "as technology and internet share valuations collapsed."
        ),
        start=date(2000, 3, 24),
        end=date(2002, 10, 9),
    ),
    HistoricalScenario(
        key="us_downgrade_euro_crisis_2011",
        name="2011 US downgrade and euro-area debt crisis",
        description=(
            "The equity decline between the April 2011 high and the October 2011 low, spanning "
            "the US credit-rating downgrade and the euro-area sovereign debt crisis."
        ),
        start=date(2011, 4, 29),
        end=date(2011, 10, 3),
    ),
    HistoricalScenario(
        key="taper_tantrum_2013",
        name="Taper tantrum",
        description=(
            "The sell-off in bonds, equities and emerging-market assets after the US Federal "
            "Reserve signalled in May 2013 that it would slow its asset purchases."
        ),
        start=date(2013, 5, 22),
        end=date(2013, 6, 24),
    ),
    HistoricalScenario(
        key="brexit_referendum_2016",
        name="Brexit referendum",
        description=(
            "The two trading days after the United Kingdom voted on 23 June 2016 to leave the "
            "European Union, measured from the close before the result was known."
        ),
        start=date(2016, 6, 23),
        end=date(2016, 6, 27),
    ),
    HistoricalScenario(
        key="india_demonetisation_2016",
        name="Demonetisation sell-off (India)",
        description=(
            "The decline in Indian equities from the announcement on 8 November 2016 that "
            "high-value banknotes were withdrawn, to the low in late December 2016."
        ),
        start=date(2016, 11, 8),
        end=date(2016, 12, 26),
    ),
    HistoricalScenario(
        key="volatility_shock_feb_2018",
        name="February 2018 volatility shock",
        description=(
            "The two-week global equity correction from the January 2018 high, during which "
            "products betting on low volatility were wiped out."
        ),
        start=date(2018, 1, 26),
        end=date(2018, 2, 8),
    ),
    HistoricalScenario(
        key="india_nbfc_crisis_2018",
        name="Non-bank lender crisis (India)",
        description=(
            "The decline in Indian equities between the August 2018 high and the October 2018 "
            "low, after defaults at IL&FS spread stress through non-bank lenders."
        ),
        start=date(2018, 8, 28),
        end=date(2018, 10, 26),
    ),
    HistoricalScenario(
        key="yen_carry_unwind_2024",
        name="August 2024 carry-trade unwind",
        description=(
            "The global equity sell-off between the mid-July 2024 high and 5 August 2024, as a "
            "rise in Japanese interest rates forced leveraged positions to be closed."
        ),
        start=date(2024, 7, 16),
        end=date(2024, 8, 5),
    ),
    HistoricalScenario(
        key="india_correction_2024_2025",
        name="2024-25 equity correction (India)",
        description=(
            "The decline in Indian equities between the September 2024 record high and the "
            "March 2025 low, during sustained selling by foreign investors."
        ),
        start=date(2024, 9, 26),
        end=date(2025, 3, 4),
    ),
    HistoricalScenario(
        key="tariff_shock_2025",
        name="2025 tariff shock",
        description=(
            "The decline in global equities between the February 2025 high and the 8 April "
            "2025 low, following the announcement of broad US import tariffs."
        ),
        start=date(2025, 2, 19),
        end=date(2025, 4, 8),
    ),
)

SCENARIOS_BY_KEY: Final[dict[str, HistoricalScenario]] = {
    scenario.key: scenario for scenario in HISTORICAL_SCENARIOS
}

# Limitations returned with every stress-test result. Stated plainly, because a
# price shock is not a macroeconomic model.
STRESS_TEST_LIMITATIONS: Final[tuple[str, ...]] = (
    "A stress test applies price changes to the portfolio's current holdings. It is "
    "an estimate of sensitivity, not a forecast.",
    "Quantities are held fixed. No trading, rebalancing, or cash flow is modelled.",
    "A historical scenario replays the returns observed in that window. Those exact "
    "returns are not expected to repeat.",
    "A relative price shock is not an interest-rate, credit, liquidity, or "
    "macroeconomic model. Bond and derivative behaviour is not modelled.",
    "Holdings with no price data in the scenario window are excluded from the "
    "estimate and listed separately.",
    "Results depend on the stored market data and on the assumptions stated with each scenario.",
)
