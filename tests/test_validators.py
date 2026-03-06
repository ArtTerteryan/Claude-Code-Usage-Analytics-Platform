"""Tests for data validation and type coercion."""

from __future__ import annotations

import pytest

from src.ingestion.validators import (
    ApiErrorRecord,
    ApiRequestRecord,
    EmployeeRecord,
    ToolEventRecord,
    UserPromptRecord,
    _parse_timestamp,
    _safe_float,
    _safe_int,
    validate_employee,
    validate_event,
)


def _raw(body: str, extra_attrs: dict | None = None) -> dict:
    attrs = {
        "user.email": "test@example.com",
        "session.id": "sess-001",
        "event.timestamp": "2026-01-15T09:30:45.123Z",
    }
    if extra_attrs:
        attrs.update(extra_attrs)
    return {
        "event_id": "evt-001",
        "body": body,
        "attributes": attrs,
        "resource": {"os.type": "linux", "host.arch": "x86_64"},
    }


class TestSafeInt:
    def test_converts_integer_string(self) -> None:
        assert _safe_int("42") == 42

    def test_converts_float_string(self) -> None:
        assert _safe_int("100.0") == 100

    def test_returns_default_for_none(self) -> None:
        assert _safe_int(None, 0) == 0

    def test_returns_default_for_non_numeric(self) -> None:
        assert _safe_int("abc", -1) == -1


class TestSafeFloat:
    def test_converts_float_string(self) -> None:
        assert _safe_float("3.14") == pytest.approx(3.14)

    def test_returns_default_for_non_numeric(self) -> None:
        assert _safe_float("not_a_number", 0.0) == 0.0


class TestParseTimestamp:
    def test_parses_valid_iso_timestamp(self) -> None:
        result = _parse_timestamp("2026-01-15T09:30:45.123Z")
        assert result is not None

    def test_returns_none_for_invalid_format(self) -> None:
        assert _parse_timestamp("bad") is None
        assert _parse_timestamp("") is None

    def test_extracts_date_and_hour(self) -> None:
        ts, date, hour = _parse_timestamp("2026-01-15T14:30:00.000Z")
        assert date == "2026-01-15"
        assert hour == 14


class TestValidateEvent:
    def test_validates_api_request_event(self) -> None:
        raw = _raw("claude_code.api_request", {
            "model": "claude-sonnet-4-6", "cost_usd": "0.0045",
            "duration_ms": "1234", "input_tokens": "500", "output_tokens": "100",
            "cache_read_tokens": "0", "cache_creation_tokens": "0",
        })
        result = validate_event(raw)
        assert result.is_valid
        assert isinstance(result.record, ApiRequestRecord)
        assert result.record.model == "claude-sonnet-4-6"
        assert result.record.cost_usd == pytest.approx(0.0045)

    def test_validates_tool_decision_event(self) -> None:
        raw = _raw("claude_code.tool_decision", {
            "tool_name": "Read", "decision": "accepted", "source": "auto",
        })
        result = validate_event(raw)
        assert result.is_valid
        assert isinstance(result.record, ToolEventRecord)
        assert result.record.event_type == "tool_decision"
        assert result.record.tool_name == "Read"

    def test_validates_tool_result_event(self) -> None:
        raw = _raw("claude_code.tool_result", {
            "tool_name": "Bash", "success": "true",
            "duration_ms": "500", "tool_result_size_bytes": "2048",
        })
        result = validate_event(raw)
        assert result.is_valid
        assert result.record.success == 1
        assert result.record.result_size_bytes == 2048

    def test_validates_user_prompt_event(self) -> None:
        raw = _raw("claude_code.user_prompt", {"prompt_length": "150"})
        result = validate_event(raw)
        assert result.is_valid
        assert isinstance(result.record, UserPromptRecord)
        assert result.record.prompt_length == 150

    def test_validates_api_error_event(self) -> None:
        raw = _raw("claude_code.api_error", {
            "model": "claude-opus-4-6", "error": "rate_limit",
            "status_code": "429", "duration_ms": "100", "attempt": "2",
        })
        result = validate_event(raw)
        assert result.is_valid
        assert isinstance(result.record, ApiErrorRecord)
        assert result.record.status_code == "429"
        assert result.record.attempt == 2

    def test_rejects_unknown_event_type(self) -> None:
        raw = _raw("unknown.type")
        result = validate_event(raw)
        assert not result.is_valid
        assert "Unknown event type" in result.rejection_reason

    def test_rejects_missing_email(self) -> None:
        raw = _raw("claude_code.api_request")
        raw["attributes"]["user.email"] = ""
        assert not validate_event(raw).is_valid

    def test_rejects_missing_session_id(self) -> None:
        raw = _raw("claude_code.api_request")
        raw["attributes"]["session.id"] = ""
        assert not validate_event(raw).is_valid

    def test_handles_undefined_status_code(self) -> None:
        raw = _raw("claude_code.api_error", {
            "status_code": "undefined", "error": "err",
        })
        result = validate_event(raw)
        assert result.is_valid
        assert result.record.status_code == "undefined"

    def test_handles_missing_tool_result_size_bytes(self) -> None:
        raw = _raw("claude_code.tool_result", {"tool_name": "Edit", "success": "true"})
        result = validate_event(raw)
        assert result.is_valid
        assert result.record.result_size_bytes is None

    def test_coerces_success_string_to_int(self) -> None:
        assert validate_event(_raw("claude_code.tool_result", {
            "tool_name": "X", "success": "true",
        })).record.success == 1
        assert validate_event(_raw("claude_code.tool_result", {
            "tool_name": "X", "success": "false",
        })).record.success == 0


class TestValidateEmployee:
    def test_validates_valid_row(self) -> None:
        row = {"email": "a@b.com", "full_name": "A B", "practice": "ML", "level": "L5", "location": "Kyiv"}
        rec = validate_employee(row)
        assert rec is not None
        assert rec.email == "a@b.com"

    def test_extracts_level_numeric(self) -> None:
        row = {"email": "a@b.com", "full_name": "", "practice": "", "level": "L5", "location": ""}
        assert validate_employee(row).level_numeric == 5

    def test_returns_none_for_missing_email(self) -> None:
        row = {"email": "", "full_name": "X", "practice": "", "level": "L1", "location": ""}
        assert validate_employee(row) is None
