"""Model Analytics page.

Model cost breakdown, latency comparison, token efficiency, cache utilization.
"""

from __future__ import annotations

import sqlite3

import pandas as pd
import streamlit as st

from src.analytics.queries import (
    Filters,
    get_daily_cache_rate,
    get_daily_metrics,
    get_model_breakdown,
    get_token_efficiency,
    get_user_leaderboard,
)
from src.dashboard.components.charts import (
    MODEL_COLORS,
    bar_chart,
    donut_chart,
    line_chart,
    horizontal_bar,
)
from src.dashboard.components.metrics import format_currency, format_number, render_kpi_cards


def render(conn: sqlite3.Connection, filters: Filters) -> None:
    st.markdown("# Model Analytics")

    models = get_model_breakdown(conn, filters)
    if models.empty:
        st.info("No data for the selected filters.")
        return

    # KPIs
    render_kpi_cards([
        {"label": "Total Cost", "value": format_currency(models["total_cost"].sum())},
        {"label": "Total Requests", "value": format_number(int(models["request_count"].sum()))},
        {"label": "Models Used", "value": str(len(models))},
        {"label": "Avg Latency", "value": f"{models['avg_duration_ms'].mean():.0f}ms"},
    ])

    st.markdown("---")

    # Cost breakdown: donut + bar
    col1, col2 = st.columns(2)
    with col1:
        fig = donut_chart(models, values="total_cost", names="model", title="Cost Share by Model")
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        fig = bar_chart(models, x="model", y="total_cost", title="Total Cost by Model", color="model")
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")
    st.subheader("Latency & Token Efficiency")

    col3, col4 = st.columns(2)
    with col3:
        fig = bar_chart(
            models, x="model", y="avg_duration_ms",
            title="Avg Latency by Model (ms)", color="model",
        )
        st.plotly_chart(fig, use_container_width=True)

    with col4:
        eff = get_token_efficiency(conn, filters)
        if not eff.empty:
            fig = bar_chart(
                eff, x="model", y="cache_hit_rate",
                title="Cache Hit Rate by Model (%)", color="model",
            )
            st.plotly_chart(fig, use_container_width=True)

    # Daily cost by model (stacked area)
    st.markdown("---")
    st.subheader("Daily Cost Trend by Model")
    daily = get_daily_metrics(conn, filters)
    if not daily.empty:
        # We need per-model daily — use the daily_cost_summary table directly
        conds, params = [], []
        if filters.date_from:
            conds.append("date >= ?")
            params.append(filters.date_from)
        if filters.date_to:
            conds.append("date <= ?")
            params.append(filters.date_to)
        if filters.practices:
            placeholders = ",".join("?" for _ in filters.practices)
            conds.append(f"practice IN ({placeholders})")
            params.extend(filters.practices)
        if filters.models:
            placeholders = ",".join("?" for _ in filters.models)
            conds.append(f"model IN ({placeholders})")
            params.extend(filters.models)

        where = (" WHERE " + " AND ".join(conds)) if conds else ""
        sql = f"""
        SELECT date, model, SUM(total_cost) AS cost
        FROM daily_cost_summary {where}
        GROUP BY date, model ORDER BY date
        """
        daily_model = pd.read_sql_query(sql, conn, params=params)
        if not daily_model.empty:
            fig = line_chart(
                daily_model, x="date", y="cost", color="model",
                title="Daily Cost by Model", color_map=MODEL_COLORS,
            )
            st.plotly_chart(fig, use_container_width=True)

    # Cache utilization trend
    st.markdown("---")
    st.subheader("Cache Utilization Over Time")
    cache_df = get_daily_cache_rate(conn, filters)
    if not cache_df.empty:
        fig = line_chart(cache_df, x="date", y="cache_hit_rate", title="Daily Cache Hit Rate (%)")
        st.plotly_chart(fig, use_container_width=True)

    # Top users by cost
    st.markdown("---")
    st.subheader("Top 20 Users by Cost")
    users = get_user_leaderboard(conn, filters)
    if not users.empty:
        top20 = users.head(20).sort_values("total_cost")
        fig = horizontal_bar(
            top20, x="total_cost", y="full_name",
            title="Top Users by Total Cost", color="practice",
        )
        st.plotly_chart(fig, use_container_width=True, key="cost_users")
