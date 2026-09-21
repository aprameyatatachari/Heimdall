"""The notification interface.

External delivery — email, SMS, push, Slack — is **not implemented**. What exists
is the boundary it will sit behind, so a delivery channel can be added later
without touching the rule engine or the lifecycle logic.

The only implementation shipped is `NullNotifier`, which records that a delivery
would have happened. That is enough for cooldown accounting to be correct and
tested now.

**Cooldowns govern delivery, not recording.** During a cooldown the signal's
observed value, severity, and `last_triggered_at` are still updated; only the
outbound notification is suppressed. An increase in severity bypasses the
cooldown, because a condition getting worse is new information.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

from app.common.logging import get_logger
from app.early_warning.models import WarningSignal
from app.early_warning.rule_types import SEVERITY_RANK, SignalSeverity

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class NotificationDecision:
    """Whether a notification should be delivered, and why."""

    deliver: bool
    reason: str


def should_notify(
    *,
    signal: WarningSignal,
    new_severity: SignalSeverity,
    previous_severity: SignalSeverity | None,
    cooldown_hours: int,
    now: datetime,
) -> NotificationDecision:
    """Decide whether to deliver a notification for a signal.

    Rules, in order:

    1. A brand-new signal is always delivered.
    2. An increase in severity is always delivered, even inside a cooldown.
    3. Otherwise, deliver only if the cooldown since the last delivery has elapsed.
    """
    if previous_severity is None:
        return NotificationDecision(True, "new signal")

    if SEVERITY_RANK[new_severity] > SEVERITY_RANK[previous_severity]:
        return NotificationDecision(
            True,
            f"severity increased from {previous_severity} to {new_severity}",
        )

    if cooldown_hours <= 0:
        return NotificationDecision(True, "no cooldown configured")

    if signal.last_notified_at is None:
        return NotificationDecision(True, "never notified")

    elapsed = now - signal.last_notified_at
    if elapsed >= timedelta(hours=cooldown_hours):
        return NotificationDecision(
            True,
            f"cooldown of {cooldown_hours}h elapsed",
        )

    remaining = timedelta(hours=cooldown_hours) - elapsed
    return NotificationDecision(
        False,
        f"within cooldown; {remaining.total_seconds() / 3600:.1f}h remaining",
    )


class Notifier(Protocol):
    """Delivers a signal to a user through some channel."""

    async def deliver(self, signal: WarningSignal, *, reason: str) -> bool:
        """Attempt delivery. Returns True when the signal was delivered."""
        ...


class NullNotifier:
    """The only notifier that exists. It records, it does not deliver.

    A delivery failure must never fail a monitoring run, so this always reports
    success and the real implementation will be expected to do the same.
    """

    async def deliver(self, signal: WarningSignal, *, reason: str) -> bool:
        """Record that a notification would have been delivered."""
        logger.info(
            "notification_suppressed_no_channel",
            signal_id=str(signal.id),
            signal_type=signal.signal_type,
            severity=signal.severity,
            reason=reason,
        )
        return True
