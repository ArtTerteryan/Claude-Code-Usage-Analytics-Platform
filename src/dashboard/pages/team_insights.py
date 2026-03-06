"""Team Insights page.

Practice comparison, cost per user by practice, level-based adoption,
geographic distribution.
"""

from __future__ import annotations

import sqlite3

import pandas as pd
import streamlit as st

from src.analytics.queries import (
    Filters,
    get_level_analysis,
    get_practice_comparison,
    get_user_leaderboard,
)
from src.dashboard.components.charts import (
    bar_chart,
    donut_chart,
    horizontal_bar,
    COLORS,
)
from src.dashboard.components.metrics import (
    format_currency,
    format_number,
    render_kpi_cards,
)


def render(conn: sqlite3.Connection, filters: Filters) -> None:
    st.markdown("# Team Insights")

    practices = get_practice_comparison(conn, filters)
    if practices.empty:
        st.info("No data for the selected filters.")
        return

    # KPIs
    render_kpi_cards([
        {"label": "Practices", "value": str(len(practices))},
        {"label": "Total Users", "value": format_number(int(practices["active_users"].sum()))},
        {"label": "Total Sessions", "value": format_number(int(practices["total_sessions"].sum()))},
        {"label": "Total Cost", "value": format_currency(practices["total_cost"].sum())},
    ])

    st.markdown("---")

    # Practice comparison
    st.subheader("Practice Comparison")
    col1, col2 = st.columns(2)

    with col1:
        fig = bar_chart(
            practices, x="practice", y="total_cost",
            title="Total Cost by Practice",
        )
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        fig = bar_chart(
            practices, x="practice", y="avg_cost_per_user",
            title="Avg Cost per User by Practice",
        )
        st.plotly_chart(fig, use_container_width=True)

    col3, col4 = st.columns(2)

    with col3:
        fig = bar_chart(
            practices, x="practice", y="active_users",
            title="Active Users by Practice",
        )
        st.plotly_chart(fig, use_container_width=True)

    with col4:
        fig = bar_chart(
            practices, x="practice", y="total_sessions",
            title="Sessions by Practice",
        )
        st.plotly_chart(fig, use_container_width=True)

    # Practice details table
    with st.expander("Practice Details"):
        display = practices[[
            "practice", "total_cost", "active_users", "total_sessions",
            "total_requests", "avg_cost_per_user"
        ]].copy()
        display["total_cost"] = display["total_cost"].round(2)
        display["avg_session_duration"] = practices["avg_session_duration"].round(0)
        st.dataframe(display, use_container_width=True, hide_index=True)

    st.markdown("---")

    # Level analysis
    st.subheader("Adoption by Seniority Level")
    levels = get_level_analysis(conn, filters)
    if not levels.empty:
        col5, col6 = st.columns(2)
        with col5:
            fig = bar_chart(
                levels, x="level", y="total_cost",
                title="Total Cost by Level",
            )
            st.plotly_chart(fig, use_container_width=True)

        with col6:
            fig = bar_chart(
                levels, x="level", y="avg_cost_per_user",
                title="Avg Cost per User by Level",
            )
            st.plotly_chart(fig, use_container_width=True)

        col7, col8 = st.columns(2)
        with col7:
            fig = bar_chart(
                levels, x="level", y="active_users",
                title="Active Users by Level",
            )
            st.plotly_chart(fig, use_container_width=True)

        with col8:
            fig = bar_chart(
                levels, x="level", y="total_sessions",
                title="Sessions by Level",
            )
            st.plotly_chart(fig, use_container_width=True)

    # Geographic distribution
    st.markdown("---")
    st.subheader("Geographic Distribution")

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
    where = (" WHERE " + " AND ".join(conds)) if conds else ""

    geo_sql = f"""
    SELECT
        emp.location,
        COUNT(DISTINCT s.user_email) AS users,
        COUNT(DISTINCT ar.session_id) AS sessions,
        SUM(ar.cost_usd) AS total_cost
    FROM api_requests ar
    JOIN sessions s ON ar.session_id = s.session_id
    JOIN employees emp ON s.user_email = emp.email
    {where}
    GROUP BY emp.location
    ORDER BY total_cost DESC
    """
    geo_df = pd.read_sql_query(geo_sql, conn, params=params)
    if not geo_df.empty:
        col9, col10 = st.columns(2)
        with col9:
            fig = donut_chart(
                geo_df, values="total_cost", names="location",
                title="Cost by Location",
            )
            st.plotly_chart(fig, use_container_width=True)
        with col10:
            fig = bar_chart(
                geo_df, x="location", y="users",
                title="Active Users by Location",
            )
            st.plotly_chart(fig, use_container_width=True)

    # User leaderboard
    st.markdown("---")
    st.subheader("User Leaderboard")
    users = get_user_leaderboard(conn, filters)
    if not users.empty:
        display = users[[
            "full_name", "practice", "level", "location",
            "total_cost", "total_sessions", "total_requests", "avg_cost_per_session"
        ]].head(30).copy()
        display["total_cost"] = display["total_cost"].round(2)
        display["avg_cost_per_session"] = display["avg_cost_per_session"].round(4)
        st.dataframe(display, use_container_width=True, hide_index=True)
