"""
XAUUSD-SCALPER-X10 | Backtest Engine V2
=======================================
Realistic next-bar XAUUSD simulation plus explicit $500 -> $5,000 research
metrics over rolling 10-trading-day windows.

Execution assumptions
---------------------
- Entry at Open of bar N+1 (no same-bar look-ahead)
- Spread and adverse slippage charged
- SL wins ties when SL and TP are both touched in one bar
- Gap-aware stop fills
- Trailing changes become effective only after the bar that raised the stop
- Floating-equity drawdown
- Any position still open at the dataset end is force-closed with costs

X10 semantics
-------------
``x10_count`` is retained for database compatibility, but no longer counts
successive powers of ten in one equity path. It now means the number of
NON-OVERLAPPING historical 10-trading-day windows that reached the configured
X10 target. Rolling-window success rate and distribution metrics are returned
separately. This is a research measurement, not a promise of future returns.
"""

import math
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
import ta

from core.config import (
    INITIAL_BALANCE,
    X10_TARGET_MULTIPLE,
    X10_HORIZON_DAYS,
    MC_RUIN_BALANCE_FRACTION,
    PIP_VALUE,
    DEFAULT_RISK_PCT,
    MIN_LOT,
    MAX_LOT,
    DEFAULT_SPREAD,
    SLIPPAGE_PER_FILL,
    MIN_WIN_RATE,
    MIN_PROFIT_FACTOR,
    MAX_DRAWDOWN,
    MIN_X10_COUNT,
    MIN_TRADES,
    MIN_REGIMES,
    M5_MIN_WIN_RATE,
    M5_MIN_PROFIT_FACTOR,
    M5_MAX_DRAWDOWN,
    M5_MIN_X10_COUNT,
    M5_MIN_TRADES,
    M5_MIN_REGIMES,
)

__all__ = [
    "INITIAL_BALANCE",
    "run_simulation",
    "validate",
    "dynamic_lot",
    "profit",
    "add_regime_indicators",
    "compute_x10_window_metrics",
]


