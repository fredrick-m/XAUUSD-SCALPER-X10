"""Tests for the parameter optimizer."""
import pandas as pd
import numpy as np
import pytest


@pytest.fixture
def sample_df():
    """Create a small OHLCV DataFrame for testing."""
    np.random.seed(42)
    n = 2000
    base = 2000.0
    close = base + np.cumsum(np.random.randn(n) * 0.5)
    df = pd.DataFrame({
        "time": pd.date_range("2024-01-01", periods=n, freq="min"),
        "Open": close + np.random.randn(n) * 0.1,
        "High": close + abs(np.random.randn(n) * 0.3),
        "Low": close - abs(np.random.randn(n) * 0.3),
        "Close": close,
        "Volume": np.random.randint(100, 1000, n),
    })
    return df


def test_optimizer_imports():
    from engine.optimizer import optimize_strategy, composite_score
    assert callable(optimize_strategy)
    assert callable(composite_score)


def test_composite_score_calculation():
    from engine.optimizer import composite_score
    metrics = {
        "win_rate": 0.65,
        "profit_factor": 3.0,
        "max_drawdown": 0.20,
        "x10_count": 5,
        "total_trades": 200,
    }
    score = composite_score(metrics)
    assert isinstance(score, float)
    assert 0.0 <= score <= 1.0


def test_composite_score_zero_trades():
    from engine.optimizer import composite_score
    metrics = {
        "win_rate": 0.0,
        "profit_factor": 0.0,
        "max_drawdown": 1.0,
        "x10_count": 0,
        "total_trades": 0,
    }
    score = composite_score(metrics)
    assert score == 0.0


def test_split_data():
    from engine.optimizer import split_data
    df = pd.DataFrame({"A": range(100)})
    train, test = split_data(df, ratio=0.7)
    assert len(train) == 70
    assert len(test) == 30


def test_optimize_returns_best_params(sample_df):
    from engine.optimizer import optimize_strategy

    # Minimal strategy module mock
    class FakeModule:
        PARAMS = {"ema_fast": 5, "ema_slow": 20, "atr_period": 14, "sl_atr": 1.5, "tp_atr": 2.5}
        @staticmethod
        def generate_signals(df, p):
            import ta as ta_lib
            df["ATR"] = ta_lib.volatility.average_true_range(
                df["High"], df["Low"], df["Close"], window=p.get("atr_period", 14)
            )
            df["signal"] = 0
            return df

    param_space = {
        "sl_atr": (0.5, 3.0),
        "tp_atr": (1.0, 5.0),
    }

    best_params, best_score = optimize_strategy(
        module=FakeModule,
        df=sample_df,
        param_space=param_space,
        n_trials=5,
        split_ratio=0.7,
    )
    assert isinstance(best_params, dict)
    assert "sl_atr" in best_params
    assert "tp_atr" in best_params
    assert isinstance(best_score, float)
