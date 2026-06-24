"""
XAUUSD-SCALPER-X10  |  Improved Backtest Engine
================================================
An improved version of backtests/engine.py with additional features:
- trailing_stop   : After 1R profit, move SL to breakeven then trail by initial_risk
- max_bars_in_trade: Force close at bar's Close after N bars (time exit)
- session_filter  : Skip entries outside active session hours

Transaction Costs (realistic Exness XAUUSD M1)
-----------------------------------------------
- Entry at Open of bar N+1 (next-bar entry — no look-ahead bias)
- Spread: per-bar from data 'spread' column (÷1000 for price), else DEFAULT_SPREAD
- Slippage: SLIPPAGE_PER_FILL per fill (entry + exit), always against the trade
- Pessimistic: when SL and TP both hit on same bar, SL is assumed first
"""

import math
import pandas as pd
import numpy as np
import ta
from typing import Dict, List, Tuple

from core.config import (
    INITIAL_BALANCE,
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
)

# Re-export INITIAL_BALANCE so tests can import it directly from this module
__all__ = [
    "INITIAL_BALANCE",
    "run_simulation",
    "validate",
    "dynamic_lot",
    "profit",
    "add_regime_indicators",
]


# ══════════════════════════════════════════════
# Regime Detection
# ══════════════════════════════════════════════

