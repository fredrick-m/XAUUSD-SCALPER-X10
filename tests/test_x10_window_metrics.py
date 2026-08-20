import pandas as pd

from engine.backtest import compute_x10_window_metrics


def _days(n):
    return pd.DataFrame({
        "time": pd.date_range("2026-01-05", periods=n, freq="D"),
        "Open": [2000.0] * n,
        "High": [2001.0] * n,
        "Low": [1999.0] * n,
        "Close": [2000.0] * n,
    })


def test_x10_success_is_a_real_ten_day_window_not_successive_powers():
    df = _days(10)
    trades = [
        {"entry_idx": 0, "exit_idx": 1, "return_frac": 1.0},
        {"entry_idx": 2, "exit_idx": 3, "return_frac": 1.0},
        {"entry_idx": 4, "exit_idx": 5, "return_frac": 1.0},
        {"entry_idx": 6, "exit_idx": 7, "return_frac": 0.25},
    ]

    m = compute_x10_window_metrics(df, trades, horizon_days=10, target_multiple=10.0)

    assert m["x10_10d_windows"] == 1
    assert m["x10_10d_successes"] == 1
    assert m["x10_10d_independent_successes"] == 1
    assert m["x10_10d_success_rate"] == 1.0
    assert m["x10_10d_fastest_target_days"] <= 10


def test_adjacent_rolling_windows_do_not_inflate_independent_success_count():
    df = _days(20)
    # One exceptional episode around days 5-8 can make several overlapping
    # rolling windows successful, but must count as only one independent event.
    trades = [
        {"entry_idx": 5, "exit_idx": 6, "return_frac": 2.0},
        {"entry_idx": 7, "exit_idx": 8, "return_frac": 2.5},
    ]

    m = compute_x10_window_metrics(df, trades, horizon_days=10, target_multiple=10.0)

    assert m["x10_10d_successes"] > 1
    assert m["x10_10d_independent_successes"] == 1


def test_window_replay_starts_each_window_from_same_capital():
    df = _days(20)
    trades = [
        {"entry_idx": 0, "exit_idx": 1, "return_frac": 0.50},
        {"entry_idx": 10, "exit_idx": 11, "return_frac": -0.50},
    ]

    m = compute_x10_window_metrics(df, trades, horizon_days=10, target_multiple=10.0)

    assert m["x10_10d_windows"] == 11
    assert m["x10_10d_best_multiple"] >= 1.0
    assert m["x10_10d_worst_multiple"] <= 0.5
    assert m["x10_10d_successes"] == 0


def test_short_dataset_has_no_eligible_x10_window():
    df = _days(9)
    m = compute_x10_window_metrics(df, [], horizon_days=10, target_multiple=10.0)

    assert m["x10_10d_windows"] == 0
    assert m["x10_10d_independent_successes"] == 0
