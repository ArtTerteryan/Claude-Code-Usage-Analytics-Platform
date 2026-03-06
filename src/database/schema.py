"""Database schema definitions and initialization.

Contains all DDL statements for creating tables and indexes.
Provides a single function to initialize a fresh database.
"""

from __future__ import annotations

import sqlite3

# ---------------------------------------------------------------------------
# DDL Statements
# ---------------------------------------------------------------------------

EMPLOYEES_TABLE = """
CREATE TABLE IF NOT EXISTS employees (
    email           TEXT PRIMARY KEY,
    full_name       TEXT NOT NULL,
    practice        TEXT NOT NULL,
    level           TEXT NOT NULL,
    level_numeric   INTEGER NOT NULL,
    location        TEXT NOT NULL
);
"""

SESSIONS_TABLE = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id      TEXT PRIMARY KEY,
    user_email      TEXT NOT NULL REFERENCES employees(email),
    start_time      TEXT NOT NULL,
    end_time        TEXT NOT NULL,
    duration_seconds REAL NOT NULL,
    num_turns       INTEGER NOT NULL DEFAULT 0,
    terminal_type   TEXT,
    os_type         TEXT,
    host_arch       TEXT,
    os_version      TEXT,
    service_version TEXT,
    organization_id TEXT
);
"""

API_REQUESTS_TABLE = """
CREATE TABLE IF NOT EXISTS api_requests (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id              TEXT UNIQUE NOT NULL,
    session_id            TEXT NOT NULL,
    timestamp             TEXT NOT NULL,
    date                  TEXT NOT NULL,
    hour                  INTEGER NOT NULL,
    model                 TEXT NOT NULL,
    cost_usd              REAL NOT NULL,
    duration_ms           INTEGER NOT NULL,
    input_tokens          INTEGER NOT NULL,
    output_tokens         INTEGER NOT NULL,
    cache_read_tokens     INTEGER NOT NULL,
    cache_creation_tokens INTEGER NOT NULL
);
"""

TOOL_EVENTS_TABLE = """
CREATE TABLE IF NOT EXISTS tool_events (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id          TEXT UNIQUE NOT NULL,
    event_type        TEXT NOT NULL,
    session_id        TEXT NOT NULL,
    timestamp         TEXT NOT NULL,
    date              TEXT NOT NULL,
    hour              INTEGER NOT NULL,
    tool_name         TEXT NOT NULL,
    decision          TEXT,
    decision_source   TEXT,
    success           INTEGER,
    duration_ms       INTEGER,
    result_size_bytes INTEGER
);
"""

API_ERRORS_TABLE = """
CREATE TABLE IF NOT EXISTS api_errors (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id      TEXT UNIQUE NOT NULL,
    session_id    TEXT NOT NULL,
    timestamp     TEXT NOT NULL,
    date          TEXT NOT NULL,
    hour          INTEGER NOT NULL,
    model         TEXT NOT NULL,
    error_message TEXT NOT NULL,
    status_code   TEXT,
    duration_ms   INTEGER NOT NULL,
    attempt       INTEGER NOT NULL
);
"""

USER_PROMPTS_TABLE = """
CREATE TABLE IF NOT EXISTS user_prompts (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id      TEXT UNIQUE NOT NULL,
    session_id    TEXT NOT NULL,
    timestamp     TEXT NOT NULL,
    date          TEXT NOT NULL,
    hour          INTEGER NOT NULL,
    prompt_length INTEGER NOT NULL
);
"""

DAILY_COST_SUMMARY_TABLE = """
CREATE TABLE IF NOT EXISTS daily_cost_summary (
    date                TEXT NOT NULL,
    model               TEXT NOT NULL,
    practice            TEXT NOT NULL,
    total_cost          REAL NOT NULL,
    total_requests      INTEGER NOT NULL,
    total_input_tokens  INTEGER NOT NULL,
    total_output_tokens INTEGER NOT NULL,
    total_cache_read    INTEGER NOT NULL,
    total_cache_create  INTEGER NOT NULL,
    avg_duration_ms     REAL NOT NULL,
    PRIMARY KEY (date, model, practice)
);
"""

# ---------------------------------------------------------------------------
# Index Statements
# ---------------------------------------------------------------------------

INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_employees_practice ON employees(practice);",
    "CREATE INDEX IF NOT EXISTS idx_employees_level ON employees(level_numeric);",
    "CREATE INDEX IF NOT EXISTS idx_employees_location ON employees(location);",
    "CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_email);",
    "CREATE INDEX IF NOT EXISTS idx_sessions_start ON sessions(start_time);",
    "CREATE INDEX IF NOT EXISTS idx_sessions_terminal ON sessions(terminal_type);",
    "CREATE INDEX IF NOT EXISTS idx_api_requests_session ON api_requests(session_id);",
    "CREATE INDEX IF NOT EXISTS idx_api_requests_date ON api_requests(date);",
    "CREATE INDEX IF NOT EXISTS idx_api_requests_model ON api_requests(model);",
    "CREATE INDEX IF NOT EXISTS idx_api_requests_timestamp ON api_requests(timestamp);",
    "CREATE INDEX IF NOT EXISTS idx_tool_events_session ON tool_events(session_id);",
    "CREATE INDEX IF NOT EXISTS idx_tool_events_date ON tool_events(date);",
    "CREATE INDEX IF NOT EXISTS idx_tool_events_tool ON tool_events(tool_name);",
    "CREATE INDEX IF NOT EXISTS idx_tool_events_decision ON tool_events(decision);",
    "CREATE INDEX IF NOT EXISTS idx_api_errors_session ON api_errors(session_id);",
    "CREATE INDEX IF NOT EXISTS idx_api_errors_date ON api_errors(date);",
    "CREATE INDEX IF NOT EXISTS idx_api_errors_model ON api_errors(model);",
    "CREATE INDEX IF NOT EXISTS idx_api_errors_status ON api_errors(status_code);",
    "CREATE INDEX IF NOT EXISTS idx_user_prompts_session ON user_prompts(session_id);",
    "CREATE INDEX IF NOT EXISTS idx_user_prompts_date ON user_prompts(date);",
]


TABLES = [
    EMPLOYEES_TABLE,
    SESSIONS_TABLE,
    API_REQUESTS_TABLE,
    TOOL_EVENTS_TABLE,
    API_ERRORS_TABLE,
    USER_PROMPTS_TABLE,
    DAILY_COST_SUMMARY_TABLE,
]

TABLE_NAMES = [
    "daily_cost_summary",
    "api_requests",
    "tool_events",
    "api_errors",
    "user_prompts",
    "sessions",
    "employees",
]


def initialize_database(conn: sqlite3.Connection) -> None:
    """Create all tables and indexes if they don't already exist.

    Args:
        conn: Active SQLite connection.
    """
    cursor = conn.cursor()
    for ddl in TABLES:
        cursor.execute(ddl)
    for idx in INDEXES:
        cursor.execute(idx)
    conn.commit()


def drop_all_tables(conn: sqlite3.Connection) -> None:
    """Drop all tables. Used for clean re-ingestion.

    Args:
        conn: Active SQLite connection.
    """
    cursor = conn.cursor()
    for table in TABLE_NAMES:
        cursor.execute(f"DROP TABLE IF EXISTS {table}")
    conn.commit()
