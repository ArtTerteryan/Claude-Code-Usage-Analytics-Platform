"""KPI card rendering helpers."""

from __future__ import annotations

import streamlit as st


def render_kpi_cards(metrics: list[dict]) -> None:
    """Render a row of KPI cards using st.metric.

    Each dict should have: label, value, and optionally delta.
    """
    cols = st.columns(len(metrics))
    for col, m in zip(cols, metrics):
        col.metric(
            label=m["label"],
            value=m["value"],
            delta=m.get("delta"),
        )


def format_currency(value: float) -> str:
    """Format a float as USD currency string."""
    if abs(value) >= 1_000:
        return f"${value:,.0f}"
    return f"${value:,.2f}"


def format_number(value: int | float) -> str:
    """Format with thousands separators."""
    if isinstance(value, float):
        return f"{value:,.1f}"
    return f"{value:,}"


def format_duration(seconds: float) -> str:
    """Format seconds into a readable duration string."""
    if seconds < 60:
        return f"{seconds:.0f}s"
    if seconds < 3600:
        return f"{seconds / 60:.1f}m"
    return f"{seconds / 3600:.1f}h"


def format_pct(value: float) -> str:
    """Format a percentage."""
    return f"{value:.1f}%"
