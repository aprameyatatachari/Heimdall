"""The disclaimers Heimdall shows everywhere its numbers appear.

Kept in one place so the application, the API documentation, and generated reports
cannot drift apart.
"""

from __future__ import annotations

from typing import Final

DISCLAIMER: Final = (
    "Heimdall is an educational portfolio-analysis tool. Its calculations are estimates "
    "based on historical data and model assumptions and do not constitute financial advice "
    "or guarantee future results."
)

EARLY_WARNING_DISCLAIMER: Final = (
    "Gjallarhorn Signals identify predefined conditions in portfolio data. They are not "
    "predictions, guarantees, or recommendations to buy, sell, or hold an investment."
)
