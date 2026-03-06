"""Tests for the batch database loader."""

from __future__ import annotations

import sqlite3

import pytest

from src.database.schema import initialize_database
from src.ingestion.loader import BatchLoader
from src.ingestion.validators import (
    ApiRequestRecord,
    EmployeeRecord,
    ToolEventRecord,
    UserPromptRecord,
)


@pytest.fixture
def db_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    initialize_database(conn)
    return conn


def _employee() -> EmployeeRecord:
    return EmployeeRecord(
        email="test@example.com", full_name="Test User",
        practice="ML Engineering", level="L5", level_numeric=5, location="Kyiv",
    )


def _api_request(event_id: str = "evt-001") -> ApiRequestRecord:
    return ApiRequestRecord(
        event_id=event_id, session_id="sess-001", user_email="test@example.com",
        timestamp="2026-01-15T09:30:45.123Z", date="2026-01-15", hour=9,
        model="claude-sonnet-4-6", cost_usd=0.005, duration_ms=1000,
        input_tokens=500, output_tokens=100, cache_read_tokens=0, cache_creation_tokens=0,
    )


def _tool_event(event_id: str = "evt-002") -> ToolEventRecord:
    return ToolEventRecord(
        event_id=event_id, event_type="tool_decision", session_id="sess-001",
        user_email="test@example.com", timestamp="2026-01-15T09:31:00.000Z",
        date="2026-01-15", hour=9, tool_name="Read",
        decision="accepted", decision_source="auto",
        success=None, duration_ms=None, result_size_bytes=None,
    )


def _user_prompt(event_id: str = "evt-003") -> UserPromptRecord:
    return UserPromptRecord(
        event_id=event_id, session_id="sess-001", user_email="test@example.com",
        timestamp="2026-01-15T09:30:00.000Z", date="2026-01-15", hour=9,
        prompt_length=50,
    )


class TestBatchLoader:
    def test_inserts_api_request_records(self, db_conn: sqlite3.Connection) -> None:
        loader = BatchLoader(db_conn, batch_size=100)
        loader.add(_api_request())
        loader.flush()
        db_conn.commit()
        count = db_conn.execute("SELECT COUNT(*) FROM api_requests").fetchone()[0]
        assert count == 1

    def test_inserts_tool_event_records(self, db_conn: sqlite3.Connection) -> None:
        loader = BatchLoader(db_conn, batch_size=100)
        loader.add(_tool_event())
        loader.flush()
        db_conn.commit()
        count = db_conn.execute("SELECT COUNT(*) FROM tool_events").fetchone()[0]
        assert count == 1

    def test_inserts_user_prompt_records(self, db_conn: sqlite3.Connection) -> None:
        loader = BatchLoader(db_conn, batch_size=100)
        loader.add(_user_prompt())
        loader.flush()
        db_conn.commit()
        count = db_conn.execute("SELECT COUNT(*) FROM user_prompts").fetchone()[0]
        assert count == 1

    def test_flushes_on_batch_size(self, db_conn: sqlite3.Connection) -> None:
        loader = BatchLoader(db_conn, batch_size=3)
        for i in range(5):
            loader.add(_api_request(f"evt-{i}"))
        # 3 should already be flushed automatically; 2 remain in buffer
        db_conn.commit()
        count = db_conn.execute("SELECT COUNT(*) FROM api_requests").fetchone()[0]
        assert count == 3
        loader.flush()
        db_conn.commit()
        count = db_conn.execute("SELECT COUNT(*) FROM api_requests").fetchone()[0]
        assert count == 5

    def test_idempotent_reinsertion(self, db_conn: sqlite3.Connection) -> None:
        loader = BatchLoader(db_conn, batch_size=100)
        loader.add(_api_request("evt-same"))
        loader.add(_api_request("evt-same"))
        loader.flush()
        db_conn.commit()
        count = db_conn.execute("SELECT COUNT(*) FROM api_requests").fetchone()[0]
        assert count == 1

    def test_build_sessions(self, db_conn: sqlite3.Connection) -> None:
        loader = BatchLoader(db_conn, batch_size=100)
        loader.add_employee(_employee())
        loader.add(_api_request(), resource={"os.type": "linux"}, attrs={})
        loader.add(_user_prompt(), resource={}, attrs={})
        loader.flush()
        db_conn.commit()
        n = loader.build_sessions()
        db_conn.commit()
        assert n >= 1
        row = db_conn.execute("SELECT * FROM sessions WHERE session_id='sess-001'").fetchone()
        assert row is not None

    def test_build_daily_summary(self, db_conn: sqlite3.Connection) -> None:
        loader = BatchLoader(db_conn, batch_size=100)
        loader.add_employee(_employee())
        loader.add(_api_request(), resource={}, attrs={})
        loader.flush()
        db_conn.commit()
        loader.build_sessions()
        db_conn.commit()
        n = loader.build_daily_summary()
        db_conn.commit()
        assert n >= 1
        row = db_conn.execute("SELECT total_cost FROM daily_cost_summary").fetchone()
        assert row[0] == pytest.approx(0.005)