def add_regime_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Add causal ADX/ATR regime labels."""
    adx_period = 14
    atr_period = 14
    atr_avg_win = 100

    df = df.copy()
    df["ADX"] = ta.trend.ADXIndicator(
        df["High"], df["Low"], df["Close"], window=adx_period
    ).adx()
    df["ATR"] = ta.volatility.average_true_range(
        df["High"], df["Low"], df["Close"], window=atr_period
    )
    df["ATR_avg"] = df["ATR"].rolling(atr_avg_win).mean()

    def classify_regime(row):
        if pd.isna(row["ADX"]) or pd.isna(row["ATR_avg"]):
            return "UNKNOWN"
        if row["ATR"] > 1.5 * row["ATR_avg"]:
            return "HIGH_VOLATILITY"
        if row["ADX"] > 25:
            return "TREND"
        if row["ADX"] < 20:
            return "RANGE"
        return "MIXED"

    df["regime"] = df.apply(classify_regime, axis=1)
    return df


def dynamic_lot(balance: float, sl_distance: float, risk_pct: float) -> float:
    """Position size from account balance, stop distance and risk fraction."""
    if sl_distance <= 0 or balance <= 0:
        return MIN_LOT
    lot = (balance * risk_pct) / (sl_distance * PIP_VALUE)
    return max(MIN_LOT, min(round(lot, 3), MAX_LOT))


def profit(entry: float, exit_: float, direction: int, lot_size: float) -> float:
    """XAUUSD P&L in USD for one trade."""
    if direction == 1:
        return (exit_ - entry) * lot_size * PIP_VALUE
    return (entry - exit_) * lot_size * PIP_VALUE


def _empty_x10_metrics(horizon_days: int, target_multiple: float) -> dict:
    return {
        "x10_10d_model": "closed_trade_fractional_replay_v1",
        "x10_10d_horizon_days": int(horizon_days),
        "x10_10d_target_multiple": float(target_multiple),
        "x10_10d_windows": 0,
        "x10_10d_successes": 0,
        "x10_10d_success_rate": 0.0,
        "x10_10d_independent_successes": 0,
        "x10_10d_independent_success_rate": 0.0,
        "x10_10d_median_multiple": 1.0,
        "x10_10d_p10_multiple": 1.0,
        "x10_10d_p90_multiple": 1.0,
        "x10_10d_best_multiple": 1.0,
        "x10_10d_worst_multiple": 1.0,
        "x10_10d_median_closed_dd": 0.0,
        "x10_10d_worst_closed_dd": 0.0,
        "x10_10d_ruin_rate": 0.0,
        "x10_10d_fastest_target_days": None,
        "x10_10d_median_target_days": None,
    }


def compute_x10_window_metrics(
    df: pd.DataFrame,
    trade_records: List[dict],
    horizon_days: int = X10_HORIZON_DAYS,
    target_multiple: float = X10_TARGET_MULTIPLE,
    ruin_fraction: float = MC_RUIN_BALANCE_FRACTION,
) -> dict:
    """Evaluate the strategy in every rolling N-trading-day window.

    Each trade stores the return fraction realized by the main simulation.
    Replaying those fractional returns from the same starting capital makes
    each historical window independent without re-running the whole bar engine
    hundreds of times. This is exact while lot sizing is proportional to
    equity; MIN_LOT/MAX_LOT clipping can introduce small scale differences and
    is therefore explicitly identified by the model tag.

    A trade is included only when both its entry and exit fall inside a window,
    so a window always starts flat. ``independent_successes`` greedily counts
    successful windows that do not overlap; this prevents one exceptional
    episode from being counted repeatedly by adjacent rolling starts.
    """
    out = _empty_x10_metrics(horizon_days, target_multiple)
    if horizon_days <= 0 or target_multiple <= 1.0 or "time" not in df.columns:
        return out

    times = pd.to_datetime(df["time"], errors="coerce")
    if times.isna().all():
        return out
    normalized = times.dt.normalize()
    trading_days = list(pd.Index(normalized.dropna().drop_duplicates()))
    if len(trading_days) < horizon_days:
        return out

    day_pos = {day: i for i, day in enumerate(trading_days)}
    records = []
    for tr in trade_records:
        try:
            entry_i = int(tr["entry_idx"])
            exit_i = int(tr["exit_idx"])
            if entry_i < 0 or exit_i < entry_i or exit_i >= len(df):
                continue
            entry_day = normalized.iloc[entry_i]
            exit_day = normalized.iloc[exit_i]
            if pd.isna(entry_day) or pd.isna(exit_day):
                continue
            r = float(tr["return_frac"])
            if not math.isfinite(r):
                continue
            records.append({
                "entry_day": day_pos.get(entry_day),
                "exit_day": day_pos.get(exit_day),
                "return_frac": r,
            })
        except (KeyError, TypeError, ValueError, IndexError):
            continue

    records = [r for r in records if r["entry_day"] is not None and r["exit_day"] is not None]
    records.sort(key=lambda r: (r["exit_day"], r["entry_day"]))

    target_balance = INITIAL_BALANCE * target_multiple
    ruin_balance = INITIAL_BALANCE * ruin_fraction
    windows = []
    target_days = []

    for start in range(0, len(trading_days) - horizon_days + 1):
        end = start + horizon_days - 1
        balance = float(INITIAL_BALANCE)
        peak = balance
        max_dd = 0.0
        ruined = False
        reached = False
        reached_days = None

        for tr in records:
            if tr["entry_day"] < start:
                continue
            # Records are ordered primarily by exit_day, not entry_day. A
            # later record may therefore still have an entry inside this
            # window; never break on entry_day here.
            if tr["entry_day"] > end:
                continue
            if tr["exit_day"] > end:
                continue

            ret = max(-1.0, tr["return_frac"])
            balance = max(0.0, balance * (1.0 + ret))
            peak = max(peak, balance)
            if peak > 0:
                max_dd = max(max_dd, (peak - balance) / peak)
            if balance <= ruin_balance:
                ruined = True
            if not reached and balance >= target_balance:
                reached = True
                reached_days = int(tr["exit_day"] - start + 1)
                target_days.append(reached_days)

        windows.append({
            "start": start,
            "end": end,
            "success": reached,
            "final_multiple": balance / INITIAL_BALANCE if INITIAL_BALANCE > 0 else 0.0,
            "max_dd": max_dd,
            "ruined": ruined,
            "target_days": reached_days,
        })

    if not windows:
        return out

    successes = sum(1 for w in windows if w["success"])
    independent = 0
    last_used_end = -1
    for w in windows:
        if w["success"] and w["start"] > last_used_end:
            independent += 1
            last_used_end = w["end"]

    multiples = np.asarray([w["final_multiple"] for w in windows], dtype=float)
    dds = np.asarray([w["max_dd"] for w in windows], dtype=float)
    ruins = sum(1 for w in windows if w["ruined"])
    nonoverlap_slots = max(1, len(trading_days) // horizon_days)

    out.update({
        "x10_10d_windows": len(windows),
        "x10_10d_successes": successes,
        "x10_10d_success_rate": round(successes / len(windows), 6),
        "x10_10d_independent_successes": independent,
        "x10_10d_independent_success_rate": round(independent / nonoverlap_slots, 6),
        "x10_10d_median_multiple": round(float(np.median(multiples)), 6),
        "x10_10d_p10_multiple": round(float(np.percentile(multiples, 10)), 6),
        "x10_10d_p90_multiple": round(float(np.percentile(multiples, 90)), 6),
        "x10_10d_best_multiple": round(float(np.max(multiples)), 6),
        "x10_10d_worst_multiple": round(float(np.min(multiples)), 6),
        "x10_10d_median_closed_dd": round(float(np.median(dds)), 6),
        "x10_10d_worst_closed_dd": round(float(np.max(dds)), 6),
        "x10_10d_ruin_rate": round(ruins / len(windows), 6),
        "x10_10d_fastest_target_days": min(target_days) if target_days else None,
        "x10_10d_median_target_days": round(float(np.median(target_days)), 2) if target_days else None,
    })
    return out


def run_simulation(
    df: pd.DataFrame,
    signals: pd.Series,
    sl_prices: pd.Series,
    tp_prices: pd.Series,
    directions: pd.Series,
    risk_pct: float = DEFAULT_RISK_PCT,
    spread_override: float = None,
    slippage_override: float = None,
    trailing_stop: bool = False,
    max_bars_in_trade: int = 0,
    session_filter: bool = False,
    session_hours: tuple = (7, 21),
) -> dict:
    """Bar-by-bar simulation with dynamic lot sizing and realistic costs."""
    slippage = slippage_override if slippage_override is not None else SLIPPAGE_PER_FILL
    has_spread_col = "spread" in df.columns
    session_start, session_end = session_hours

    balance = float(INITIAL_BALANCE)
    equity_peak = float(INITIAL_BALANCE)
    max_dd = 0.0
    trades: List[float] = []
    trade_records: List[dict] = []
    equity_curve = [float(INITIAL_BALANCE)]

    in_trade = False
    entry_px = 0.0
    sl = 0.0
    tp = 0.0
    direction = 0
    current_lot = MIN_LOT
    initial_risk = 0.0
    bars_in_trade = 0
    entry_bar_idx = -1

    blown_account = False
    pending_entry = False
    pending_sl = 0.0
    pending_tp = 0.0
    pending_dir = 0

    n_bars = len(df)
    if n_bars == 0:
        metrics = {
            "total_trades": 0,
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "max_drawdown": 0.0,
            "final_balance": round(balance, 2),
            "return_pct": 0.0,
            "blown_account": False,
            "equity_curve": equity_curve,
        }
        metrics.update(_empty_x10_metrics(X10_HORIZON_DAYS, X10_TARGET_MULTIPLE))
        metrics["x10_count"] = 0
        return metrics

    arr_open = df["Open"].values
    arr_high = df["High"].values
    arr_low = df["Low"].values
    arr_close = df["Close"].values
    arr_signals = signals.values
    arr_sl = sl_prices.values
    arr_tp = tp_prices.values

    if session_filter and "time" in df.columns:
        arr_hours = pd.to_datetime(df["time"]).dt.hour.values
    else:
        arr_hours = None
    arr_spread = df["spread"].values if has_spread_col else None

    def close_trade(pnl: float, exit_idx: int):
        nonlocal balance, in_trade
        before = balance
        balance += pnl
        trades.append(float(pnl))
        trade_records.append({
            "entry_idx": entry_bar_idx,
            "exit_idx": exit_idx,
            "pnl": float(pnl),
            "return_frac": float(pnl / before) if before > 0 else -1.0,
        })
        in_trade = False

    for i in range(n_bars):
        if spread_override is not None:
            bar_spread = spread_override
        elif arr_spread is not None:
            bar_spread = max(float(arr_spread[i]) * 0.01, 0.05)
        else:
            bar_spread = DEFAULT_SPREAD

        if pending_entry and not in_trade and session_filter and arr_hours is not None:
            bar_hour = int(arr_hours[i])
            if not (session_start <= bar_hour < session_end):
                pending_entry = False

        if pending_entry and not in_trade:
            raw_entry = arr_open[i]
            entry_px = raw_entry + bar_spread + slippage if pending_dir == 1 else raw_entry - slippage
            sl = pending_sl
            tp = pending_tp
            direction = pending_dir
            sl_distance = abs(entry_px - sl)
            if sl_distance > 0:
                current_lot = dynamic_lot(balance, sl_distance, risk_pct)
                initial_risk = sl_distance
                in_trade = True
                bars_in_trade = 0
                entry_bar_idx = i
            pending_entry = False

        if in_trade:
            bars_in_trade += 1
            bar_high = arr_high[i]
            bar_low = arr_low[i]
            bar_open = arr_open[i]

            if max_bars_in_trade > 0 and bars_in_trade >= max_bars_in_trade:
                raw_exit = arr_close[i]
                exit_px = raw_exit - slippage if direction == 1 else raw_exit + bar_spread + slippage
                close_trade(profit(entry_px, exit_px, direction, current_lot), i)
            else:
                if direction == 1:
                    hit_sl = bar_low <= sl
                    hit_tp = bar_high >= tp
                else:
                    hit_sl = bar_high >= sl
                    hit_tp = bar_low <= tp

                if hit_sl:
                    exit_px = (
                        min(sl, bar_open) - slippage
                        if direction == 1
                        else max(sl, bar_open) + bar_spread + slippage
                    )
                    close_trade(profit(entry_px, exit_px, direction, current_lot), i)
                elif hit_tp:
                    exit_px = tp - slippage if direction == 1 else tp + bar_spread + slippage
                    close_trade(profit(entry_px, exit_px, direction, current_lot), i)

            if trailing_stop and in_trade:
                if direction == 1:
                    unrealized = bar_high - entry_px
                    if unrealized >= initial_risk:
                        new_sl = bar_high - initial_risk
                        if new_sl > sl:
                            sl = new_sl
                else:
                    unrealized = entry_px - bar_low
                    if unrealized >= initial_risk:
                        new_sl = bar_low + initial_risk
                        if new_sl < sl:
                            sl = new_sl

        if balance <= 0:
            balance = 0.0
            blown_account = True
            break

        sig = arr_signals[i]
        if not in_trade and not pending_entry and sig != 0:
            sl_val = arr_sl[i]
            tp_val = arr_tp[i]
            if not (math.isnan(float(sl_val)) or math.isnan(float(tp_val))):
                pending_entry = True
                pending_sl = float(sl_val)
                pending_tp = float(tp_val)
                pending_dir = int(sig)

        if in_trade:
            if direction == 1:
                mark_px = arr_close[i]
            else:
                mark_px = arr_close[i] + bar_spread
            equity = balance + profit(entry_px, mark_px, direction, current_lot)
        else:
            equity = balance
        equity_curve.append(float(equity))
        equity_peak = max(equity_peak, equity)
        dd = (equity_peak - equity) / equity_peak if equity_peak > 0 else 0.0
        max_dd = max(max_dd, dd)

    if in_trade and not blown_account:
        i = n_bars - 1
        if spread_override is not None:
            final_spread = spread_override
        elif arr_spread is not None:
            final_spread = max(float(arr_spread[i]) * 0.01, 0.05)
        else:
            final_spread = DEFAULT_SPREAD
        raw_exit = arr_close[i]
        exit_px = raw_exit - slippage if direction == 1 else raw_exit + final_spread + slippage
        close_trade(profit(entry_px, exit_px, direction, current_lot), i)
        equity_curve.append(float(max(balance, 0.0)))
        equity_peak = max(equity_peak, balance)
        if equity_peak > 0:
            max_dd = max(max_dd, (equity_peak - balance) / equity_peak)
        if balance <= 0:
            balance = 0.0
            blown_account = True

    n = len(trades)
    wins = [t for t in trades if t > 0]
    losses = [t for t in trades if t <= 0]
    win_rate = len(wins) / n if n else 0.0
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    pf = gross_profit / gross_loss if gross_loss > 0 else (
        float("inf") if gross_profit > 0 else 0.0
    )

    x10 = compute_x10_window_metrics(df, trade_records)

    metrics = {
        "total_trades": n,
        "win_rate": round(win_rate, 4),
        "profit_factor": round(pf, 4),
        "max_drawdown": round(max_dd, 4),
        "x10_count": int(x10["x10_10d_independent_successes"]),
        "final_balance": round(balance, 2),
        "return_pct": round((balance - INITIAL_BALANCE) / INITIAL_BALANCE * 100, 2),
        "blown_account": blown_account,
        "equity_curve": equity_curve,
    }
    metrics.update(x10)
    return metrics


def validate(metrics: dict, regimes_tested: int, timeframe: str = "M1") -> Tuple[bool, List[str]]:
    """Check aggregate quality plus independent X10-window evidence."""
    if timeframe == "M5":
        min_wr = M5_MIN_WIN_RATE
        min_pf = M5_MIN_PROFIT_FACTOR
        max_dd = M5_MAX_DRAWDOWN
        min_x10 = M5_MIN_X10_COUNT
        min_trades = M5_MIN_TRADES
        min_regimes = M5_MIN_REGIMES
    else:
        min_wr = MIN_WIN_RATE
        min_pf = MIN_PROFIT_FACTOR
        max_dd = MAX_DRAWDOWN
        min_x10 = MIN_X10_COUNT
        min_trades = MIN_TRADES
        min_regimes = MIN_REGIMES

    fails = []
    if metrics.get("win_rate", 0.0) < min_wr:
        fails.append(f"WR {metrics.get('win_rate', 0):.1%} < {min_wr:.0%}")
    if metrics.get("profit_factor", 0.0) < min_pf:
        fails.append(f"PF {metrics.get('profit_factor', 0):.2f} < {min_pf}")
    if metrics.get("max_drawdown", 1.0) >= max_dd:
        fails.append(f"DD {metrics.get('max_drawdown', 1):.1%} >= {max_dd:.0%}")
    if min_x10 > 0 and metrics.get("x10_count", 0) < min_x10:
        fails.append(
            f"x10_10d independent successes {metrics.get('x10_count', 0)} < {min_x10}"
        )
    if metrics.get("total_trades", 0) < min_trades:
        fails.append(f"trades {metrics.get('total_trades', 0)} < {min_trades}")
    if regimes_tested < min_regimes:
        fails.append(f"regimes {regimes_tested} < {min_regimes}")
    return (len(fails) == 0, fails)
