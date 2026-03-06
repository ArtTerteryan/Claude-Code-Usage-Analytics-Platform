"""Executive Summary page.

KPI cards, daily cost trend, daily request volume, hourly activity heatmap.
"""

from __future__ import annotations

import sqlite3

import streamlit as st

from src.analytics.queries import (
    Filters,
    get_daily_metrics,
    get_hourly_activity,
    get_kpi_summary,
    get_model_breakdown,
    get_tool_usage,
)
from src.dashboard.components.charts import (
    area_chart,
    bar_chart,
    donut_chart,
    heatmap,
    horizontal_bar,
    line_chart,
)
from src.dashboard.components.metrics import (
    format_currency,
    format_duration,
    format_number,
    format_pct,
    render_kpi_cards,
)


def render(conn: sqlite3.Connection, filters: Filters) -> None:
    st.markdown("# Executive Summary")

    # KPIs
    kpi = get_kpi_summary(conn, filters)
    render_kpi_cards([
        {"label": "Total Cost", "value": format_currency(kpi["total_cost"])},
        {"label": "Active Users", "value": format_number(kpi["active_users"])},
        {"label": "Sessions", "value": format_number(kpi["total_sessions"])},
        {"label": "API Requests", "value": format_number(kpi["total_requests"])},
        {"label": "Error Rate", "value": format_pct(kpi["error_rate"])},
        {"label": "Avg Session", "value": format_duration(kpi["avg_session_duration"])},
    ])

    st.markdown("---")

    # Daily cost trend + daily requests
    daily = get_daily_metrics(conn, filters)
    if not daily.empty:
        col1, col2 = st.columns(2)
        with col1:
            fig = area_chart(daily, x="date", y="total_cost", title="Daily Cost ($)")
            st.plotly_chart(fig, use_container_width=True)
        with col2:
            fig = line_chart(daily, x="date", y="total_requests", title="Daily API Requests")
            st.plotly_chart(fig, use_container_width=True)

        col3, col4 = st.columns(2)
        with col3:
            fig = line_chart(daily, x="date", y="active_users", title="Daily Active Users")
            st.plotly_chart(fig, use_container_width=True)
        with col4:
            fig = bar_chart(daily, x="date", y="total_errors", title="Daily Errors")
            st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")

    # Model cost donut + tool ranking
    col5, col6 = st.columns(2)
    with col5:
        models = get_model_breakdown(conn, filters)
        if not models.empty:
            fig = donut_chart(models, values="total_cost", names="model", title="Cost by Model")
            st.plotly_chart(fig, use_container_width=True)

    with col6:
        tools = get_tool_usage(conn, filters)
        if not tools.empty:
            top10 = tools.head(10).sort_values("total_decisions")
            fig = horizontal_bar(
                top10, x="total_decisions", y="tool_name", title="Top 10 Tools"
            )
            st.plotly_chart(fig, use_container_width=True)

    # Hourly heatmap
    hourly = get_hourly_activity(conn, filters)
    if not hourly.empty:
        day_names = {0: "Sun", 1: "Mon", 2: "Tue", 3: "Wed", 4: "Thu", 5: "Fri", 6: "Sat"}
        hourly["day_name"] = hourly["day_of_week"].map(day_names)
        fig = heatmap(
            hourly, x="hour", y="day_name", z="event_count",
            title="API Requests by Hour & Day of Week",
            height=300,
        )
        st.plotly_chart(fig, use_container_width=True)
