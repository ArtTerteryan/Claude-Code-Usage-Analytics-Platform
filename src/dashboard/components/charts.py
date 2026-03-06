"""Reusable Plotly chart builders with consistent styling.

Every function takes a DataFrame and returns a plotly Figure.
Uses a single color palette defined here for the entire dashboard.
"""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# ---------------------------------------------------------------------------
# Color palette
# ---------------------------------------------------------------------------

COLORS = [
    "#6366F1",  # indigo
    "#EC4899",  # pink
    "#F59E0B",  # amber
    "#10B981",  # emerald
    "#3B82F6",  # blue
    "#8B5CF6",  # violet
    "#EF4444",  # red
    "#14B8A6",  # teal
    "#F97316",  # orange
    "#06B6D4",  # cyan
]

MODEL_COLORS = {
    "claude-haiku-4-5-20251001": "#10B981",
    "claude-opus-4-6": "#6366F1",
    "claude-opus-4-5-20251101": "#8B5CF6",
    "claude-sonnet-4-5-20250929": "#3B82F6",
    "claude-sonnet-4-6": "#06B6D4",
}

LAYOUT_DEFAULTS = dict(
    font=dict(family="Inter, system-ui, sans-serif", size=12),
    margin=dict(l=40, r=20, t=40, b=40),
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    hovermode="x unified",
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
)


def _apply_layout(fig: go.Figure, title: str = "", height: int = 400) -> go.Figure:
    fig.update_layout(title=title, height=height, **LAYOUT_DEFAULTS)
    fig.update_xaxes(showgrid=True, gridcolor="rgba(128,128,128,0.1)")
    fig.update_yaxes(showgrid=True, gridcolor="rgba(128,128,128,0.1)")
    return fig


# ---------------------------------------------------------------------------
# Chart builders
# ---------------------------------------------------------------------------


def line_chart(
    df: pd.DataFrame,
    x: str,
    y: str,
    color: str | None = None,
    title: str = "",
    height: int = 400,
    color_map: dict | None = None,
) -> go.Figure:
    fig = px.line(
        df, x=x, y=y, color=color,
        color_discrete_map=color_map or MODEL_COLORS,
        color_discrete_sequence=COLORS,
    )
    return _apply_layout(fig, title, height)


def area_chart(
    df: pd.DataFrame,
    x: str,
    y: str,
    color: str | None = None,
    title: str = "",
    height: int = 400,
) -> go.Figure:
    fig = px.area(
        df, x=x, y=y, color=color,
        color_discrete_map=MODEL_COLORS,
        color_discrete_sequence=COLORS,
    )
    return _apply_layout(fig, title, height)


def bar_chart(
    df: pd.DataFrame,
    x: str,
    y: str,
    color: str | None = None,
    orientation: str = "v",
    title: str = "",
    height: int = 400,
    text: str | None = None,
    barmode: str = "group",
) -> go.Figure:
    fig = px.bar(
        df, x=x, y=y, color=color, orientation=orientation,
        text=text,
        color_discrete_map=MODEL_COLORS,
        color_discrete_sequence=COLORS,
        barmode=barmode,
    )
    fig.update_traces(textposition="outside") if text else None
    return _apply_layout(fig, title, height)


def donut_chart(
    df: pd.DataFrame,
    values: str,
    names: str,
    title: str = "",
    height: int = 400,
    color_map: dict | None = None,
) -> go.Figure:
    fig = px.pie(
        df, values=values, names=names, hole=0.45,
        color=names,
        color_discrete_map=color_map or MODEL_COLORS,
        color_discrete_sequence=COLORS,
    )
    fig.update_traces(textposition="inside", textinfo="percent+label")
    return _apply_layout(fig, title, height)


def heatmap(
    df: pd.DataFrame,
    x: str,
    y: str,
    z: str,
    title: str = "",
    height: int = 400,
    color_scale: str = "Viridis",
) -> go.Figure:
    pivot = df.pivot_table(index=y, columns=x, values=z, aggfunc="sum").fillna(0)
    fig = go.Figure(data=go.Heatmap(
        z=pivot.values,
        x=pivot.columns.tolist(),
        y=pivot.index.tolist(),
        colorscale=color_scale,
        hoverongaps=False,
    ))
    return _apply_layout(fig, title, height)


def horizontal_bar(
    df: pd.DataFrame,
    x: str,
    y: str,
    title: str = "",
    height: int = 400,
    color: str | None = None,
    text: str | None = None,
) -> go.Figure:
    fig = px.bar(
        df, x=x, y=y, orientation="h", color=color, text=text,
        color_discrete_sequence=COLORS,
    )
    if text:
        fig.update_traces(textposition="outside")
    return _apply_layout(fig, title, height)


