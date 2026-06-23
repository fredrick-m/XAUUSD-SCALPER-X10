"""
XAUUSD-SCALPER-X10 Backtest Engine
====================================
Starting balance : $50
Lot sizing       : Dynamic (% risk model)
                   lot = (balance * risk_pct) / (sl_distance * PIP_VALUE)
                   PIP_VALUE = 100  (matches P&L formula: price_diff * lot * 100)
Profit formula   : (exit - entry) * lot * 100  (for longs; negated for shorts)
Bar-by-bar M1 simulation with market regime detection.

Transaction Costs (v2)
----------------------
- Entry at Open of bar N+1 (not Close of signal bar — eliminates look-ahead bias)
- Spread: per-bar from data column if available, else DEFAULT_SPREAD ($0.35 RT)
- Slippage: $0.05 per fill (entry + exit), always against the trade
- Ambiguity: when SL and TP both hit on same bar, SL assumed first (pessimistic)

Regimes
-------
TREND          : ADX > 25
RANGE          : ADX < 20
HIGH_VOLATILITY: ATR > 1.5x rolling average ATR

Validation Criteria (ALL must pass)
-------------------------------------
Win Rate        > 62%
Profit Factor   > 2.0
Max Drawdown    < 35%
x10 occurrences >= 5
Total Trades    >= 200
Regimes tested  >= 3

Dynamic Lot Scaling (5% risk, ~20-unit SL)
-------------------------------------------
Balance  | Lot
---------|--------
$50      | ~0.01
$100     | ~0.02
$500     | ~0.10
$1,000   | ~0.20
"""

import importlib.util
import sys
import os
import math
import pandas as pd
import numpy as np
import ta
from pathlib import Path
from typing import Dict, List, Tuple

# ──────────────────────────────────────────────
# Paths
# ──────────────────────────────────────────────
BASE_DIR      = Path(r"C:\Users\hp\XAUUSD-SCALPER-X10")
DATA_PATH     = BASE_DIR / "data" / "raw" / "XAUUSD_M1.csv"
STRATEGY_DIR  = BASE_DIR / "strategies"
RESULTS_DIR   = BASE_DIR / "backtests" / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# ──────────────────────────────────────────────
# Engine constants
# ──────────────────────────────────────────────
INITIAL_BALANCE  = 50.0            # Starting balance: $50
PIP_VALUE        = 100.0           # USD per price-unit per 1 lot (matches P&L: diff * lot * 100)
RISK_PERCENTS    = [0.02, 0.05, 0.10, 0.20]   # Test values: 2%, 5%, 10%, 20%
DEFAULT_RISK_PCT = 0.05            # Default: 5%
MIN_LOT          = 0.001           # Minimum lot size
MAX_LOT          = 100.0           # Maximum lot size (safety cap)

# ──────────────────────────────────────────────
# Transaction costs (realistic Exness XAUUSD M1)
# ──────────────────────────────────────────────
# Spread: applied at entry (ask-bid). Data 'spread' col is in MT5 points (÷1000 for price).
# XAUUSD 3-decimal: 1 point = $0.001. spread=160 → $0.16.
# If data has per-bar spread, we use it; otherwise fall back to this default.
DEFAULT_SPREAD   = 0.35            # $0.35 round-trip fallback (≈ 20-25 cents typical + buffer)
SLIPPAGE_PER_FILL = 0.05           # $0.05 per fill (entry + exit = $0.10 round-trip)

# Validation thresholds
MIN_WIN_RATE    = 0.62
MIN_PF          = 2.0
MAX_DD          = 0.35
MIN_X10_COUNT   = 5
MIN_TRADES      = 200
MIN_REGIMES     = 3


# ══════════════════════════════════════════════
# Data Loading & Regime Detection
# ══════════════════════════════════════════════

def load_data() -> pd.DataFrame:
    df = pd.read_csv(DATA_PATH, parse_dates=["time"])
    df = df.rename(columns={
        "open": "Open", "high": "High", "low": "Low",
        "close": "Close", "tick_volume": "Volume"
    })
    df = df.sort_values("time").reset_index(drop=True)
    return df


