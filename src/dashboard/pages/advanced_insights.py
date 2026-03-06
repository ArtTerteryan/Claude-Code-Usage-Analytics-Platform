"""Advanced Analytics page — Anomaly Detection & Trend Forecasting."""

from __future__ import annotations

import sqlite3

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.analytics.queries import Filters, get_daily_metrics, get_session_cost_stats
from src.config import (
    CONFIDENCE_MULTIPLIER,
    FORECAST_HORIZON_DAYS,
    IQR_MULTIPLIER,
    SMA_WINDOW,
    ZSCORE_THRESHOLD,
)
from src.dashboard.components.charts import LAYOUT_DEFAULTS


# ---------------------------------------------------------------------------
# Anomaly detection helpers
# ---------------------------------------------------------------------------

def _modified_zscore(series: pd.Series) -> pd.Series:
    median = series.median()
    mad = (series - median).abs().median()
    if mad == 0:
        return pd.Series(0.0, index=series.index)
    return 0.6745 * (series - median) / mad


def _flag_anomalies(series: pd.Series) -> pd.Series:
    """Return boolean mask — True if Modified Z-Score OR IQR flags the point."""
    z_flag = _modified_zscore(series).abs() > ZSCORE_THRESHOLD
    q1, q3 = series.quantile(0.25), series.quantile(0.75)
    iqr = q3 - q1
    iqr_flag = (series < q1 - IQR_MULTIPLIER * iqr) | (series > q3 + IQR_MULTIPLIER * iqr)
    return z_flag | iqr_flag


# ---------------------------------------------------------------------------
# Page entry point
# ---------------------------------------------------------------------------

def render(conn: sqlite3.Connection, filters: Filters) -> None:
    st.markdown("# Advanced Analytics")

    tab1, tab2 = st.tabs(["Anomaly Detection", "Trend Forecasting"])

    with tab1:
        _render_anomaly_detection(conn, filters)

    with tab2:
        _render_trend_forecasting(conn, filters)


# ---------------------------------------------------------------------------
# Anomaly Detection
# ---------------------------------------------------------------------------

