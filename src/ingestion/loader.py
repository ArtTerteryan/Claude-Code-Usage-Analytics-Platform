"""Batch database loader for validated telemetry records.

Accumulates records in memory buffers and flushes to SQLite in batches
using executemany() for performance. Supports idempotent re-ingestion
via INSERT OR IGNORE.
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import astuple

from src.ingestion.validators import (
    ApiErrorRecord,
    ApiRequestRecord,
    EmployeeRecord,
    ToolEventRecord,
    UserPromptRecord,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SQL templates
# ---------------------------------------------------------------------------

_INSERT_EMPLOYEE = """
INSERT OR REPLACE INTO employees (email, full_name, practice, level, level_numeric, location)
VALUES (?, ?, ?, ?, ?, ?)
"""

_INSERT_API_REQUEST = """
INSERT OR IGNORE INTO api_requests
    (event_id, session_id, timestamp, date, hour, model,
     cost_usd, duration_ms, input_tokens, output_tokens,
     cache_read_tokens, cache_creation_tokens)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

_INSERT_TOOL_EVENT = """
INSERT OR IGNORE INTO tool_events
    (event_id, event_type, session_id, timestamp, date, hour, tool_name,
     decision, decision_source, success, duration_ms, result_size_bytes)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

_INSERT_USER_PROMPT = """
INSERT OR IGNORE INTO user_prompts
    (event_id, session_id, timestamp, date, hour, prompt_length)
VALUES (?, ?, ?, ?, ?, ?)
"""

_INSERT_API_ERROR = """
INSERT OR IGNORE INTO api_errors
    (event_id, session_id, timestamp, date, hour, model,
     error_message, status_code, duration_ms, attempt)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""

_BUILD_SESSIONS = """
INSERT OR IGNORE INTO sessions
    (session_id, user_email, start_time, end_time, duration_seconds,
     num_turns, terminal_type, os_type, host_arch, os_version,
     service_version, organization_id)
SELECT
    e.session_id,
    e.user_email,
    e.min_ts,
    e.max_ts,
    (julianday(e.max_ts) - julianday(e.min_ts)) * 86400.0,
    COALESCE(p.num_turns, 0),
    e.terminal_type,
    e.os_type,
    e.host_arch,
    e.os_version,
    e.service_version,
    e.organization_id
FROM (
    SELECT
        session_id,
        user_email,
        MIN(timestamp) AS min_ts,
        MAX(timestamp) AS max_ts,
        terminal_type,
        os_type,
        host_arch,
        os_version,
        service_version,
        organization_id
    FROM session_meta
    GROUP BY session_id
) e
LEFT JOIN (
    SELECT session_id, COUNT(*) AS num_turns
    FROM user_prompts
    GROUP BY session_id
) p ON e.session_id = p.session_id
"""

_BUILD_DAILY_SUMMARY = """
INSERT OR REPLACE INTO daily_cost_summary
    (date, model, practice, total_cost, total_requests,
     total_input_tokens, total_output_tokens, total_cache_read,
     total_cache_create, avg_duration_ms)
SELECT
    ar.date,
    ar.model,
    emp.practice,
    SUM(ar.cost_usd),
    COUNT(*),
    SUM(ar.input_tokens),
    SUM(ar.output_tokens),
    SUM(ar.cache_read_tokens),
    SUM(ar.cache_creation_tokens),
    AVG(ar.duration_ms)
FROM api_requests ar
JOIN sessions s ON ar.session_id = s.session_id
JOIN employees emp ON s.user_email = emp.email
GROUP BY ar.date, ar.model, emp.practice
"""

_CREATE_SESSION_META = """
CREATE TEMPORARY TABLE IF NOT EXISTS session_meta (
    session_id TEXT NOT NULL,
    user_email TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    terminal_type TEXT,
    os_type TEXT,
    host_arch TEXT,
    os_version TEXT,
    service_version TEXT,
    organization_id TEXT
)
"""

