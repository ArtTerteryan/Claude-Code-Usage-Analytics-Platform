"""Sidebar filter widgets for the dashboard.

Renders date range pickers, practice/level/model multiselects,
and returns a Filters instance for use by all pages.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime

import streamlit as st

from src.analytics.queries import (
    Filters,
    get_date_range,
    get_distinct_levels,
    get_distinct_models,
    get_distinct_practices,
)


def render_sidebar_filters(conn: sqlite3.Connection) -> Filters:
    """Render sidebar filter widgets and return active Filters."""
    st.sidebar.markdown("## Filters")

    # Date range
    date_min, date_max = get_date_range(conn)
    d_min = datetime.strptime(date_min, "%Y-%m-%d").date()
    d_max = datetime.strptime(date_max, "%Y-%m-%d").date()

    date_from = st.sidebar.date_input("Start date", value=d_min, min_value=d_min, max_value=d_max)
    date_to = st.sidebar.date_input("End date", value=d_max, min_value=d_min, max_value=d_max)

    st.sidebar.markdown("---")

    # Practice filter
    all_practices = get_distinct_practices(conn)
    practices = st.sidebar.multiselect("Practice", options=all_practices, default=[])

    # Level filter
    all_levels = get_distinct_levels(conn)
    levels = st.sidebar.multiselect("Level", options=all_levels, default=[])

    # Model filter
    all_models = get_distinct_models(conn)
    models = st.sidebar.multiselect("Model", options=all_models, default=[])

    return Filters(
        date_from=str(date_from),
        date_to=str(date_to),
        practices=practices,
        levels=levels,
        models=models,
    )