def _render_anomaly_detection(conn: sqlite3.Connection, filters: Filters) -> None:
    daily = get_daily_metrics(conn, filters)
    if daily.empty:
        st.info("No data for the selected filters.")
        return

    # --- Daily cost anomalies ---
    st.subheader("Daily Cost Anomalies")
    daily = daily.copy()
    daily["is_anomaly"] = _flag_anomalies(daily["total_cost"])
    n_anom = int(daily["is_anomaly"].sum())

    c1, c2, c3 = st.columns(3)
    c1.metric("Days Analyzed", len(daily))
    c2.metric("Anomalous Days", n_anom)
    c3.metric("Anomaly Rate", f"{n_anom / len(daily) * 100:.1f}%")

    normal = daily[~daily["is_anomaly"]]
    anomalous = daily[daily["is_anomaly"]]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=normal["date"], y=normal["total_cost"],
        mode="markers", name="Normal",
        marker=dict(color="#6366F1", size=7, opacity=0.7),
        hovertemplate="<b>%{x}</b><br>Cost: $%{y:.4f}<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=anomalous["date"], y=anomalous["total_cost"],
        mode="markers", name="Anomaly",
        marker=dict(color="#EF4444", size=12, symbol="x", line=dict(width=2)),
        hovertemplate="<b>%{x}</b><br>Cost: $%{y:.4f}  ANOMALY<extra></extra>",
    ))
    fig.update_layout(title="Daily Cost — Anomaly Scatter", height=400, **LAYOUT_DEFAULTS)
    fig.update_xaxes(showgrid=True, gridcolor="rgba(128,128,128,0.1)")
    fig.update_yaxes(showgrid=True, gridcolor="rgba(128,128,128,0.1)", title="Cost (USD)")
    st.plotly_chart(fig, use_container_width=True)

    if not anomalous.empty:
        st.markdown("**Anomalous Days**")
        disp = anomalous[["date", "total_cost", "total_requests", "active_users"]].copy()
        disp["total_cost"] = disp["total_cost"].apply(lambda v: f"${v:.4f}")
        st.dataframe(disp, use_container_width=True, hide_index=True)

    st.markdown("---")

    # --- Session anomalies ---
    st.subheader("Anomalous Sessions")
    sessions = get_session_cost_stats(conn, filters)
    if sessions.empty:
        st.info("No session data available.")
        return

    sessions = sessions.copy()
    sessions["is_anomaly"] = _flag_anomalies(sessions["total_cost"])
    n_sess = int(sessions["is_anomaly"].sum())

    c1, c2, c3 = st.columns(3)
    c1.metric("Total Sessions", f"{len(sessions):,}")
    c2.metric("Anomalous Sessions", f"{n_sess:,}")
    c3.metric("Session Anomaly Rate", f"{n_sess / len(sessions) * 100:.1f}%")

    norm_s = sessions[~sessions["is_anomaly"]]
    anom_s = sessions[sessions["is_anomaly"]]

    fig2 = go.Figure()
    fig2.add_trace(go.Scatter(
        x=norm_s["duration_seconds"] / 60,
        y=norm_s["total_cost"],
        mode="markers", name="Normal",
        marker=dict(color="#6366F1", size=norm_s["num_turns"].clip(upper=20).clip(lower=4), opacity=0.5),
        text=norm_s["num_turns"],
        hovertemplate="Duration: %{x:.1f} min<br>Cost: $%{y:.4f}<br>Turns: %{text}<extra>Normal</extra>",
    ))
    if not anom_s.empty:
        fig2.add_trace(go.Scatter(
            x=anom_s["duration_seconds"] / 60,
            y=anom_s["total_cost"],
            mode="markers", name="Anomaly",
            marker=dict(color="#EF4444", size=14, symbol="x", line=dict(width=2)),
            text=anom_s["user_email"],
            hovertemplate="Duration: %{x:.1f} min<br>Cost: $%{y:.4f}<br>User: %{text}<extra>Anomaly</extra>",
        ))
    fig2.update_layout(
        title="Session Cost vs Duration (marker size = turns)",
        height=400, **LAYOUT_DEFAULTS,
    )
    fig2.update_xaxes(title="Duration (minutes)", showgrid=True, gridcolor="rgba(128,128,128,0.1)")
    fig2.update_yaxes(title="Total Cost (USD)", showgrid=True, gridcolor="rgba(128,128,128,0.1)")
    st.plotly_chart(fig2, use_container_width=True)

    if not anom_s.empty:
        st.markdown("**Anomalous Sessions Detail**")
        disp_s = anom_s[["session_id", "user_email", "practice", "start_date",
                          "total_cost", "duration_seconds", "num_turns"]].copy()
        disp_s["total_cost"] = disp_s["total_cost"].apply(lambda v: f"${v:.4f}")
        disp_s["duration_seconds"] = disp_s["duration_seconds"].apply(lambda v: f"{v / 60:.1f} min")
        disp_s = disp_s.rename(columns={"duration_seconds": "duration"})
        st.dataframe(disp_s, use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# Trend Forecasting
# ---------------------------------------------------------------------------

def _render_trend_forecasting(conn: sqlite3.Connection, filters: Filters) -> None:
    daily = get_daily_metrics(conn, filters)
    if daily.empty or len(daily) < SMA_WINDOW + 1:
        st.info(f"Need at least {SMA_WINDOW + 1} days of data for forecasting.")
        return

    daily = daily.copy().sort_values("date").reset_index(drop=True)

    # --- Cost forecast ---
    st.subheader("7-Day Cost Forecast")
    _forecast_chart(
        dates=daily["date"],
        values=daily["total_cost"],
        title=f"Daily Cost Trend + {FORECAST_HORIZON_DAYS}-Day Forecast",
        y_label="Cost (USD)",
        value_fmt="${:.4f}",
        hist_color="#6366F1",
        forecast_color="#10B981",
        band_color="rgba(16,185,129,0.15)",
    )

    st.markdown("---")

    # --- Token forecast ---
    st.subheader("Token Consumption Forecast")
    total_tokens = daily["total_input_tokens"] + daily["total_output_tokens"]
    _forecast_chart(
        dates=daily["date"],
        values=total_tokens,
        title=f"Token Consumption + {FORECAST_HORIZON_DAYS}-Day Forecast",
        y_label="Total Tokens",
        value_fmt="{:,.0f}",
        hist_color="#8B5CF6",
        forecast_color="#EC4899",
        band_color="rgba(139,92,246,0.15)",
    )


def _forecast_chart(
    dates: pd.Series,
    values: pd.Series,
    title: str,
    y_label: str,
    value_fmt: str,
    hist_color: str,
    forecast_color: str,
    band_color: str,
) -> None:
    sma = values.rolling(SMA_WINDOW, min_periods=1).mean()

    x_num = np.arange(len(values))
    slope, intercept = np.polyfit(x_num, values, 1)
    residual_std = (values - (slope * x_num + intercept)).std()

    last_date = pd.to_datetime(dates.iloc[-1])
    future_x = np.arange(len(values), len(values) + FORECAST_HORIZON_DAYS)
    future_dates = pd.date_range(last_date + pd.Timedelta(days=1), periods=FORECAST_HORIZON_DAYS)
    forecast = slope * future_x + intercept
    upper = forecast + CONFIDENCE_MULTIPLIER * residual_std
    lower = (forecast - CONFIDENCE_MULTIPLIER * residual_std).clip(0)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=dates, y=values, mode="lines+markers", name="Historical",
        line=dict(color=hist_color, width=2), marker=dict(size=4),
        hovertemplate=f"<b>%{{x}}</b><br>{value_fmt.format(0).split('0')[0]}%{{y:.2f}}<extra>Historical</extra>",
    ))
    fig.add_trace(go.Scatter(
        x=dates, y=sma, mode="lines", name=f"SMA({SMA_WINDOW})",
        line=dict(color="#F59E0B", width=2, dash="dot"),
    ))
    fig.add_trace(go.Scatter(
        x=list(future_dates) + list(future_dates)[::-1],
        y=list(upper) + list(lower)[::-1],
        fill="toself", fillcolor=band_color,
        line=dict(color="rgba(0,0,0,0)"),
        name="95% Confidence", hoverinfo="skip",
    ))
    fig.add_trace(go.Scatter(
        x=future_dates, y=forecast, mode="lines+markers", name="Forecast",
        line=dict(color=forecast_color, width=2, dash="dash"),
        marker=dict(size=7, symbol="diamond"),
        hovertemplate="<b>%{x}</b><br>Forecast: %{y:.2f}<extra></extra>",
    ))
    fig.update_layout(title=title, height=450, **LAYOUT_DEFAULTS)
    fig.update_xaxes(showgrid=True, gridcolor="rgba(128,128,128,0.1)")
    fig.update_yaxes(title=y_label, showgrid=True, gridcolor="rgba(128,128,128,0.1)")
    st.plotly_chart(fig, use_container_width=True)

    forecast_df = pd.DataFrame({
        "Date": future_dates.strftime("%Y-%m-%d"),
        "Forecast": [value_fmt.format(v) for v in forecast],
        "Lower Bound (95%)": [value_fmt.format(v) for v in lower],
        "Upper Bound (95%)": [value_fmt.format(v) for v in upper],
    })
    st.dataframe(forecast_df, use_container_width=True, hide_index=True)
