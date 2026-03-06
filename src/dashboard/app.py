"""Main Streamlit dashboard application.

Entry point for the multi-page analytics dashboard.
Run with: streamlit run src/dashboard/app.py
"""

from __future__ import annotations

import streamlit as st

from src.config import DB_PATH
from src.database.connection import get_read_connection
from src.dashboard.components.filters import render_sidebar_filters
from src.dashboard.pages import (
    advanced_insights,
    cost_analysis,
    error_analysis,
    overview,
    team_insights,
    tool_usage,
)

PAGES = {
    "Executive Summary": overview,
    "Model Analytics": cost_analysis,
    "Tool Usage": tool_usage,
    "Team Insights": team_insights,
    "Errors & Reliability": error_analysis,
    "Advanced Analytics": advanced_insights,
}


def main() -> None:
    st.set_page_config(
        page_title="Claude Code Analytics",
        page_icon="📊",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # Hide Streamlit's auto-generated multi-page navigation
    st.markdown(
        "<style>[data-testid='stSidebarNav']{display:none}</style>",
        unsafe_allow_html=True,
    )

    # Branding
    st.sidebar.markdown(
        "# 📊 Claude Code\n### Telemetry Analytics"
    )
    st.sidebar.markdown("---")

    # Navigation
    page_name = st.sidebar.radio("Navigate", list(PAGES.keys()), label_visibility="collapsed")

    # DB connection (cached for session)
    conn = _get_connection()

    # Sidebar filters
    filters = render_sidebar_filters(conn)

    st.sidebar.markdown("---")
    st.sidebar.caption("Built for Provectus")

    # Render selected page
    PAGES[page_name].render(conn, filters)


@st.cache_resource
def _get_connection():
    return get_read_connection(DB_PATH)


if __name__ == "__main__":
    main()
