"""Unit tests for portfolio and position request validation."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.portfolios.schemas import (
    DuplicateAssetMode,
    PortfolioCreateRequest,
    PortfolioUpdateRequest,
    PositionCreateRequest,
    PositionUpdateRequest,
)

# --- Portfolio creation ------------------------------------------------------


def test_name_is_trimmed():
    assert PortfolioCreateRequest(name="  Retirement  ").name == "Retirement"


def test_blank_name_is_rejected():
    with pytest.raises(ValidationError):
        PortfolioCreateRequest(name="   ")


def test_base_currency_defaults_to_usd():
    assert PortfolioCreateRequest(name="Core").base_currency == "USD"


def test_unsupported_base_currency_is_rejected():
    with pytest.raises(ValidationError, match="Unsupported base currency"):
        PortfolioCreateRequest(name="Core", base_currency="EUR")


def test_base_currency_is_upper_cased():
    assert PortfolioCreateRequest(name="Core", base_currency="usd").base_currency == "USD"


def test_benchmark_symbol_is_normalized():
    assert PortfolioCreateRequest(name="Core", benchmark_symbol=" spy ").benchmark_symbol == "SPY"


def test_empty_benchmark_symbol_becomes_null():
    assert PortfolioCreateRequest(name="Core", benchmark_symbol="   ").benchmark_symbol is None


def test_invalid_benchmark_symbol_is_rejected():
    with pytest.raises(ValidationError):
        PortfolioCreateRequest(name="Core", benchmark_symbol="not a symbol!")


def test_unknown_fields_are_rejected():
    with pytest.raises(ValidationError):
        PortfolioCreateRequest(name="Core", user_id="00000000-0000-0000-0000-000000000000")


def test_empty_description_becomes_null():
    assert PortfolioCreateRequest(name="Core", description="  ").description is None


# --- Portfolio update --------------------------------------------------------


def test_update_tracks_which_fields_were_sent():
    payload = PortfolioUpdateRequest.model_validate({"name": "Renamed"})
    assert payload.model_dump(exclude_unset=True) == {"name": "Renamed"}


def test_update_can_explicitly_clear_a_nullable_field():
    payload = PortfolioUpdateRequest.model_validate({"benchmark_symbol": None})
    assert payload.model_dump(exclude_unset=True) == {"benchmark_symbol": None}


def test_update_rejects_a_base_currency_change():
    with pytest.raises(ValidationError):
        PortfolioUpdateRequest.model_validate({"base_currency": "USD"})


# --- Position creation -------------------------------------------------------


def _position(**overrides):
    payload = {"symbol": "AAPL", "quantity": "10", "average_cost": "185.20"}
    payload.update(overrides)
    return PositionCreateRequest.model_validate(payload)


def test_quantity_and_cost_are_decimals_not_floats():
    position = _position(quantity="10.12345678", average_cost="185.2050")
    assert position.quantity == Decimal("10.12345678")
    assert position.average_cost == Decimal("185.2050")
    assert isinstance(position.quantity, Decimal)


def test_zero_quantity_is_rejected():
    with pytest.raises(ValidationError):
        _position(quantity="0")


def test_negative_quantity_is_rejected():
    with pytest.raises(ValidationError):
        _position(quantity="-5")


def test_negative_average_cost_is_rejected():
    with pytest.raises(ValidationError):
        _position(average_cost="-1")


def test_zero_average_cost_is_allowed_for_a_gifted_or_vested_holding():
    assert _position(average_cost="0").average_cost == Decimal("0")


def test_excess_quantity_precision_is_rejected():
    with pytest.raises(ValidationError):
        _position(quantity="1.123456789")


def test_excess_cost_precision_is_rejected():
    with pytest.raises(ValidationError):
        _position(average_cost="1.12345")


def test_symbol_is_normalized():
    assert _position(symbol=" aapl ").symbol == "AAPL"


def test_invalid_symbol_is_rejected():
    with pytest.raises(ValidationError):
        _position(symbol="=1+1")


def test_future_purchase_date_is_rejected():
    tomorrow = (datetime.now(UTC) + timedelta(days=1)).date()
    with pytest.raises(ValidationError, match="future"):
        _position(purchase_date=tomorrow.isoformat())


def test_past_purchase_date_is_accepted():
    assert _position(purchase_date="2024-03-15").purchase_date == date(2024, 3, 15)


def test_duplicate_mode_defaults_to_reject():
    assert _position().on_duplicate is DuplicateAssetMode.REJECT


def test_duplicate_mode_accepts_merge():
    assert _position(on_duplicate="merge").on_duplicate is DuplicateAssetMode.MERGE


def test_unknown_duplicate_mode_is_rejected():
    with pytest.raises(ValidationError):
        _position(on_duplicate="overwrite")


# --- Position update ---------------------------------------------------------


def test_position_update_tracks_sent_fields_only():
    payload = PositionUpdateRequest.model_validate({"quantity": "12"})
    assert payload.model_dump(exclude_unset=True) == {"quantity": Decimal("12")}


def test_position_update_cannot_change_the_asset():
    with pytest.raises(ValidationError):
        PositionUpdateRequest.model_validate({"symbol": "MSFT"})


def test_position_update_rejects_a_non_positive_quantity():
    with pytest.raises(ValidationError):
        PositionUpdateRequest.model_validate({"quantity": "0"})
