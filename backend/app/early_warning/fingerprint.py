"""Signal fingerprinting.

A fingerprint is the stable identity of an underlying **condition**, not of an
observation of it. It is built only from things that do not change while the
condition persists:

* portfolio id
* alert rule id
* signal type
* the affected subject — a symbol, a sector, a scenario key, or a fixed scope name

It deliberately excludes timestamps, observed values, severities, and thresholds.
Including any of those would give the same condition a new fingerprint on every
monitoring run, which is exactly the duplicate-signal behaviour this prevents.
"""

from __future__ import annotations

import hashlib
import uuid
from typing import Final

# Used when a condition applies to the portfolio as a whole rather than to one
# asset, sector, or scenario.
PORTFOLIO_SCOPE: Final = "portfolio"

FINGERPRINT_LENGTH: Final = 64


def build_fingerprint(
    *,
    portfolio_id: uuid.UUID,
    alert_rule_id: uuid.UUID,
    signal_type: str,
    subject: str | None,
) -> str:
    """Return the stable fingerprint of one condition.

    The result is a hex SHA-256 digest, so it has a fixed length whatever the
    subject is, and it never contains user data in readable form.
    """
    parts = [
        str(portfolio_id),
        str(alert_rule_id),
        signal_type.strip().lower(),
        (subject or PORTFOLIO_SCOPE).strip().lower(),
    ]
    material = "|".join(parts)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()
