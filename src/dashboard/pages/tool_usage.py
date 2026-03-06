"""Tool Usage page.

Tool popularity, acceptance rates, success rates, duration analysis.
"""

from __future__ import annotations

import sqlite3

import pandas as pd
import streamlit as st

from src.analytics.queries import Filters, get_tool_usage
from src.dashboard.components.charts import (
    bar_chart,
    horizontal_bar,
    heatmap,
    COLORS,
)
from src.dashboard.components.metrics import format_number, format_pct, render_kpi_cards


def render(conn: sqlite3.Connection, filters: Filters) -> None:
    st.markdown("# Tool Usage Analytics")

    tools = get_tool_usage(conn, filters)
    if tools.empty:
        st.info("No tool data for the selected filters.")
        return

    total_decisions = int(tools["total_decisions"].sum())
    total_results = int(tools["total_results"].sum())
    overall_accept = tools["accepted"].sum() / max(tools["total_decisions"].sum(), 1) * 100
    overall_success = tools["succeeded"].sum() / max(tools["total_results"].sum(), 1) * 100

    render_kpi_cards([
        {"label": "Total Tool Decisions", "value": format_number(total_decisions)},
        {"label": "Total Executions", "value": format_number(total_results)},
        {"label": "Overall Accept Rate", "value": format_pct(overall_accept)},
        {"label": "Overall Success Rate", "value": format_pct(overall_success)},
    ])

    st.markdown("---")

    # Tool frequency bar chart
    st.subheader("Tool Popularity")
    top_tools = tools.head(15).sort_values("total_decisions")
    fig = horizontal_bar(
        top_tools, x="total_decisions", y="tool_name",
        title="Tool Usage Frequency (Decisions)",
    )
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")

    # Accept / Reject rates + Success / Failure rates
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Acceptance Rate by Tool")
        accept_df = tools[tools["total_decisions"] > 0].copy()
        accept_df = accept_df.sort_values("accept_rate")

        fig = horizontal_bar(
            accept_df, x="accept_rate", y="tool_name",
            title="Accept Rate (%)",
        )
        fig.update_xaxes(range=[90, 100])
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("Success Rate by Tool")
        success_df = tools[tools["total_results"] > 0].copy()
        success_df = success_df.sort_values("success_rate")

        fig = horizontal_bar(
            success_df, x="success_rate", y="tool_name",
            title="Execution Success Rate (%)",
        )
        fig.update_xaxes(range=[85, 100])
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")

    # Duration analysis
    st.subheader("Average Execution Duration by Tool")
    duration_df = tools[tools["avg_duration_ms"].notna()].copy()
    duration_df = duration_df.sort_values("avg_duration_ms", ascending=False)

    fig = horizontal_bar(
        duration_df, x="avg_duration_ms", y="tool_name",
        title="Avg Duration (ms) — Log Scale",
    )
    fig.update_xaxes(type="log")
    st.plotly_chart(fig, use_container_width=True)

    # Tool mix by practice
    st.markdown("---")
    st.subheader("Tool Mix by Practice")
    conds, params = [], []
    if filters.date_from:
        conds.append("te.date >= ?")
        params.append(filters.date_from)
    if filters.date_to:
        conds.append("te.date <= ?")
        params.append(filters.date_to)
    where = (" WHERE " + " AND ".join(conds)) if conds else ""

    sql = f"""
    SELECT emp.practice, te.tool_name, COUNT(*) AS cnt
    FROM tool_events te
    JOIN sessions s ON te.session_id = s.session_id
    JOIN employees emp ON s.user_email = emp.email
    {where + (" AND " if where else " WHERE ") + "te.event_type = 'tool_decision'"}
    GROUP BY emp.practice, te.tool_name
    ORDER BY cnt DESC
    """
    mix_df = pd.read_sql_query(sql, conn, params=params)
    if not mix_df.empty:
        # Show top 8 tools per practice as a heatmap
        top8 = tools.head(8)["tool_name"].tolist()
        mix_filtered = mix_df[mix_df["tool_name"].isin(top8)]
        if not mix_filtered.empty:
            fig = heatmap(
                mix_filtered, x="tool_name", y="practice", z="cnt",
                title="Tool Usage Count by Practice (Top 8 Tools)",
                height=350,
                color_scale="Blues",
            )
            st.plotly_chart(fig, use_container_width=True)

    # Detail table
    with st.expander("Full Tool Statistics Table"):
        display_df = tools[[
            "tool_name", "total_decisions", "accepted", "rejected",
            "accept_rate", "total_results", "succeeded", "failed",
            "success_rate", "avg_duration_ms"
        ]].copy()
        display_df["avg_duration_ms"] = display_df["avg_duration_ms"].round(0)
        st.dataframe(display_df, use_container_width=True, hide_index=True)
