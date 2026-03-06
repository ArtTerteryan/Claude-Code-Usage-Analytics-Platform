"""Tests for analytics computations — anomaly detection and forecasting."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.dashboard.pages.advanced_insights import _flag_anomalies, _modified_zscore


class TestModifiedZscore:
    def test_normal_values_have_low_scores(self) -> None:
        s = pd.Series([10.0, 10.1, 9.9, 10.2, 9.8, 10.0, 10.1])
        z = _modified_zscore(s)
        assert (z.abs() < 3.5).all()

    def test_outlier_has_high_score(self) -> None:
        # Need enough spread so MAD > 0
        s = pd.Series([10.0, 11.0, 9.0, 10.5, 9.5, 10.2, 9.8, 100.0])
        z = _modified_zscore(s)
        assert z.iloc[-1] > 3.5

    def test_handles_constant_array(self) -> None:
        s = pd.Series([5.0, 5.0, 5.0, 5.0])
        z = _modified_zscore(s)
        assert not z.isna().any()
        assert (z == 0.0).all()


class TestFlagAnomalies:
    def test_detects_obvious_outlier(self) -> None:
        values = [10.0] * 50 + [1000.0]
        s = pd.Series(values)
        flags = _flag_anomalies(s)
        assert flags.iloc[-1] is True or flags.iloc[-1] == True

    def test_few_anomalies_in_uniform_data(self) -> None:
        np.random.seed(42)
        s = pd.Series(np.random.normal(100, 1, 100))
        flags = _flag_anomalies(s)
        # Tight normal data should have very few (if any) false positives
        assert flags.sum() <= 2


class TestMovingAverage:
    def test_correct_window_size(self) -> None:
        s = pd.Series(range(20), dtype=float)
        sma = s.rolling(7, min_periods=1).mean()
        assert len(sma) == 20
        assert sma.iloc[9] == pytest.approx(sum(range(3, 10)) / 7)

    def test_min_periods_fills_early_values(self) -> None:
        s = pd.Series([1.0, 2.0, 3.0])
        sma = s.rolling(7, min_periods=1).mean()
        assert not sma.isna().any()
        assert sma.iloc[0] == pytest.approx(1.0)


class TestLinearTrend:
    def test_perfect_linear_data(self) -> None:
        x = np.arange(30)
        y = 2.0 * x + 5.0
        slope, intercept = np.polyfit(x, y, 1)
        assert slope == pytest.approx(2.0, abs=1e-10)
        assert intercept == pytest.approx(5.0, abs=1e-10)

    def test_returns_slope_and_intercept(self) -> None:
        x = np.arange(10)
        y = np.array([1.0, 3.0, 2.0, 5.0, 4.0, 6.0, 5.0, 8.0, 7.0, 9.0])
        slope, intercept = np.polyfit(x, y, 1)
        assert isinstance(slope, float)
        assert isinstance(intercept, float)
        assert slope > 0


class TestForecast:
    def test_forecast_extends_beyond_data(self) -> None:
        x = np.arange(30)
        slope, intercept = 1.5, 10.0
        future_x = np.arange(30, 37)
        forecast = slope * future_x + intercept
        assert len(forecast) == 7
        assert forecast[0] > slope * 29 + intercept

    def test_confidence_bands_contain_forecast(self) -> None:
        x = np.arange(30)
        y = 2.0 * x + 5.0 + np.random.normal(0, 1, 30)
        slope, intercept = np.polyfit(x, y, 1)
        std = (y - (slope * x + intercept)).std()
        future_x = np.arange(30, 37)
        forecast = slope * future_x + intercept
        upper = forecast + 1.96 * std
        lower = forecast - 1.96 * std
        assert (upper > forecast).all()
        assert (lower < forecast).all()