_INSERT_SESSION_META = """
INSERT INTO session_meta
    (session_id, user_email, timestamp, terminal_type, os_type,
     host_arch, os_version, service_version, organization_id)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


class BatchLoader:
    """Accumulates validated records and batch-inserts them into SQLite."""

    def __init__(self, conn: sqlite3.Connection, batch_size: int = 5000) -> None:
        self.conn = conn
        self.batch_size = batch_size
        self._buffers: dict[str, list[tuple]] = {
            "api_requests": [],
            "tool_events": [],
            "user_prompts": [],
            "api_errors": [],
            "session_meta": [],
        }
        self._sql_map = {
            "api_requests": _INSERT_API_REQUEST,
            "tool_events": _INSERT_TOOL_EVENT,
            "user_prompts": _INSERT_USER_PROMPT,
            "api_errors": _INSERT_API_ERROR,
            "session_meta": _INSERT_SESSION_META,
        }
        # Create temp table for session metadata
        self.conn.execute(_CREATE_SESSION_META)

    def add(
        self,
        record: ApiRequestRecord | ToolEventRecord | UserPromptRecord | ApiErrorRecord,
        resource: dict | None = None,
        attrs: dict | None = None,
    ) -> None:
        """Add a validated record to the appropriate buffer. Flushes if buffer is full."""
        if isinstance(record, ApiRequestRecord):
            self._buffers["api_requests"].append((
                record.event_id, record.session_id, record.timestamp,
                record.date, record.hour, record.model, record.cost_usd,
                record.duration_ms, record.input_tokens, record.output_tokens,
                record.cache_read_tokens, record.cache_creation_tokens,
            ))
            self._maybe_flush("api_requests")
        elif isinstance(record, ToolEventRecord):
            self._buffers["tool_events"].append((
                record.event_id, record.event_type, record.session_id,
                record.timestamp, record.date, record.hour, record.tool_name,
                record.decision, record.decision_source, record.success,
                record.duration_ms, record.result_size_bytes,
            ))
            self._maybe_flush("tool_events")
        elif isinstance(record, UserPromptRecord):
            self._buffers["user_prompts"].append((
                record.event_id, record.session_id, record.timestamp,
                record.date, record.hour, record.prompt_length,
            ))
            self._maybe_flush("user_prompts")
        elif isinstance(record, ApiErrorRecord):
            self._buffers["api_errors"].append((
                record.event_id, record.session_id, record.timestamp,
                record.date, record.hour, record.model, record.error_message,
                record.status_code, record.duration_ms, record.attempt,
            ))
            self._maybe_flush("api_errors")

        # Track session metadata from every event
        if resource is None:
            resource = {}
        if attrs is None:
            attrs = {}
        self._buffers["session_meta"].append((
            record.session_id,
            record.user_email,
            record.timestamp,
            attrs.get("terminal.type"),
            resource.get("os.type"),
            resource.get("host.arch"),
            resource.get("os.version"),
            resource.get("service.version"),
            attrs.get("organization.id"),
        ))
        self._maybe_flush("session_meta")

    def add_employee(self, record: EmployeeRecord) -> None:
        """Insert or replace an employee record."""
        self.conn.execute(_INSERT_EMPLOYEE, astuple(record))

    def flush(self) -> None:
        """Flush all remaining buffered records to the database."""
        for table in self._buffers:
            if self._buffers[table]:
                self._flush_buffer(table)

    def build_sessions(self) -> int:
        """Derive session records from loaded events and insert into sessions table."""
        self.conn.execute(_BUILD_SESSIONS)
        count = self.conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        logger.info("Built %d sessions", count)
        # Clean up temp table
        self.conn.execute("DROP TABLE IF EXISTS session_meta")
        return count

    def build_daily_summary(self) -> int:
        """Populate the daily_cost_summary table from api_requests + employees."""
        self.conn.execute(_BUILD_DAILY_SUMMARY)
        count = self.conn.execute("SELECT COUNT(*) FROM daily_cost_summary").fetchone()[0]
        logger.info("Built %d daily summary rows", count)
        return count

    def _maybe_flush(self, table: str) -> None:
        if len(self._buffers[table]) >= self.batch_size:
            self._flush_buffer(table)

    def _flush_buffer(self, table: str) -> None:
        records = self._buffers[table]
        if not records:
            return
        sql = self._sql_map[table]
        self.conn.executemany(sql, records)
        logger.debug("Flushed %d records to %s", len(records), table)
        self._buffers[table] = []
