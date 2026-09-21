"""Validation and normalization of provider observations.

Pure functions. A provider's output is never trusted: it is sorted, deduplicated,
range-checked, and either accepted or flagged with a reason. Bad data is reported,
never silently replaced with zeroes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import StrEnum
from itertools import pairwise
from typing import Final

from app.market_data.provider import PriceObservation

# A single-day move larger than this is almost always a data error (a missing
# split adjustment, a currency change) rather than a real return. Such a bar is
# flagged rather than dropped, because a few genuine moves are this large.
EXTREME_DAILY_RETURN: Final = Decimal("0.60")

# Prices above this are implausible for the instruments Heimdall supports.
MAX_PLAUSIBLE_PRICE: Final = Decimal("1e9")


class DataQualityIssue(StrEnum):
    """Why an observation was rejected or flagged."""

    DUPLICATE_DATE = "duplicate_date"
    NON_POSITIVE_PRICE = "non_positive_price"
    IMPLAUSIBLE_PRICE = "implausible_price"
    # Reported by a provider adapter when a vendor row has no adjusted close.
    MISSING_ADJUSTED_CLOSE = "missing_adjusted_close"
    INVALID_OHLC = "invalid_ohlc"
    NEGATIVE_VOLUME = "negative_volume"
    FUTURE_DATE = "future_date"
    EXTREME_RETURN = "extreme_return"
    UNSUPPORTED_CURRENCY = "unsupported_currency"


@dataclass(frozen=True, slots=True)
class ObservationProblem:
    """One problem found in a provider's output."""

    observation_date: date | None
    issue: DataQualityIssue
    message: str
    # Rejected observations are not stored. Flagged ones are stored and reported.
    rejected: bool


@dataclass(slots=True)
class ValidationResult:
    """Clean observations, plus everything that was wrong with the input."""

    observations: list[PriceObservation] = field(default_factory=list)
    problems: list[ObservationProblem] = field(default_factory=list)

    @property
    def rejected_count(self) -> int:
        """How many observations were discarded."""
        return sum(1 for problem in self.problems if problem.rejected)

    @property
    def flagged_count(self) -> int:
        """How many observations were kept but marked suspicious."""
        return sum(1 for problem in self.problems if not problem.rejected)


def validate_observations(
    observations: list[PriceObservation],
    *,
    today: date,
) -> ValidationResult:
    """Sort, deduplicate, and validate a provider's observations.

    Rules:

    * Observations are returned ascending by date, whatever order they arrived in.
    * A repeated date keeps the first occurrence and rejects the rest.
    * A non-positive, missing, or implausible price rejects the observation, because
      no return can be computed from it.
    * An invalid OHLC relationship (`low > high`, or a close outside the range)
      rejects the observation.
    * A dated-in-the-future observation is rejected.
    * An extreme one-day move is **flagged, not rejected**: some real moves are
      that large, so the caller is told rather than having data removed.
    """
    result = ValidationResult()
    seen: set[date] = set()

    for observation in sorted(observations, key=lambda item: item.date):
        problem = _check(observation, today=today, seen=seen)
        if problem is not None:
            result.problems.append(problem)
            if problem.rejected:
                continue
        seen.add(observation.date)
        result.observations.append(observation)

    result.problems.extend(_flag_extreme_returns(result.observations))
    return result


def _check(
    observation: PriceObservation,
    *,
    today: date,
    seen: set[date],
) -> ObservationProblem | None:
    """Return a problem for one observation, or None when it is clean."""
    if observation.date in seen:
        return ObservationProblem(
            observation_date=observation.date,
            issue=DataQualityIssue.DUPLICATE_DATE,
            message=f"Duplicate observation for {observation.date.isoformat()}.",
            rejected=True,
        )

    if observation.date > today:
        return ObservationProblem(
            observation_date=observation.date,
            issue=DataQualityIssue.FUTURE_DATE,
            message=f"Observation dated {observation.date.isoformat()} is in the future.",
            rejected=True,
        )

    for label, value in (
        ("close", observation.close),
        ("adjusted close", observation.adjusted_close),
    ):
        if not value.is_finite() or value <= 0:
            return ObservationProblem(
                observation_date=observation.date,
                issue=DataQualityIssue.NON_POSITIVE_PRICE,
                message=f"{label.capitalize()} on {observation.date.isoformat()} is not positive.",
                rejected=True,
            )
        if value > MAX_PLAUSIBLE_PRICE:
            return ObservationProblem(
                observation_date=observation.date,
                issue=DataQualityIssue.IMPLAUSIBLE_PRICE,
                message=f"{label.capitalize()} on {observation.date.isoformat()} is implausible.",
                rejected=True,
            )

    ohlc_problem = _check_ohlc(observation)
    if ohlc_problem is not None:
        return ohlc_problem

    if observation.volume is not None and observation.volume < 0:
        return ObservationProblem(
            observation_date=observation.date,
            issue=DataQualityIssue.NEGATIVE_VOLUME,
            message=f"Volume on {observation.date.isoformat()} is negative.",
            rejected=True,
        )

    return None


def _check_ohlc(observation: PriceObservation) -> ObservationProblem | None:
    """Verify that any supplied open/high/low/close values are consistent."""
    high, low = observation.high, observation.low
    if high is None or low is None:
        return None

    candidates = [value for value in (observation.open, observation.close) if value is not None]
    inconsistent = low > high or any(value < low or value > high for value in candidates)

    if inconsistent:
        return ObservationProblem(
            observation_date=observation.date,
            issue=DataQualityIssue.INVALID_OHLC,
            message=(
                f"Open/high/low/close values on {observation.date.isoformat()} are inconsistent."
            ),
            rejected=True,
        )
    return None


def _flag_extreme_returns(observations: list[PriceObservation]) -> list[ObservationProblem]:
    """Flag single-day moves large enough to suggest an unadjusted corporate action."""
    problems: list[ObservationProblem] = []

    for previous, current in pairwise(observations):
        if previous.adjusted_close <= 0:  # pragma: no cover - rejected earlier
            continue
        change = (current.adjusted_close - previous.adjusted_close) / previous.adjusted_close
        if abs(change) >= EXTREME_DAILY_RETURN:
            problems.append(
                ObservationProblem(
                    observation_date=current.date,
                    issue=DataQualityIssue.EXTREME_RETURN,
                    message=(
                        f"Adjusted close moved {change:.1%} on {current.date.isoformat()}. "
                        "This may indicate an unadjusted corporate action rather than a "
                        "real return."
                    ),
                    rejected=False,
                )
            )

    return problems
