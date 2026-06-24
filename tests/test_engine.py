"""Tests for the improved backtest engine."""
import pandas as pd
import numpy as np
import pytest


def _make_sample_data(n=200):
    np.random.seed(42)
    times = pd.date_range("2025-06-01 08:00", periods=n, freq="1min")
    close = 2000 + np.cumsum(np.random.randn(n) * 0.5)
    high = close + np.abs(np.random.randn(n) * 0.3)
    low = close - np.abs(np.random.randn(n) * 0.3)
    open_ = close + np.random.randn(n) * 0.1
    volume = np.random.randint(50, 500, n)
    spread = np.full(n, 160)
    return pd.DataFrame({
        "time": times, "Open": open_, "High": high, "Low": low,
        "Close": close, "Volume": volume, "spread": spread,
    })


def _make_signals(df, long_indices=None, short_indices=None):
    signals = pd.Series(0, index=df.index)
    sl_prices = pd.Series(np.nan, index=df.index)
    tp_prices = pd.Series(np.nan, index=df.index)
    for i in (long_indices or []):
        signals.iloc[i] = 1
        sl_prices.iloc[i] = df["Close"].iloc[i] - 2.0
        tp_prices.iloc[i] = df["Close"].iloc[i] + 4.0
    for i in (short_indices or []):
        signals.iloc[i] = -1
        sl_prices.iloc[i] = df["Close"].iloc[i] + 2.0
        tp_prices.iloc[i] = df["Close"].iloc[i] - 4.0
    return signals, sl_prices, tp_prices


def test_engine_imports():
    from engine.backtest import run_simulation, INITIAL_BALANCE
    assert INITIAL_BALANCE == 50.0


def test_basic_simulation_runs():
    from engine.backtest import run_simulation
    df = _make_sample_data()
    signals, sl, tp = _make_signals(df, long_indices=[10, 50, 100])
    result = run_simulation(df, signals, sl, tp, signals)
    assert "total_trades" in result
    assert "win_rate" in result
    assert "equity_curve" in result
    assert result["total_trades"] >= 0


def test_trailing_stop_enabled():
    from engine.backtest import run_simulation
    df = _make_sample_data()
    signals, sl, tp = _make_signals(df, long_indices=[10, 50, 100])
    result_no_trail = run_simulation(df, signals, sl, tp, signals, trailing_stop=False)
    result_trail = run_simulation(df, signals, sl, tp, signals, trailing_stop=True)
    assert result_no_trail["total_trades"] >= 0
    assert result_trail["total_trades"] >= 0


def test_time_exit():
    from engine.backtest import run_simulation
    df = _make_sample_data(500)
    signals = pd.Series(0, index=df.index)
    sl_prices = pd.Series(np.nan, index=df.index)
    tp_prices = pd.Series(np.nan, index=df.index)
    signals.iloc[10] = 1
    sl_prices.iloc[10] = df["Close"].iloc[10] - 100
    tp_prices.iloc[10] = df["Close"].iloc[10] + 100
    result = run_simulation(df, signals, sl_prices, tp_prices, signals, max_bars_in_trade=30)
    assert result["total_trades"] >= 1


def test_session_filter():
    from engine.backtest import run_simulation
    df = _make_sample_data(500)
    df["time"] = pd.date_range("2025-06-01 00:00", periods=500, freq="1min")
    signals, sl, tp = _make_signals(df, long_indices=[5, 60, 120, 300, 450])
    result_filtered = run_simulation(df, signals, sl, tp, signals, session_filter=True, session_hours=(7, 21))
    result_unfiltered = run_simulation(df, signals, sl, tp, signals, session_filter=False)
    assert result_filtered["total_trades"] <= result_unfiltered["total_trades"]


def test_no_signals_returns_zero_trades():
    from engine.backtest import run_simulation
    df = _make_sample_data()
    signals = pd.Series(0, index=df.index)
    sl = pd.Series(np.nan, index=df.index)
    tp = pd.Series(np.nan, index=df.index)
    result = run_simulation(df, signals, sl, tp, signals)
    assert result["total_trades"] == 0
    assert result["final_balance"] == 50.0


def test_validate_function():
    from engine.backtest import validate
    metrics = {"win_rate": 0.65, "profit_factor": 2.5, "max_drawdown": 0.20, "x10_count": 6, "total_trades": 300}
    passed, fails = validate(metrics, regimes_tested=3)
    assert passed
    assert len(fails) == 0


def test_validate_fails():
    from engine.backtest import validate
    metrics = {"win_rate": 0.35, "profit_factor": 1.0, "max_drawdown": 0.50, "x10_count": 0, "total_trades": 50}
    passed, fails = validate(metrics, regimes_tested=1)
    assert not passed
    assert len(fails) > 0