def add_regime_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Add ADX and ATR columns used for regime classification."""
    adx_period  = 14
    atr_period  = 14
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


# ══════════════════════════════════════════════
# Dynamic Lot Sizing
# ══════════════════════════════════════════════

def dynamic_lot(balance: float, sl_distance: float, risk_pct: float) -> float:
    """
    Compute position size using the % risk model.

    Formula: lot = (balance * risk_pct) / (sl_distance * PIP_VALUE)

    Auto-scales with balance (compounding on wins, protection on losses).
    """
    if sl_distance <= 0 or balance <= 0:
        return MIN_LOT
    lot = (balance * risk_pct) / (sl_distance * PIP_VALUE)
    return max(MIN_LOT, min(round(lot, 3), MAX_LOT))


# ══════════════════════════════════════════════
# P&L Calculation
# ══════════════════════════════════════════════

def profit(entry: float, exit_: float, direction: int, lot_size: float) -> float:
    """XAUUSD P&L in USD for a single trade."""
    if direction == 1:   # long
        return (exit_ - entry) * lot_size * PIP_VALUE
    else:                # short
        return (entry - exit_) * lot_size * PIP_VALUE


# ══════════════════════════════════════════════
# Core Backtest Simulator
# ══════════════════════════════════════════════

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
    """
    Bar-by-bar M1 simulation with dynamic lot sizing, realistic costs,
    next-bar entry, and pessimistic SL-first fill assumption.

    Parameters
    ----------
    df                 : OHLCV DataFrame (indexed 0..N), may contain 'spread' column
                         (MT5 points — divided by 1000 to get price units).
    signals            : Series of 1 (long), -1 (short), 0 (no signal).
    sl_prices          : Series of SL prices (used at signal bar index).
    tp_prices          : Series of TP prices.
    directions         : Series of +1 / -1 corresponding to trade direction.
    risk_pct           : Fraction of balance to risk per trade (default 5%).
    spread_override    : Fixed spread in price units (overrides per-bar data).
    slippage_override  : Fixed slippage per fill (overrides config default).
    trailing_stop      : If True, trail SL once unrealized profit >= initial_risk (1R).
                         SL is first moved to breakeven, then trails by initial_risk.
    max_bars_in_trade  : Force-close the trade at bar's Close after this many bars.
                         0 = disabled (no time exit).
    session_filter     : If True, pending entries are discarded when the entry bar's
                         hour falls outside session_hours.
    session_hours      : (start_hour, end_hour) inclusive range for trading session.
                         E.g. (7, 21) allows entry on bars with hour in [7, 20].

    Returns
    -------
    dict with keys: total_trades, win_rate, profit_factor, max_drawdown,
                    x10_count, final_balance, return_pct, blown_account, equity_curve
    """
    slippage = slippage_override if slippage_override is not None else SLIPPAGE_PER_FILL
    has_spread_col = "spread" in df.columns

    session_start, session_end = session_hours  # e.g. 7, 21 → hours 7-20 inclusive

    balance       = INITIAL_BALANCE
    equity_peak   = INITIAL_BALANCE
    max_dd        = 0.0
    trades        = []
    equity_curve  = [INITIAL_BALANCE]
    x10_count     = 0
    next_x10_target = INITIAL_BALANCE * 10   # first milestone: $500

    in_trade      = False
    entry_px      = 0.0
    sl            = 0.0
    tp            = 0.0
    direction     = 0
    current_lot   = MIN_LOT
    initial_risk  = 0.0   # |entry - initial_sl| in price units (1R distance)
    bars_in_trade = 0
    trailing_activated = False

    blown_account = False

    # Pending signal for next-bar entry
    pending_entry = False
    pending_sl    = 0.0
    pending_tp    = 0.0
    pending_dir   = 0

    n_bars = len(df)

    for i in range(n_bars):
        row = df.iloc[i]

        # ── Session filter on pending entry ──────────
        if pending_entry and not in_trade and session_filter:
            bar_hour = pd.Timestamp(row["time"]).hour
            # Discard pending entry if outside active session
            if not (session_start <= bar_hour < session_end):
                pending_entry = False

        # ── Execute pending entry at this bar's Open ──
        if pending_entry and not in_trade:
            if spread_override is not None:
                bar_spread = spread_override
            elif has_spread_col:
                bar_spread = row["spread"] / 1000.0   # MT5 points → price units
            else:
                bar_spread = DEFAULT_SPREAD

            raw_entry = row["Open"]
            if pending_dir == 1:   # long: buy at ask = open + half_spread + slippage
                entry_px = raw_entry + bar_spread / 2.0 + slippage
            else:                  # short: sell at bid = open - half_spread - slippage
                entry_px = raw_entry - bar_spread / 2.0 - slippage

            sl        = pending_sl
            tp        = pending_tp
            direction = pending_dir
            sl_distance = abs(entry_px - sl)

            if sl_distance > 0:
                current_lot  = dynamic_lot(balance, sl_distance, risk_pct)
                initial_risk = sl_distance          # 1R in price units
                in_trade     = True
                bars_in_trade = 0
                trailing_activated = False

            pending_entry = False

        # ── Manage open trade ──────────────────────────
        if in_trade:
            bars_in_trade += 1

            # ── Trailing stop logic ──────────────────
            if trailing_stop:
                if direction == 1:   # long
                    unrealized = row["High"] - entry_px
                    if unrealized >= initial_risk:
                        # Move SL to at least breakeven, then trail by initial_risk behind High
                        new_sl = row["High"] - initial_risk
                        if new_sl > sl:
                            sl = new_sl
                else:                # short
                    unrealized = entry_px - row["Low"]
                    if unrealized >= initial_risk:
                        new_sl = row["Low"] + initial_risk
                        if new_sl < sl:
                            sl = new_sl

            # ── Time exit (checked before SL/TP) ────
            if max_bars_in_trade > 0 and bars_in_trade >= max_bars_in_trade:
                # Force close at Close of this bar
                raw_exit = row["Close"]
                if direction == 1:
                    exit_px = raw_exit - slippage
                else:
                    exit_px = raw_exit + slippage
                pnl = profit(entry_px, exit_px, direction, current_lot)
                balance += pnl
                trades.append(pnl)
                in_trade = False
            else:
                # ── SL / TP check ────────────────────
                hit_sl = False
                hit_tp = False

                if direction == 1:   # long
                    hit_sl = row["Low"] <= sl
                    hit_tp = row["High"] >= tp
                else:                # short
                    hit_sl = row["High"] >= sl
                    hit_tp = row["Low"] <= tp

                # Pessimistic: SL before TP on same bar
                if hit_sl:
                    if direction == 1:
                        exit_px = sl - slippage
                    else:
                        exit_px = sl + slippage
                    pnl = profit(entry_px, exit_px, direction, current_lot)
                    balance += pnl
                    trades.append(pnl)
                    in_trade = False
                elif hit_tp:
                    if direction == 1:
                        exit_px = tp - slippage
                    else:
                        exit_px = tp + slippage
                    pnl = profit(entry_px, exit_px, direction, current_lot)
                    balance += pnl
                    trades.append(pnl)
                    in_trade = False

            # ── x10 milestone check ──────────────────
            while not in_trade and balance >= next_x10_target:
                x10_count += 1
                next_x10_target *= 10

        # ── Circuit breaker: account blown ───────────
        if balance <= 0:
            balance = 0.0
            blown_account = True
            break

        # ── Register signal for next-bar entry ───────
        sig = signals.iloc[i]
        if not in_trade and not pending_entry and sig != 0:
            sl_val = sl_prices.iloc[i]
            tp_val = tp_prices.iloc[i]
            if not (math.isnan(float(sl_val)) or math.isnan(float(tp_val))):
                pending_entry = True
                pending_sl    = float(sl_val)
                pending_tp    = float(tp_val)
                pending_dir   = int(sig)

        # ── Track drawdown ───────────────────────────
        equity_curve.append(balance)
        if balance > equity_peak:
            equity_peak = balance
        dd = (equity_peak - balance) / equity_peak if equity_peak > 0 else 0.0
        if dd > max_dd:
            max_dd = dd

    # ── Compute aggregate metrics ─────────────────
    n      = len(trades)
    wins   = [t for t in trades if t > 0]
    losses = [t for t in trades if t <= 0]

    win_rate     = len(wins) / n if n else 0.0
    gross_profit = sum(wins)
    gross_loss   = abs(sum(losses))
    pf = gross_profit / gross_loss if gross_loss > 0 else (
        float("inf") if gross_profit > 0 else 0.0
    )

    return {
        "total_trades"  : n,
        "win_rate"      : round(win_rate, 4),
        "profit_factor" : round(pf, 4),
        "max_drawdown"  : round(max_dd, 4),
        "x10_count"     : x10_count,
        "final_balance" : round(balance, 2),
        "return_pct"    : round((balance - INITIAL_BALANCE) / INITIAL_BALANCE * 100, 2),
        "blown_account" : blown_account,
        "equity_curve"  : equity_curve,
    }


# ══════════════════════════════════════════════
# Validation
# ══════════════════════════════════════════════

def validate(metrics: dict, regimes_tested: int) -> Tuple[bool, List[str]]:
    """
    Check whether backtest metrics meet all validation criteria.

    Returns (passed, list_of_failing_criteria).
    """
    fails = []
    if metrics["win_rate"] <= MIN_WIN_RATE:
        fails.append(f"WR {metrics['win_rate']:.1%} <= {MIN_WIN_RATE:.0%}")
    if metrics["profit_factor"] < MIN_PROFIT_FACTOR:
        fails.append(f"PF {metrics['profit_factor']:.2f} < {MIN_PROFIT_FACTOR}")
    if metrics["max_drawdown"] >= MAX_DRAWDOWN:
        fails.append(f"DD {metrics['max_drawdown']:.1%} >= {MAX_DRAWDOWN:.0%}")
    if metrics["x10_count"] < MIN_X10_COUNT:
        fails.append(f"x10_count {metrics['x10_count']} < {MIN_X10_COUNT}")
    if metrics["total_trades"] < MIN_TRADES:
        fails.append(f"trades {metrics['total_trades']} < {MIN_TRADES}")
    if regimes_tested < MIN_REGIMES:
        fails.append(f"regimes {regimes_tested} < {MIN_REGIMES}")
    return (len(fails) == 0, fails)
