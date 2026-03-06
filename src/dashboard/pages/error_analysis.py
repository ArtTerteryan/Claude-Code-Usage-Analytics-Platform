"""Errors & Reliability page.

Error rate over time, error type breakdown, error rate by model,
status code distribution, retry analysis.
"""

from __future__ import annotations

import sqlite3

import pandas as pd
import streamlit as st

from src.analytics.queries import (
    Filters,
    get_error_analysis,
    get_error_rate_over_time,
    get_kpi_summary,
)
from src.dashboard.components.charts import (
    bar_chart,
    donut_chart,
    horizontal_bar,
    line_chart,
    COLORS,
)
from src.dashboard.components.metrics import format_number, format_pct, render_kpi_cards


def render(conn: sqlite3.Connection, filters: Filters) -> None:
    st.markdown("# Errors & Reliability")

    kpi = get_kpi_summary(conn, filters)

    render_kpi_cards([
        {"label": "Total Errors", "value": format_number(kpi["total_errors"])},
        {"label": "Error Rate", "value": format_pct(kpi["error_rate"])},
        {"label": "Total Requests", "value": format_number(kpi["total_requests"])},
        {"label": "Avg Latency", "value": f"{kpi['avg_latency_ms']:.0f}ms"},
    ])

    st.markdown("---")

    # Error rate over time
    st.subheader("Error Rate Over Time")
    rate_df = get_error_rate_over_time(conn, filters)
    if not rate_df.empty:
        fig = line_chart(rate_df, x="date", y="error_rate", title="Daily Error Rate (%)")
        st.plotly_chart(fig, use_container_width=True)

        col1, col2 = st.columns(2)
        with col1:
            fig = bar_chart(rate_df, x="date", y="error_count", title="Daily Error Count")
            st.plotly_chart(fig, use_container_width=True)
        with col2:
            fig = line_chart(rate_df, x="date", y="request_count", title="Daily Request Count")
            st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")

    # Error breakdown
    errors = get_error_analysis(conn, filters)
    if errors.empty:
        st.info("No errors in the selected period.")
        return

    st.subheader("Error Type Breakdown")
    col3, col4 = st.columns(2)

    with col3:
        by_type = errors.groupby("error_message", as_index=False)["count"].sum()
        by_type = by_type.sort_values("count", ascending=False)
        # Shorten long error messages for display
        by_type["error_short"] = by_type["error_message"].str[:50]
        fig = horizontal_bar(
            by_type, x="count", y="error_short",
            title="Errors by Type",
        )
        st.plotly_chart(fig, use_container_width=True)

    with col4:
        by_status = errors.groupby("status_code", as_index=False)["count"].sum()
        by_status = by_status.sort_values("count", ascending=False)
        fig = donut_chart(
            by_status, values="count", names="status_code",
            title="Errors by Status Code",
        )
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")

    # Error rate by model
    st.subheader("Error Rate by Model")
    by_model = errors.groupby("model", as_index=False)["count"].sum()
    by_model = by_model.sort_values("count", ascending=False)

    # Get request counts per model for rate calculation
    model_req_sql = "SELECT model, COUNT(*) AS requests FROM api_requests GROUP BY model"
    model_req = pd.read_sql_query(model_req_sql, conn)
    model_merged = by_model.merge(model_req, on="model", how="left")
    model_merged["error_rate"] = (
        model_merged["count"] / (model_merged["count"] + model_merged["requests"]) * 100
    ).round(2)

    col5, col6 = st.columns(2)
    with col5:
        fig = bar_chart(
            model_merged, x="model", y="count",
            title="Error Count by Model", color="model",
        )
        st.plotly_chart(fig, use_container_width=True)
    with col6:
        fig = bar_chart(
            model_merged, x="model", y="error_rate",
            title="Error Rate by Model (%)", color="model",
        )
        st.plotly_chart(fig, use_container_width=True)

    # Retry attempts distribution
    st.markdown("---")
    st.subheader("Retry Attempts Distribution")

    retry_conds, retry_params = [], []
    if filters.date_from:
        retry_conds.append("date >= ?")
        retry_params.append(filters.date_from)
    if filters.date_to:
        retry_conds.append("date <= ?")
        retry_params.append(filters.date_to)
    retry_where = (" WHERE " + " AND ".join(retry_conds)) if retry_conds else ""

    retry_sql = f"""
    SELECT attempt, COUNT(*) AS count
    FROM api_errors {retry_where}
    GROUP BY attempt ORDER BY attempt
    """
    retry_df = pd.read_sql_query(retry_sql, conn, params=retry_params)
    if not retry_df.empty:
        retry_df["attempt"] = retry_df["attempt"].astype(str)
        fig = bar_chart(retry_df, x="attempt", y="count", title="Retry Attempt Distribution")
        st.plotly_chart(fig, use_container_width=True)

    # Detail table
    with st.expander("Full Error Details"):
        st.dataframe(errors, use_container_width=True, hide_index=True)
