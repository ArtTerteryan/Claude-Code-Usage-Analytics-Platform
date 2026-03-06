"""SQLite connection manager.

Provides a context-managed connection with WAL mode, foreign keys,
and optimized pragmas for analytical workloads.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator


def _configure_connection(conn: sqlite3.Connection) -> None:
    """Apply common pragmas and settings to a connection."""
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=-64000")  # 64 MB cache
    conn.execute("PRAGMA temp_store=MEMORY")


@contextmanager
def get_connection(db_path: Path) -> Generator[sqlite3.Connection, None, None]:
    """Open a SQLite connection with analytical optimizations.

    Enables WAL mode, foreign keys, and returns rows as sqlite3.Row
    for dict-like access. Commits on clean exit, rolls back on exception.

    Args:
        db_path: Path to the SQLite database file.

    Yields:
        sqlite3.Connection configured for analytical use.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    _configure_connection(conn)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_read_connection(db_path: Path) -> sqlite3.Connection:
    """Open a read-only connection for use in long-lived processes (dashboard, API).

    Does not use a context manager — caller is responsible for closing.

    Args:
        db_path: Path to the SQLite database file.

    Returns:
        sqlite3.Connection in read-only mode.
    """
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, check_same_thread=False)
    _configure_connection(conn)
    return conn
