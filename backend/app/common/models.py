"""Column types and mixins shared by every ORM model."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated

from sqlalchemy import DateTime, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

# --- Reusable column types ---------------------------------------------------

# UUID primary key. Generated in Python so an object has its identity before it
# is flushed, which keeps services free of round trips.
UUIDPrimaryKey = Annotated[
    uuid.UUID,
    mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
]

UUIDColumn = Annotated[uuid.UUID, mapped_column(PGUUID(as_uuid=True))]

# Timezone-aware timestamps, always stored in UTC.
TimestampColumn = Annotated[datetime, mapped_column(DateTime(timezone=True))]

# Quantities: securities can be fractional, so allow eight decimal places.
Quantity = Annotated[Decimal, mapped_column(Numeric(20, 8))]

# Prices and monetary amounts: four decimal places covers sub-cent pricing.
Money = Annotated[Decimal, mapped_column(Numeric(20, 4))]

# ISO 4217 currency code.
CurrencyCode = Annotated[str, mapped_column(String(3))]


class TimestampMixin:
    """Adds `created_at` and `updated_at`, maintained by the database."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
