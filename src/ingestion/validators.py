"""Data validation and type coercion for telemetry events.

Converts string-encoded numerics, booleans, and optional fields into
their target Python types. Rejects malformed records with reasons.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Validated record types
# ---------------------------------------------------------------------------


@dataclass
class ApiRequestRecord:
    """Validated record for a claude_code.api_request event."""

    event_id: str
    session_id: str
    user_email: str
    timestamp: str
    date: str
    hour: int
    model: str
    cost_usd: float
    duration_ms: int
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_creation_tokens: int


@dataclass
class ToolEventRecord:
    """Validated record for a tool_decision or tool_result event."""

    event_id: str
    event_type: str  # 'tool_decision' or 'tool_result'
    session_id: str
    user_email: str
    timestamp: str
    date: str
    hour: int
    tool_name: str
    decision: str | None
    decision_source: str | None
    success: int | None  # 1/0/None
    duration_ms: int | None
    result_size_bytes: int | None


@dataclass
class UserPromptRecord:
    """Validated record for a claude_code.user_prompt event."""

    event_id: str
    session_id: str
    user_email: str
    timestamp: str
    date: str
    hour: int
    prompt_length: int


@dataclass
class ApiErrorRecord:
    """Validated record for a claude_code.api_error event."""

    event_id: str
    session_id: str
    user_email: str
    timestamp: str
    date: str
    hour: int
    model: str
    error_message: str
    status_code: str | None
    duration_ms: int
    attempt: int


@dataclass
class SessionRecord:
    """Derived session record, built after all events are loaded."""

    session_id: str
    user_email: str
    start_time: str
    end_time: str
    duration_seconds: float
    num_turns: int
    terminal_type: str | None
    os_type: str | None
    host_arch: str | None
    os_version: str | None
    service_version: str | None
    organization_id: str | None


@dataclass
class EmployeeRecord:
    """Validated record for an employee from CSV."""

    email: str
    full_name: str
    practice: str
    level: str
    level_numeric: int
    location: str


# ---------------------------------------------------------------------------
# Validation results
# ---------------------------------------------------------------------------


@dataclass
class ValidationResult:
    """Result of validating a single raw event."""

    record: ApiRequestRecord | ToolEventRecord | UserPromptRecord | ApiErrorRecord | None
    is_valid: bool
    rejection_reason: str | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _safe_int(value: str | None, default: int | None = None) -> int | None:
    """Safely convert a string to int via float (handles '100.0')."""
    if value is None:
        return default
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return default


def _safe_float(value: str | None, default: float | None = None) -> float | None:
    """Safely convert a string to float."""
    if value is None:
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def _parse_timestamp(ts_str: str) -> tuple[str, str, int] | None:
    """Parse ISO timestamp string into (iso_str, date_str, hour).

    Args:
        ts_str: Timestamp like '2026-01-15T09:30:45.123Z'.

    Returns:
        Tuple of (original_str, 'YYYY-MM-DD', hour_int) or None if unparseable.
    """
    try:
        # Format: YYYY-MM-DDThh:mm:ss.mmmZ
        date_part = ts_str[:10]  # YYYY-MM-DD
        hour = int(ts_str[11:13])
        # Basic validation
        if len(date_part) != 10 or date_part[4] != "-" or date_part[7] != "-":
            return None
        return (ts_str, date_part, hour)
    except (IndexError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Per-type validators
# ---------------------------------------------------------------------------


def _validate_common(raw: dict) -> tuple[dict, str | None]:
    """Extract and validate common fields shared by all event types.

    Returns (common_fields_dict, rejection_reason_or_none).
    """
    attrs = raw.get("attributes", {})
    event_id = raw.get("event_id", "")
    user_email = attrs.get("user.email", "")
    session_id = attrs.get("session.id", "")
    ts_str = attrs.get("event.timestamp", "")

    if not user_email:
        return {}, f"Missing user.email in event {event_id}"
    if not session_id:
        return {}, f"Missing session.id in event {event_id}"

    ts = _parse_timestamp(ts_str)
    if ts is None:
        return {}, f"Unparseable timestamp '{ts_str}' in event {event_id}"

    return {
        "event_id": event_id,
        "session_id": session_id,
        "user_email": user_email,
        "timestamp": ts[0],
        "date": ts[1],
        "hour": ts[2],
        "attrs": attrs,
        "resource": raw.get("resource", {}),
    }, None


def _validate_api_request(raw: dict) -> ValidationResult:
    common, reason = _validate_common(raw)
    if reason:
        return ValidationResult(record=None, is_valid=False, rejection_reason=reason)

    attrs = common["attrs"]
    cost = _safe_float(attrs.get("cost_usd"), 0.0)
    if cost is not None and cost < 0:
        cost = 0.0

    record = ApiRequestRecord(
        event_id=common["event_id"],
        session_id=common["session_id"],
        user_email=common["user_email"],
        timestamp=common["timestamp"],
        date=common["date"],
        hour=common["hour"],
        model=attrs.get("model", "unknown"),
        cost_usd=round(cost, 6),
        duration_ms=_safe_int(attrs.get("duration_ms"), 0),
        input_tokens=_safe_int(attrs.get("input_tokens"), 0),
        output_tokens=_safe_int(attrs.get("output_tokens"), 0),
        cache_read_tokens=_safe_int(attrs.get("cache_read_tokens"), 0),
        cache_creation_tokens=_safe_int(attrs.get("cache_creation_tokens"), 0),
    )
    return ValidationResult(record=record, is_valid=True)


def _validate_tool_decision(raw: dict) -> ValidationResult:
    common, reason = _validate_common(raw)
    if reason:
        return ValidationResult(record=None, is_valid=False, rejection_reason=reason)

    attrs = common["attrs"]
    record = ToolEventRecord(
        event_id=common["event_id"],
        event_type="tool_decision",
        session_id=common["session_id"],
        user_email=common["user_email"],
        timestamp=common["timestamp"],
        date=common["date"],
        hour=common["hour"],
        tool_name=attrs.get("tool_name", "unknown"),
        decision=attrs.get("decision"),
        decision_source=attrs.get("source"),
        success=None,
        duration_ms=None,
        result_size_bytes=None,
    )
    return ValidationResult(record=record, is_valid=True)


def _validate_tool_result(raw: dict) -> ValidationResult:
    common, reason = _validate_common(raw)
    if reason:
        return ValidationResult(record=None, is_valid=False, rejection_reason=reason)

    attrs = common["attrs"]
    success_str = attrs.get("success")
    success = None
    if success_str is not None:
        success = 1 if success_str == "true" else 0

    record = ToolEventRecord(
        event_id=common["event_id"],
        event_type="tool_result",
        session_id=common["session_id"],
        user_email=common["user_email"],
        timestamp=common["timestamp"],
        date=common["date"],
        hour=common["hour"],
        tool_name=attrs.get("tool_name", "unknown"),
        decision=attrs.get("decision_type"),
        decision_source=attrs.get("decision_source"),
        success=success,
        duration_ms=_safe_int(attrs.get("duration_ms")),
        result_size_bytes=_safe_int(attrs.get("tool_result_size_bytes")),
    )
    return ValidationResult(record=record, is_valid=True)


def _validate_user_prompt(raw: dict) -> ValidationResult:
    common, reason = _validate_common(raw)
    if reason:
        return ValidationResult(record=None, is_valid=False, rejection_reason=reason)

    attrs = common["attrs"]
    record = UserPromptRecord(
        event_id=common["event_id"],
        session_id=common["session_id"],
        user_email=common["user_email"],
        timestamp=common["timestamp"],
        date=common["date"],
        hour=common["hour"],
        prompt_length=_safe_int(attrs.get("prompt_length"), 0),
    )
    return ValidationResult(record=record, is_valid=True)


def _validate_api_error(raw: dict) -> ValidationResult:
    common, reason = _validate_common(raw)
    if reason:
        return ValidationResult(record=None, is_valid=False, rejection_reason=reason)

    attrs = common["attrs"]
    status_code = attrs.get("status_code")
    # Keep "undefined" as-is (it's a valid status in this data)

    record = ApiErrorRecord(
        event_id=common["event_id"],
        session_id=common["session_id"],
        user_email=common["user_email"],
        timestamp=common["timestamp"],
        date=common["date"],
        hour=common["hour"],
        model=attrs.get("model", "unknown"),
        error_message=attrs.get("error", "unknown error"),
        status_code=status_code,
        duration_ms=_safe_int(attrs.get("duration_ms"), 0),
        attempt=_safe_int(attrs.get("attempt"), 1),
    )
    return ValidationResult(record=record, is_valid=True)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_VALIDATORS = {
    "claude_code.api_request": _validate_api_request,
    "claude_code.tool_decision": _validate_tool_decision,
    "claude_code.tool_result": _validate_tool_result,
    "claude_code.user_prompt": _validate_user_prompt,
    "claude_code.api_error": _validate_api_error,
}


def validate_event(raw: dict) -> ValidationResult:
    """Validate and coerce a raw event dict into a typed record.

    Dispatches to the appropriate type-specific validator based on
    the event's 'body' field.
    """
    body = raw.get("body", "")
    validator = _VALIDATORS.get(body)
    if validator is None:
        return ValidationResult(
            record=None,
            is_valid=False,
            rejection_reason=f"Unknown event type: {body}",
        )
    return validator(raw)


def validate_employee(row: dict) -> EmployeeRecord | None:
    """Validate and coerce a CSV row into an EmployeeRecord.

    Extracts level_numeric from the level string (e.g. 'L5' -> 5).
    """
    email = row.get("email", "").strip()
    if not email:
        return None

    level = row.get("level", "L0").strip()
    try:
        level_numeric = int(level.lstrip("L"))
    except ValueError:
        level_numeric = 0

    return EmployeeRecord(
        email=email,
        full_name=row.get("full_name", "").strip(),
        practice=row.get("practice", "").strip(),
        level=level,
        level_numeric=level_numeric,
        location=row.get("location", "").strip(),
    )
