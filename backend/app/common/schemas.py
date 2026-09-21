"""Response primitives shared across features."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

# Pagination bounds, applied to every collection endpoint.
DEFAULT_PAGE_LIMIT = 50
MAX_PAGE_LIMIT = 200


class ApiModel(BaseModel):
    """Base class for API schemas.

    `from_attributes` lets a schema be built from an ORM object, but ORM objects
    are never returned from a route directly.
    """

    model_config = ConfigDict(from_attributes=True, extra="forbid")


class Page[ItemT](BaseModel):
    """One page of a collection, with a stable ordering guaranteed by the route."""

    items: list[ItemT]
    total: int = Field(description="Total number of matching records.")
    limit: int = Field(description="Maximum number of items requested.")
    offset: int = Field(description="Number of items skipped.")


class DeletedResponse(BaseModel):
    """Returned by delete endpoints that do not respond with 204."""

    deleted: bool = True
