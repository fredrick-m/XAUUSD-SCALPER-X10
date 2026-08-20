import numpy as np
import pandas as pd

from engine.backtest import dynamic_lot, run_simulation


def test_zero_risk_does_not_create_minimum_lot():
    assert dynamic_lot(500.0, 2.0, 0.0) == 0.0


def test_intrabar_stop_is_applied_before_timeout_close():
    df = pd.DataFrame(
        {
            "time": pd.date_range("2026-01-05 10:00", periods=3, freq="5min"),
            "Open": [100.0, 100.0, 105.0],
            "High": [100.5, 106.0, 106.0],
            "Low": [99.5, 98.0, 104.0],
            "Close": [100.0, 105.0, 105.0],
            "Volume": [100, 100, 100],
        }
    )
    signals = pd.Series([1, 0, 0])
    sl = pd.Series([99.0, np.nan, np.nan])
    tp = pd.Series([110.0, np.nan, np.nan])
    directions = pd.Series([1, 0, 0])

    metrics = run_simulation(
        df,
        signals,
        sl,
        tp,
        directions,
        risk_pct=0.01,
        spread_override=0.0,
        slippage_override=0.0,
        max_bars_in_trade=1,
        session_filter=False,
    )

    # Entry occurs at bar 1 open=100. That bar trades down to 98, through the
    # 99 stop, while closing at 105. A time-exit-first engine would incorrectly
    # book a profit; the realistic engine must book the stop loss instead.
    assert metrics["total_trades"] == 1
    assert metrics["final_balance"] < 500.0
    assert metrics["win_rate"] == 0.0
