"""Tests for structured logging behaviour."""

from __future__ import annotations

import json

from app.common.logging import configure_logging, get_logger


def test_sensitive_values_are_redacted(capsys):
    configure_logging(level="INFO", log_format="json")

    get_logger("test").info(
        "user_registered",
        email="person@example.test",
        password="super-secret",
        authorization="Bearer abc.def.ghi",
    )

    record = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert record["password"] == "[redacted]"
    assert record["authorization"] == "[redacted]"
    assert record["email"] == "person@example.test"
    assert "super-secret" not in json.dumps(record)


def test_json_records_include_level_and_timestamp(capsys):
    configure_logging(level="INFO", log_format="json")

    get_logger("test").info("something_happened", detail=1)

    record = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert record["event"] == "something_happened"
    assert record["level"] == "info"
    assert record["timestamp"]
