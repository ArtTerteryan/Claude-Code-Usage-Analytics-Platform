"""Core analytics query functions.

Each function accepts a SQLite connection and optional filter parameters,
builds parameterized SQL, and returns a pandas DataFrame ready for visualization.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

import pandas as pd


# ---------------------------------------------------------------------------
# Filter dataclass
# ---------------------------------------------------------------------------


@dataclass
class Filters:
    """Dashboard filter state. All fields are optional."""

    date_from: str | None = None
    date_to: str | None = None
    practices: list[str] = field(default_factory=list)
    levels: list[str] = field(default_factory=list)
    models: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_where(
    filters: Filters,
    date_col: str = "ar.date",
    need_emp: bool = False,
    need_session: bool = False,
    extra: list[tuple[str, list]] | None = None,
) -> tuple[str, list]:
    """Build a parameterized WHERE clause from Filters.

    Returns (sql_fragment, params) where sql_fragment starts with ' WHERE ...'
    or is empty string if no conditions.
    """
    conditions: list[str] = []
    params: list = []

    if filters.date_from:
        conditions.append(f"{date_col} >= ?")
        params.append(filters.date_from)
    if filters.date_to:
        conditions.append(f"{date_col} <= ?")
        params.append(filters.date_to)
    if filters.models:
        placeholders = ",".join("?" for _ in filters.models)
        conditions.append(f"ar.model IN ({placeholders})")
        params.extend(filters.models)
    if filters.practices:
        placeholders = ",".join("?" for _ in filters.practices)
        conditions.append(f"emp.practice IN ({placeholders})")
        params.extend(filters.practices)
    if filters.levels:
        placeholders = ",".join("?" for _ in filters.levels)
        conditions.append(f"emp.level IN ({placeholders})")
        params.extend(filters.levels)

    if extra:
        for cond, p in extra:
            conditions.append(cond)
            params.extend(p)

    if not conditions:
        return "", params
    return " WHERE " + " AND ".join(conditions), params


def _query(conn: sqlite3.Connection, sql: str, params: list | None = None) -> pd.DataFrame:
    """Execute a query and return as a DataFrame."""
    return pd.read_sql_query(sql, conn, params=params or [])


# ---------------------------------------------------------------------------
# 1. Daily metrics
# ---------------------------------------------------------------------------


def get_daily_metrics(conn: sqlite3.Connection, filters: Filters) -> pd.DataFrame:
    """Daily aggregate metrics: cost, requests, tokens, errors, sessions.

    Returns DataFrame: date, total_cost, total_requests, total_input_tokens,
    total_output_tokens, total_errors, active_users, sessions.
    """
    where, params = _build_where(filters, date_col="ar.date", need_emp=True)

    sql = f"""
    SELECT
        ar.date,
        SUM(ar.cost_usd) AS total_cost,
        COUNT(*) AS total_requests,
        SUM(ar.input_tokens) AS total_input_tokens,
        SUM(ar.output_tokens) AS total_output_tokens,
        COUNT(DISTINCT s.user_email) AS active_users,
        COUNT(DISTINCT ar.session_id) AS sessions
    FROM api_requests ar
    JOIN sessions s ON ar.session_id = s.session_id
    JOIN employees emp ON s.user_email = emp.email
    {where}
    GROUP BY ar.date
    ORDER BY ar.date
    """

    df = _query(conn, sql, params)

    # Join error counts separately (different table)
    where_err, params_err = _build_where(
        filters, date_col="e.date",
        extra=[("1=1", [])]  # ensure we always have a where
    )
    # Rebuild for error table alias
    err_conditions: list[str] = []
    err_params: list = []
    if filters.date_from:
        err_conditions.append("e.date >= ?")
        err_params.append(filters.date_from)
    if filters.date_to:
        err_conditions.append("e.date <= ?")
        err_params.append(filters.date_to)
    if filters.practices:
        placeholders = ",".join("?" for _ in filters.practices)
        err_conditions.append(f"emp.practice IN ({placeholders})")
        err_params.extend(filters.practices)
    if filters.levels:
        placeholders = ",".join("?" for _ in filters.levels)
        err_conditions.append(f"emp.level IN ({placeholders})")
        err_params.extend(filters.levels)

    err_where = (" WHERE " + " AND ".join(err_conditions)) if err_conditions else ""

    err_sql = f"""
    SELECT e.date, COUNT(*) AS total_errors
    FROM api_errors e
    JOIN sessions s ON e.session_id = s.session_id
    JOIN employees emp ON s.user_email = emp.email
    {err_where}
    GROUP BY e.date
    """
    err_df = _query(conn, err_sql, err_params)

    if not df.empty and not err_df.empty:
        df = df.merge(err_df, on="date", how="left")
        df["total_errors"] = df["total_errors"].fillna(0).astype(int)
    elif not df.empty:
        df["total_errors"] = 0

    return df


# ---------------------------------------------------------------------------
# 2. Hourly activity
# ---------------------------------------------------------------------------


def get_hourly_activity(conn: sqlite3.Connection, filters: Filters) -> pd.DataFrame:
    """Event count by hour-of-day and day-of-week.

    Returns DataFrame: day_of_week (0=Mon..6=Sun), hour, event_count.
    """
    conds: list[str] = []
    params: list = []
    if filters.date_from:
        conds.append("ar.date >= ?")
        params.append(filters.date_from)
    if filters.date_to:
        conds.append("ar.date <= ?")
        params.append(filters.date_to)
    if filters.practices or filters.levels:
        conds.append("1=1")  # force join filtering below

    where = (" WHERE " + " AND ".join(conds)) if conds else ""

    # Build practice/level sub-filter
    join_filter = ""
    if filters.practices:
        placeholders = ",".join("?" for _ in filters.practices)
        join_filter += f" AND emp.practice IN ({placeholders})"
        params.extend(filters.practices)
    if filters.levels:
        placeholders = ",".join("?" for _ in filters.levels)
        join_filter += f" AND emp.level IN ({placeholders})"
        params.extend(filters.levels)

    need_join = bool(filters.practices or filters.levels)
    join_clause = """
    JOIN sessions s ON ar.session_id = s.session_id
    JOIN employees emp ON s.user_email = emp.email
    """ if need_join else ""

    # Remove the dummy 1=1 if present alone
    conds_clean = [c for c in conds if c != "1=1"]
    if need_join:
        if filters.practices:
            placeholders = ",".join("?" for _ in filters.practices)
            conds_clean.append(f"emp.practice IN ({placeholders})")
        if filters.levels:
            placeholders = ",".join("?" for _ in filters.levels)
            conds_clean.append(f"emp.level IN ({placeholders})")

    # Simpler approach: just do the full join always for correctness
    all_conds: list[str] = []
    all_params: list = []
    if filters.date_from:
        all_conds.append("ar.date >= ?")
        all_params.append(filters.date_from)
    if filters.date_to:
        all_conds.append("ar.date <= ?")
        all_params.append(filters.date_to)
    if filters.practices:
        placeholders = ",".join("?" for _ in filters.practices)
        all_conds.append(f"emp.practice IN ({placeholders})")
        all_params.extend(filters.practices)
    if filters.levels:
        placeholders = ",".join("?" for _ in filters.levels)
        all_conds.append(f"emp.level IN ({placeholders})")
        all_params.extend(filters.levels)

    where_clean = (" WHERE " + " AND ".join(all_conds)) if all_conds else ""

    sql = f"""
    SELECT
        CAST(strftime('%w', ar.date) AS INTEGER) AS day_of_week,
        ar.hour,
        COUNT(*) AS event_count
    FROM api_requests ar
    JOIN sessions s ON ar.session_id = s.session_id
    JOIN employees emp ON s.user_email = emp.email
    {where_clean}
    GROUP BY day_of_week, ar.hour
    ORDER BY day_of_week, ar.hour
    """
    return _query(conn, sql, all_params)


# ---------------------------------------------------------------------------
# 3. Model breakdown
# ---------------------------------------------------------------------------


def get_model_breakdown(conn: sqlite3.Connection, filters: Filters) -> pd.DataFrame:
    """Per-model stats: count, total cost, avg cost, avg latency, tokens.

    Returns DataFrame: model, request_count, total_cost, avg_cost,
    avg_duration_ms, total_input_tokens, total_output_tokens,
    total_cache_read, total_cache_create.
    """
    where, params = _build_where(filters, date_col="ar.date")

    sql = f"""
    SELECT
        ar.model,
        COUNT(*) AS request_count,
        SUM(ar.cost_usd) AS total_cost,
        AVG(ar.cost_usd) AS avg_cost,
        AVG(ar.duration_ms) AS avg_duration_ms,
        SUM(ar.input_tokens) AS total_input_tokens,
        SUM(ar.output_tokens) AS total_output_tokens,
        SUM(ar.cache_read_tokens) AS total_cache_read,
        SUM(ar.cache_creation_tokens) AS total_cache_create
    FROM api_requests ar
    JOIN sessions s ON ar.session_id = s.session_id
    JOIN employees emp ON s.user_email = emp.email
    {where}
    GROUP BY ar.model
    ORDER BY total_cost DESC
    """
    return _query(conn, sql, params)


# ---------------------------------------------------------------------------
# 4. Tool usage
# ---------------------------------------------------------------------------


def get_tool_usage(conn: sqlite3.Connection, filters: Filters) -> pd.DataFrame:
    """Tool acceptance rates, success rates, avg durations.

    Returns DataFrame: tool_name, total_decisions, accepted, rejected,
    accept_rate, total_results, succeeded, failed, success_rate, avg_duration_ms.
    """
    conds, params = [], []
    if filters.date_from:
        conds.append("te.date >= ?")
        params.append(filters.date_from)
    if filters.date_to:
        conds.append("te.date <= ?")
        params.append(filters.date_to)
    if filters.practices:
        placeholders = ",".join("?" for _ in filters.practices)
        conds.append(f"emp.practice IN ({placeholders})")
        params.extend(filters.practices)
    if filters.levels:
        placeholders = ",".join("?" for _ in filters.levels)
        conds.append(f"emp.level IN ({placeholders})")
        params.extend(filters.levels)

    where = (" WHERE " + " AND ".join(conds)) if conds else ""

    sql = f"""
    SELECT
        te.tool_name,
        SUM(CASE WHEN te.event_type = 'tool_decision' THEN 1 ELSE 0 END) AS total_decisions,
        SUM(CASE WHEN te.event_type = 'tool_decision' AND te.decision = 'accept' THEN 1 ELSE 0 END) AS accepted,
        SUM(CASE WHEN te.event_type = 'tool_decision' AND te.decision = 'reject' THEN 1 ELSE 0 END) AS rejected,
        SUM(CASE WHEN te.event_type = 'tool_result' THEN 1 ELSE 0 END) AS total_results,
        SUM(CASE WHEN te.event_type = 'tool_result' AND te.success = 1 THEN 1 ELSE 0 END) AS succeeded,
        SUM(CASE WHEN te.event_type = 'tool_result' AND te.success = 0 THEN 1 ELSE 0 END) AS failed,
        AVG(CASE WHEN te.event_type = 'tool_result' THEN te.duration_ms END) AS avg_duration_ms
    FROM tool_events te
    JOIN sessions s ON te.session_id = s.session_id
    JOIN employees emp ON s.user_email = emp.email
    {where}
    GROUP BY te.tool_name
    ORDER BY total_decisions DESC
    """
    df = _query(conn, sql, params)
    if not df.empty:
        df["accept_rate"] = (df["accepted"] / df["total_decisions"].replace(0, 1) * 100).round(1)
        df["success_rate"] = (df["succeeded"] / df["total_results"].replace(0, 1) * 100).round(1)
    return df


# ---------------------------------------------------------------------------
# 5. Practice comparison
# ---------------------------------------------------------------------------


def get_practice_comparison(conn: sqlite3.Connection, filters: Filters) -> pd.DataFrame:
    """Per-practice cost, sessions, users, avg metrics.

    Returns DataFrame: practice, total_cost, total_sessions, active_users,
    avg_cost_per_user, avg_session_duration, total_requests.
    """
    conds, params = [], []
    if filters.date_from:
        conds.append("ar.date >= ?")
        params.append(filters.date_from)
    if filters.date_to:
        conds.append("ar.date <= ?")
        params.append(filters.date_to)
    if filters.models:
        placeholders = ",".join("?" for _ in filters.models)
        conds.append(f"ar.model IN ({placeholders})")
        params.extend(filters.models)

    where = (" WHERE " + " AND ".join(conds)) if conds else ""

    sql = f"""
    SELECT
        emp.practice,
        SUM(ar.cost_usd) AS total_cost,
        COUNT(DISTINCT ar.session_id) AS total_sessions,
        COUNT(DISTINCT s.user_email) AS active_users,
        COUNT(*) AS total_requests,
        AVG(s.duration_seconds) AS avg_session_duration
    FROM api_requests ar
    JOIN sessions s ON ar.session_id = s.session_id
    JOIN employees emp ON s.user_email = emp.email
    {where}
    GROUP BY emp.practice
    ORDER BY total_cost DESC
    """
    df = _query(conn, sql, params)
    if not df.empty:
        df["avg_cost_per_user"] = (df["total_cost"] / df["active_users"].replace(0, 1)).round(2)
    return df


# ---------------------------------------------------------------------------
# 6. Level analysis
# ---------------------------------------------------------------------------


def get_level_analysis(conn: sqlite3.Connection, filters: Filters) -> pd.DataFrame:
    """Per-level adoption and cost metrics.

    Returns DataFrame: level, level_numeric, total_cost, active_users,
    total_sessions, avg_cost_per_user, total_requests.
    """
    conds, params = [], []
    if filters.date_from:
        conds.append("ar.date >= ?")
        params.append(filters.date_from)
    if filters.date_to:
        conds.append("ar.date <= ?")
        params.append(filters.date_to)
    if filters.practices:
        placeholders = ",".join("?" for _ in filters.practices)
        conds.append(f"emp.practice IN ({placeholders})")
        params.extend(filters.practices)
    if filters.models:
        placeholders = ",".join("?" for _ in filters.models)
        conds.append(f"ar.model IN ({placeholders})")
        params.extend(filters.models)

    where = (" WHERE " + " AND ".join(conds)) if conds else ""

    sql = f"""
    SELECT
        emp.level,
        emp.level_numeric,
        SUM(ar.cost_usd) AS total_cost,
        COUNT(DISTINCT s.user_email) AS active_users,
        COUNT(DISTINCT ar.session_id) AS total_sessions,
        COUNT(*) AS total_requests
    FROM api_requests ar
    JOIN sessions s ON ar.session_id = s.session_id
    JOIN employees emp ON s.user_email = emp.email
    {where}
    GROUP BY emp.level, emp.level_numeric
    ORDER BY emp.level_numeric
    """
    df = _query(conn, sql, params)
    if not df.empty:
        df["avg_cost_per_user"] = (df["total_cost"] / df["active_users"].replace(0, 1)).round(2)
    return df


# ---------------------------------------------------------------------------
# 7. User leaderboard
# ---------------------------------------------------------------------------


def get_user_leaderboard(conn: sqlite3.Connection, filters: Filters) -> pd.DataFrame:
    """Top users by cost, sessions, requests.

    Returns DataFrame: email, full_name, practice, level, location,
    total_cost, total_sessions, total_requests, avg_cost_per_session.
    """
    where, params = _build_where(filters, date_col="ar.date")

    sql = f"""
    SELECT
        emp.email,
        emp.full_name,
        emp.practice,
        emp.level,
        emp.location,
        SUM(ar.cost_usd) AS total_cost,
        COUNT(DISTINCT ar.session_id) AS total_sessions,
        COUNT(*) AS total_requests
    FROM api_requests ar
    JOIN sessions s ON ar.session_id = s.session_id
    JOIN employees emp ON s.user_email = emp.email
    {where}
    GROUP BY emp.email
    ORDER BY total_cost DESC
    """
    df = _query(conn, sql, params)
    if not df.empty:
        df["avg_cost_per_session"] = (
            df["total_cost"] / df["total_sessions"].replace(0, 1)
        ).round(4)
    return df


# ---------------------------------------------------------------------------
# 8. Session analysis
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 9. Error analysis
# ---------------------------------------------------------------------------


def get_error_analysis(conn: sqlite3.Connection, filters: Filters) -> pd.DataFrame:
    """Error type distribution.

    Returns DataFrame: error_message, status_code, count, model.
    """
    conds, params = [], []
    if filters.date_from:
        conds.append("e.date >= ?")
        params.append(filters.date_from)
    if filters.date_to:
        conds.append("e.date <= ?")
        params.append(filters.date_to)
    if filters.models:
        placeholders = ",".join("?" for _ in filters.models)
        conds.append(f"e.model IN ({placeholders})")
        params.extend(filters.models)
    if filters.practices:
        placeholders = ",".join("?" for _ in filters.practices)
        conds.append(f"emp.practice IN ({placeholders})")
        params.extend(filters.practices)

    where = (" WHERE " + " AND ".join(conds)) if conds else ""

    sql = f"""
    SELECT
        e.error_message,
        e.status_code,
        e.model,
        COUNT(*) AS count
    FROM api_errors e
    JOIN sessions s ON e.session_id = s.session_id
    JOIN employees emp ON s.user_email = emp.email
    {where}
    GROUP BY e.error_message, e.status_code, e.model
    ORDER BY count DESC
    """
    return _query(conn, sql, params)


def get_error_rate_over_time(conn: sqlite3.Connection, filters: Filters) -> pd.DataFrame:
    """Daily error rate = errors / (errors + requests).

    Returns DataFrame: date, error_count, request_count, error_rate.
    """
    conds, params = [], []
    if filters.date_from:
        conds.append("dates.date >= ?")
        params.append(filters.date_from)
    if filters.date_to:
        conds.append("dates.date <= ?")
        params.append(filters.date_to)

    where = (" WHERE " + " AND ".join(conds)) if conds else ""

    sql = f"""
    SELECT
        dates.date,
        COALESCE(err.cnt, 0) AS error_count,
        COALESCE(req.cnt, 0) AS request_count
    FROM (SELECT DISTINCT date FROM api_requests UNION SELECT DISTINCT date FROM api_errors) dates
    LEFT JOIN (SELECT date, COUNT(*) AS cnt FROM api_errors GROUP BY date) err ON dates.date = err.date
    LEFT JOIN (SELECT date, COUNT(*) AS cnt FROM api_requests GROUP BY date) req ON dates.date = req.date
    {where}
    ORDER BY dates.date
    """
    df = _query(conn, sql, params)
    if not df.empty:
        total = df["error_count"] + df["request_count"]
        df["error_rate"] = (df["error_count"] / total.replace(0, 1) * 100).round(2)
    return df


# ---------------------------------------------------------------------------
# 10. Token efficiency
# ---------------------------------------------------------------------------


def get_token_efficiency(conn: sqlite3.Connection, filters: Filters) -> pd.DataFrame:
    """Cache hit rates and token ratios by model.

    Returns DataFrame: model, avg_input, avg_output, avg_cache_read,
    avg_cache_create, cache_hit_rate, output_input_ratio.
    """
    where, params = _build_where(filters, date_col="ar.date")

    sql = f"""
    SELECT
        ar.model,
        AVG(ar.input_tokens) AS avg_input,
        AVG(ar.output_tokens) AS avg_output,
        AVG(ar.cache_read_tokens) AS avg_cache_read,
        AVG(ar.cache_creation_tokens) AS avg_cache_create,
        SUM(ar.cache_read_tokens) AS total_cache_read,
        SUM(ar.input_tokens + ar.cache_read_tokens + ar.cache_creation_tokens) AS total_all_input
    FROM api_requests ar
    JOIN sessions s ON ar.session_id = s.session_id
    JOIN employees emp ON s.user_email = emp.email
    {where}
    GROUP BY ar.model
    """
    df = _query(conn, sql, params)
    if not df.empty:
        df["cache_hit_rate"] = (
            df["total_cache_read"] / df["total_all_input"].replace(0, 1) * 100
        ).round(1)
        df["output_input_ratio"] = (
            df["avg_output"] / df["avg_input"].replace(0, 1)
        ).round(2)
    return df


def get_daily_cache_rate(conn: sqlite3.Connection, filters: Filters) -> pd.DataFrame:
    """Daily cache hit rate over time.

    Returns DataFrame: date, cache_hit_rate.
    """
    where, params = _build_where(filters, date_col="ar.date")

    sql = f"""
    SELECT
        ar.date,
        SUM(ar.cache_read_tokens) AS total_cache_read,
        SUM(ar.input_tokens + ar.cache_read_tokens + ar.cache_creation_tokens) AS total_all_input
    FROM api_requests ar
    JOIN sessions s ON ar.session_id = s.session_id
    JOIN employees emp ON s.user_email = emp.email
    {where}
    GROUP BY ar.date
    ORDER BY ar.date
    """
    df = _query(conn, sql, params)
    if not df.empty:
        df["cache_hit_rate"] = (
            df["total_cache_read"] / df["total_all_input"].replace(0, 1) * 100
        ).round(1)
    return df


# ---------------------------------------------------------------------------
# 11. Prompt analysis
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Utility: metadata queries for filter options
# ---------------------------------------------------------------------------


def get_date_range(conn: sqlite3.Connection) -> tuple[str, str]:
    """Get min and max date from the data."""
    row = conn.execute("SELECT MIN(date), MAX(date) FROM api_requests").fetchone()
    return row[0], row[1]


def get_distinct_practices(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute("SELECT DISTINCT practice FROM employees ORDER BY practice").fetchall()
    return [r[0] for r in rows]


def get_distinct_levels(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT DISTINCT level FROM employees ORDER BY level_numeric"
    ).fetchall()
    return [r[0] for r in rows]


def get_distinct_models(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute("SELECT DISTINCT model FROM api_requests ORDER BY model").fetchall()
    return [r[0] for r in rows]


def get_kpi_summary(conn: sqlite3.Connection, filters: Filters) -> dict:
    """Quick KPI numbers for the executive summary."""
    where, params = _build_where(filters, date_col="ar.date")

    sql = f"""
    SELECT
        SUM(ar.cost_usd) AS total_cost,
        COUNT(*) AS total_requests,
        COUNT(DISTINCT ar.session_id) AS total_sessions,
        COUNT(DISTINCT s.user_email) AS active_users,
        AVG(ar.duration_ms) AS avg_latency_ms
    FROM api_requests ar
    JOIN sessions s ON ar.session_id = s.session_id
    JOIN employees emp ON s.user_email = emp.email
    {where}
    """
    row = conn.execute(sql, params).fetchone()

    # Error rate
    err_conds, err_params = [], []
    if filters.date_from:
        err_conds.append("date >= ?")
        err_params.append(filters.date_from)
    if filters.date_to:
        err_conds.append("date <= ?")
        err_params.append(filters.date_to)
    err_where = (" WHERE " + " AND ".join(err_conds)) if err_conds else ""
    err_count = conn.execute(
        f"SELECT COUNT(*) FROM api_errors{err_where}", err_params
    ).fetchone()[0]

    total_req = row["total_requests"] or 0
    error_rate = (err_count / (err_count + total_req) * 100) if (err_count + total_req) > 0 else 0

    # Avg session duration
    sess_conds, sess_params = [], []
    if filters.date_from:
        sess_conds.append("s.start_time >= ?")
        sess_params.append(filters.date_from)
    if filters.date_to:
        sess_conds.append("s.start_time <= ?")
        sess_params.append(filters.date_to + "T23:59:59")
    if filters.practices:
        placeholders = ",".join("?" for _ in filters.practices)
        sess_conds.append(f"emp.practice IN ({placeholders})")
        sess_params.extend(filters.practices)
    sess_where = (" WHERE " + " AND ".join(sess_conds)) if sess_conds else ""

    avg_dur = conn.execute(
        f"""SELECT AVG(s.duration_seconds) FROM sessions s
        JOIN employees emp ON s.user_email = emp.email
        {sess_where}""",
        sess_params,
    ).fetchone()[0] or 0

    return {
        "total_cost": row["total_cost"] or 0,
        "total_requests": total_req,
        "total_sessions": row["total_sessions"] or 0,
        "active_users": row["active_users"] or 0,
        "avg_latency_ms": row["avg_latency_ms"] or 0,
        "error_rate": round(error_rate, 2),
        "total_errors": err_count,
        "avg_session_duration": round(avg_dur, 1),
    }


def get_session_cost_stats(conn: sqlite3.Connection, filters: Filters) -> pd.DataFrame:
    """Per-session aggregated cost, duration, and turns for anomaly detection.

    Returns DataFrame: session_id, user_email, practice, start_date,
    total_cost, duration_seconds, num_turns.
    """
    conds, params = [], []
    if filters.date_from:
        conds.append("ar.date >= ?")
        params.append(filters.date_from)
    if filters.date_to:
        conds.append("ar.date <= ?")
        params.append(filters.date_to)
    if filters.practices:
        placeholders = ",".join("?" for _ in filters.practices)
        conds.append(f"emp.practice IN ({placeholders})")
        params.extend(filters.practices)
    if filters.levels:
        placeholders = ",".join("?" for _ in filters.levels)
        conds.append(f"emp.level IN ({placeholders})")
        params.extend(filters.levels)
    if filters.models:
        placeholders = ",".join("?" for _ in filters.models)
        conds.append(f"ar.model IN ({placeholders})")
        params.extend(filters.models)

    where = (" WHERE " + " AND ".join(conds)) if conds else ""

    sql = f"""
    SELECT
        ar.session_id,
        s.user_email,
        emp.practice,
        MIN(ar.date) AS start_date,
        SUM(ar.cost_usd) AS total_cost,
        s.duration_seconds,
        s.num_turns
    FROM api_requests ar
    JOIN sessions s ON ar.session_id = s.session_id
    JOIN employees emp ON s.user_email = emp.email
    {where}
    GROUP BY ar.session_id
    ORDER BY total_cost DESC
    """
    return _query(conn, sql, params)