def add_regime_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Add ADX and ATR columns used for regime classification."""
    adx_period  = 14
    atr_period  = 14
    atr_avg_win = 100   # rolling window for average ATR

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
        return "MIXED"   # 20-25 ADX — transitional, not counted as pure regime

    df["regime"] = df.apply(classify_regime, axis=1)
    return df


# ══════════════════════════════════════════════
# Dynamic Lot Sizing
# ══════════════════════════════════════════════

def dynamic_lot(balance: float, sl_distance: float, risk_pct: float) -> float:
    """
    Compute position size using the % risk model.

    Formula: lot = (balance * risk_pct) / (sl_distance * PIP_VALUE)

    Auto-scales with balance:
    - Balance grows  → lots grow  (compounding)
    - Balance shrinks → lots shrink (drawdown protection)
    """
    if sl_distance <= 0 or balance <= 0:
        return MIN_LOT
    lot = (balance * risk_pct) / (sl_distance * PIP_VALUE)
    return max(MIN_LOT, min(round(lot, 3), MAX_LOT))


# ══════════════════════════════════════════════
# Core Backtest Simulator
# ══════════════════════════════════════════════

def profit(entry: float, exit_: float, direction: int, lot_size: float) -> float:
    """XAUUSD P&L in USD for a single trade."""
    if direction == 1:   # long
        return (exit_ - entry) * lot_size * 100
    else:                # short
        return (entry - exit_) * lot_size * 100


def run_simulation(df: pd.DataFrame, signals: pd.Series,
                   sl_prices: pd.Series, tp_prices: pd.Series,
                   directions: pd.Series,
                   risk_pct: float = DEFAULT_RISK_PCT,
                   spread_override: float = None,
                   slippage_override: float = None) -> dict:
    """
    Bar-by-bar simulation with dynamic lot sizing, realistic costs,
    next-bar entry, and pessimistic SL-first fill assumption.

    Parameters
    ----------
    df         : OHLCV dataframe (indexed 0..N), may contain 'spread' column
                 (in points, ÷100 for price units)
    signals    : Series of 1 (long), -1 (short), 0 (no signal)
    sl_prices  : Series of SL prices (one per bar, only used at signal bar)
    tp_prices  : Series of TP prices
    directions : Series of +1 / -1 corresponding to trade direction
    risk_pct   : Fraction of balance to risk per trade (e.g. 0.05 = 5%)
    spread_override  : If set, use this fixed spread instead of per-bar data
    slippage_override: If set, use this slippage per fill

    Key differences from v1:
    - Entry at Open of bar N+1 (not Close of signal bar N) — eliminates look-ahead
    - Spread cost applied at entry (widens entry price against the trade)
    - Slippage applied at both entry and exit (always against the trade)
    - Pessimistic SL-first: when both SL and TP are hit on the same bar,
      SL is assumed hit first regardless of direction

    Returns
    -------
    dict with detailed performance metrics
    """
    slippage = slippage_override if slippage_override is not None else SLIPPAGE_PER_FILL
    has_spread_col = "spread" in df.columns

    balance      = INITIAL_BALANCE
    equity_peak  = INITIAL_BALANCE
    max_dd       = 0.0
    trades       = []           # list of pnl values
    equity_curve = [INITIAL_BALANCE]
    x10_count    = 0            # times balance reached a new x10 multiple
    next_x10_target = INITIAL_BALANCE * 10   # first milestone: $500

    in_trade  = False
    entry_px  = 0.0
    sl        = 0.0
    tp        = 0.0
    direction = 0
    current_lot = MIN_LOT

    blown_account = False

    # Pending signal from previous bar (for next-bar entry)
    pending_entry = False
    pending_sl    = 0.0
    pending_tp    = 0.0
    pending_dir   = 0

    n_bars = len(df)

    for i in range(n_bars):
        row = df.iloc[i]

        # ── Execute pending entry at this bar's Open ──
        if pending_entry and not in_trade:
            # Get spread for this bar
            if spread_override is not None:
                bar_spread = spread_override
            elif has_spread_col:
                bar_spread = row["spread"] / 1000.0  # MT5 points → price units (1 point = $0.001 for XAUUSD)
            else:
                bar_spread = DEFAULT_SPREAD

            raw_entry = row["Open"]
            # Apply spread + slippage against the trade direction
            if pending_dir == 1:   # long: buy at ask = open + half_spread + slippage
                entry_px = raw_entry + bar_spread / 2.0 + slippage
            else:                  # short: sell at bid = open - half_spread - slippage
                entry_px = raw_entry - bar_spread / 2.0 - slippage

            sl        = pending_sl
            tp        = pending_tp
            direction = pending_dir
            sl_distance = abs(entry_px - sl)
            if sl_distance > 0:
                current_lot = dynamic_lot(balance, sl_distance, risk_pct)
                in_trade = True
            pending_entry = False

        # ── Manage open trade ──────────────────
        if in_trade:
            hit_sl = False
            hit_tp = False

            if direction == 1:   # long
                hit_sl = row["Low"] <= sl
                hit_tp = row["High"] >= tp
            else:                # short
                hit_sl = row["High"] >= sl
                hit_tp = row["Low"] <= tp

            # Pessimistic convention: if both hit, assume SL first
            if hit_sl:
                # Apply slippage on exit (against the trade)
                if direction == 1:
                    exit_px = sl - slippage       # long SL slips down
                else:
                    exit_px = sl + slippage        # short SL slips up
                pnl = profit(entry_px, exit_px, direction, current_lot)
                balance += pnl
                trades.append(pnl)
                in_trade = False
            elif hit_tp:
                # TP exit: slippage still against (but TP is favorable)
                if direction == 1:
                    exit_px = tp - slippage        # long TP slips down slightly
                else:
                    exit_px = tp + slippage         # short TP slips up slightly
                pnl = profit(entry_px, exit_px, direction, current_lot)
                balance += pnl
                trades.append(pnl)
                in_trade = False

            # Check x10 milestone after trade closes
            while not in_trade and balance >= next_x10_target:
                x10_count += 1
                next_x10_target *= 10

        # ── Circuit breaker: account blown ─────
        if balance <= 0:
            balance = 0.0
            blown_account = True
            break

        # ── Register signal for next-bar entry ─────
        sig = signals.iloc[i]
        if not in_trade and not pending_entry and sig != 0:
            sl_val = sl_prices.iloc[i]
            tp_val = tp_prices.iloc[i]
            if not (math.isnan(sl_val) or math.isnan(tp_val)):
                pending_entry = True
                pending_sl    = sl_val
                pending_tp    = tp_val
                pending_dir   = int(sig)

        # ── Track drawdown ──────────────────────
        equity_curve.append(balance)
        if balance > equity_peak:
            equity_peak = balance
        dd = (equity_peak - balance) / equity_peak if equity_peak > 0 else 0.0
        if dd > max_dd:
            max_dd = dd

    # ── Compute metrics ────────────────────────
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


def validate(metrics: dict, regimes_tested: int) -> Tuple[bool, List[str]]:
    """Return (passed, list_of_failing_criteria)."""
    fails = []
    if metrics["win_rate"] <= MIN_WIN_RATE:
        fails.append(f"WR {metrics['win_rate']:.1%} <= {MIN_WIN_RATE:.0%}")
    if metrics["profit_factor"] < MIN_PF:
        fails.append(f"PF {metrics['profit_factor']:.2f} < {MIN_PF}")
    if metrics["max_drawdown"] >= MAX_DD:
        fails.append(f"DD {metrics['max_drawdown']:.1%} >= {MAX_DD:.0%}")
    if metrics["x10_count"] < MIN_X10_COUNT:
        fails.append(f"x10_count {metrics['x10_count']} < {MIN_X10_COUNT}")
    if metrics["total_trades"] < MIN_TRADES:
        fails.append(f"trades {metrics['total_trades']} < {MIN_TRADES}")
    if regimes_tested < MIN_REGIMES:
        fails.append(f"regimes {regimes_tested} < {MIN_REGIMES}")
    return (len(fails) == 0, fails)


# ══════════════════════════════════════════════
# Strategy Loader
# ══════════════════════════════════════════════

def load_strategy(strategy_file: Path):
    """Dynamically load a strategy module."""
    spec   = importlib.util.spec_from_file_location(strategy_file.stem, strategy_file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def get_strategy_signals(module, df: pd.DataFrame) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """
    Call module.generate_signals() and extract signal + SL/TP prices.
    Returns (signals, sl_prices, tp_prices).
    """
    p      = module.PARAMS
    sig_df = module.generate_signals(df.copy(), p)

    signals = sig_df["signal"].fillna(0).astype(int)

    # Derive SL/TP from ATR if columns not already present
    if "ATR" not in sig_df.columns:
        sig_df["ATR"] = ta.volatility.average_true_range(
            sig_df["High"], sig_df["Low"], sig_df["Close"], window=14
        )

    sl_atr = p.get("sl_atr", 1.5)
    tp_atr = p.get("tp_atr", 2.5)

    sl_prices = pd.Series(index=sig_df.index, dtype=float)
    tp_prices = pd.Series(index=sig_df.index, dtype=float)

    long_mask  = signals == 1
    short_mask = signals == -1

    sl_prices[long_mask]  = sig_df.loc[long_mask, "Close"] - sl_atr * sig_df.loc[long_mask, "ATR"]
    tp_prices[long_mask]  = sig_df.loc[long_mask, "Close"] + tp_atr * sig_df.loc[long_mask, "ATR"]
    sl_prices[short_mask] = sig_df.loc[short_mask, "Close"] + sl_atr * sig_df.loc[short_mask, "ATR"]
    tp_prices[short_mask] = sig_df.loc[short_mask, "Close"] - tp_atr * sig_df.loc[short_mask, "ATR"]

    sl_prices = sl_prices.fillna(float("nan"))
    tp_prices = tp_prices.fillna(float("nan"))

    return signals, sl_prices, tp_prices


# ══════════════════════════════════════════════
# Main Batch Runner
# ══════════════════════════════════════════════

def run_batch():
    print("=" * 60)
    print("XAUUSD-SCALPER-X10  |  Batch Backtest Engine")
    print(f"Balance : ${INITIAL_BALANCE:,.0f}  |  Dynamic lot sizing")
    print(f"Risk %  : {[f'{r*100:.0f}%' for r in RISK_PERCENTS]}")
    print("=" * 60)

    # Load and prepare data
    print("\nLoading M1 data...")
    df = load_data()
    df = add_regime_indicators(df)
    print(f"  Bars loaded : {len(df):,}")
    print(f"  Date range  : {df['time'].min()} to {df['time'].max()}")

    # Regime breakdown
    regime_counts = df["regime"].value_counts()
    print(f"\nRegime distribution:")
    for r, c in regime_counts.items():
        print(f"  {r:<20}: {c:,} bars ({c/len(df):.1%})")

    known_regimes = [r for r in ["TREND", "RANGE", "HIGH_VOLATILITY"] if r in df["regime"].values]
    print(f"\n  Valid regimes for testing: {known_regimes}")

    # Regime index masks
    regime_masks = {r: df["regime"] == r for r in known_regimes}

    # Discover strategy files
    strategy_files = sorted(STRATEGY_DIR.glob("strategy_s*.py"))
    print(f"\nStrategies found: {len(strategy_files)}")

    rows      = []
    validated = []

    for sf in strategy_files:
        sid = sf.stem.upper().replace("STRATEGY_", "")
        print(f"\n  [{sid}] {sf.name}")

        try:
            module = load_strategy(sf)
        except Exception as e:
            print(f"    LOAD ERROR: {e}")
            rows.append({"strategy": sid, "risk_pct": None, "error": str(e)})
            continue

        try:
            signals, sl_prices, tp_prices = get_strategy_signals(module, df)
        except Exception as e:
            print(f"    SIGNAL ERROR: {e}")
            rows.append({"strategy": sid, "risk_pct": None, "error": f"signal: {e}"})
            continue

        # ── Test each risk_pct value ────────────
        for risk_pct in RISK_PERCENTS:
            label = f"{risk_pct*100:.0f}%"
            print(f"    risk={label:<4}", end="  ")

            # Full dataset backtest
            try:
                full_metrics = run_simulation(df, signals, sl_prices, tp_prices,
                                              signals, risk_pct=risk_pct)
            except Exception as e:
                print(f"SIM ERROR: {e}")
                rows.append({"strategy": sid, "risk_pct": label, "error": f"sim: {e}"})
                continue

            # Per-regime backtest
            regime_results      = {}
            regimes_with_trades = 0
            for regime_name, mask in regime_masks.items():
                r_df  = df[mask].reset_index(drop=True)
                r_sig = signals[mask].reset_index(drop=True)
                r_sl  = sl_prices[mask].reset_index(drop=True)
                r_tp  = tp_prices[mask].reset_index(drop=True)
                if len(r_df) < 50:
                    continue
                try:
                    rm = run_simulation(r_df, r_sig, r_sl, r_tp, r_sig,
                                        risk_pct=risk_pct)
                    regime_results[regime_name] = rm
                    if rm["total_trades"] > 0:
                        regimes_with_trades += 1
                except Exception:
                    pass

            regimes_tested = regimes_with_trades

            passed, fails = validate(full_metrics, regimes_tested)
            status = "PASS" if passed else "FAIL"
            print(status, end="")
            if fails:
                print(f"  [{'; '.join(fails)}]", end="")
            print()

            row = {
                "strategy"      : sid,
                "risk_pct"      : label,
                "total_trades"  : full_metrics["total_trades"],
                "win_rate"      : full_metrics["win_rate"],
                "profit_factor" : full_metrics["profit_factor"],
                "max_drawdown"  : full_metrics["max_drawdown"],
                "x10_count"     : full_metrics["x10_count"],
                "final_balance" : full_metrics["final_balance"],
                "return_pct"    : full_metrics["return_pct"],
                "regimes_tested": regimes_tested,
                "passed"        : passed,
                "fail_reasons"  : "; ".join(fails),
            }
            # Add per-regime metrics
            for r in ["TREND", "RANGE", "HIGH_VOLATILITY"]:
                rm = regime_results.get(r, {})
                row[f"{r}_trades"] = rm.get("total_trades", 0)
                row[f"{r}_wr"]     = rm.get("win_rate", None)
                row[f"{r}_pf"]     = rm.get("profit_factor", None)
                row[f"{r}_dd"]     = rm.get("max_drawdown", None)

            rows.append(row)
            if passed:
                validated.append(row)

    # ── Save results ────────────────────────────
    results_df   = pd.DataFrame(rows)
    results_path = RESULTS_DIR / "batch2_results.csv"
    results_df.to_csv(results_path, index=False)
    print(f"\n\nResults saved -> {results_path}")

    passed_count = len(validated)
    print(f"\n{'='*60}")
    print(f"SUMMARY: {passed_count} strategy/risk_pct combos PASSED validation")
    print(f"{'='*60}")

    if passed_count > 0:
        val_df   = pd.DataFrame(validated)
        val_path = RESULTS_DIR / "validated.csv"
        val_df.to_csv(val_path, index=False)
        print(f"\nValidated strategies saved -> {val_path}")
        print("\nPassing combinations:")
        for v in validated:
            print(f"  {v['strategy']} risk={v['risk_pct']}"
                  f"  WR={v['win_rate']:.1%}  PF={v['profit_factor']:.2f}"
                  f"  DD={v['max_drawdown']:.1%}  x10={v['x10_count']}"
                  f"  trades={v['total_trades']}")
        return {"passed": validated, "all": rows}

    # ── No strategies passed: write report ──────
    print("\n0 strategies passed. Generating failure report...")

    def criteria_score(r):
        if "error" in r and not isinstance(r.get("win_rate"), float):
            return -1
        score = 0
        if r.get("win_rate", 0) > MIN_WIN_RATE:       score += 1
        if r.get("profit_factor", 0) >= MIN_PF:        score += 1
        if r.get("max_drawdown", 1) < MAX_DD:          score += 1
        if r.get("x10_count", 0) >= MIN_X10_COUNT:     score += 1
        if r.get("total_trades", 0) >= MIN_TRADES:     score += 1
        if r.get("regimes_tested", 0) >= MIN_REGIMES:  score += 1
        return score

    valid_rows = [r for r in rows if "error" not in r]
    best = max(valid_rows, key=criteria_score) if valid_rows else (rows[0] if rows else {})

    fail_counts = {
        "win_rate"      : 0,
        "profit_factor" : 0,
        "max_drawdown"  : 0,
        "x10_count"     : 0,
        "total_trades"  : 0,
        "regimes_tested": 0,
    }
    for r in valid_rows:
        if r.get("win_rate", 0) <= MIN_WIN_RATE:          fail_counts["win_rate"] += 1
        if r.get("profit_factor", 0) < MIN_PF:            fail_counts["profit_factor"] += 1
        if r.get("max_drawdown", 1) >= MAX_DD:            fail_counts["max_drawdown"] += 1
        if r.get("x10_count", 0) < MIN_X10_COUNT:         fail_counts["x10_count"] += 1
        if r.get("total_trades", 0) < MIN_TRADES:         fail_counts["total_trades"] += 1
        if r.get("regimes_tested", 0) < MIN_REGIMES:      fail_counts["regimes_tested"] += 1

    most_blocking = max(fail_counts, key=fail_counts.get)

    report_lines = [
        "XAUUSD-SCALPER-X10  |  Batch Backtest Report",
        "=" * 60,
        f"Date           : 2026-03-28",
        f"Data range     : {df['time'].min()} to {df['time'].max()}",
        f"Total bars     : {len(df):,}",
        f"Strategies     : {len(strategy_files)} tested, 0 passed",
        f"Risk% tested   : {[f'{r*100:.0f}%' for r in RISK_PERCENTS]}",
        f"Start balance  : ${INITIAL_BALANCE:,.0f}",
        f"Lot sizing     : Dynamic (balance * risk% / sl_distance / {PIP_VALUE})",
        "",
        "Validation Criteria",
        "-------------------",
        f"  Win Rate        > {MIN_WIN_RATE:.0%}",
        f"  Profit Factor   >= {MIN_PF}",
        f"  Max Drawdown    < {MAX_DD:.0%}",
        f"  x10 count       >= {MIN_X10_COUNT}",
        f"  Total Trades    >= {MIN_TRADES}",
        f"  Regimes tested  >= {MIN_REGIMES}",
        "",
        "Failure Frequency per Criterion",
        "--------------------------------",
    ]
    for k, v in sorted(fail_counts.items(), key=lambda x: -x[1]):
        pct = v / len(valid_rows) * 100 if valid_rows else 0
        report_lines.append(f"  {k:<20}: {v}/{len(valid_rows)} combos failed ({pct:.0f}%)")

    report_lines += [
        "",
        f"Most Blocking Criterion: {most_blocking.upper()} "
        f"(failed in {fail_counts[most_blocking]}/{len(valid_rows)} combos)",
        "",
        "Best Strategy/Risk combo (closest to passing)",
        "----------------------------------------------",
    ]
    for k, v in best.items():
        if k != "equity_curve":
            report_lines.append(f"  {k:<20}: {v}")

    report_lines += [
        "",
        "Recommendations",
        "---------------",
        "1. Most-blocking criterion: " + most_blocking,
        "2. Dynamic lot sizing is active — starting balance $50, compounding enabled.",
        "3. Suggested tuning directions:",
        "   - If WR is low    : tighten TP/SL ratios or add trend confirmation filters",
        "   - If PF is low    : reduce SL_ATR or increase TP_ATR multiplier",
        "   - If DD is high   : lower risk_pct (try 2%) or add intra-day drawdown guard",
        "   - If x10 low      : use higher risk_pct (10-20%) for aggressive compounding",
        "   - If trades < 200 : relax signal conditions or use wider ATR windows",
        "4. Consider genetic optimization of the best strategy's PARAMS dict.",
        "5. Consider ensemble / multi-strategy portfolio to combine partial passes.",
        "",
        "END OF REPORT",
    ]

    report_text = "\n".join(report_lines)
    report_path = RESULTS_DIR / "batch2_report.txt"
    report_path.write_text(report_text)
    print(f"Report saved -> {report_path}")

    return {"passed": [], "all": rows, "best": best, "fail_counts": fail_counts,
            "most_blocking": most_blocking, "report": report_text}


# ══════════════════════════════════════════════
# Entry point
# ══════════════════════════════════════════════
if __name__ == "__main__":
    result = run_batch()
