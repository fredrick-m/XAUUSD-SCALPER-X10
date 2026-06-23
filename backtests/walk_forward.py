"""
Walk-Forward Validation Engine
==============================
Anchored walk-forward: expanding in-sample window, fixed-size out-of-sample window.
Reports IS->OOS degradation ratios to detect overfitting.

Usage:
    python -m backtests.walk_forward                  # all strategies
    python -m backtests.walk_forward S001             # single strategy
    python -m backtests.walk_forward S001 S005 S012   # specific strategies
"""

import sys
import math
import pandas as pd
import numpy as np
from pathlib import Path
from typing import List, Dict, Optional, Tuple

from backtests.engine import (
    load_data, add_regime_indicators, load_strategy, get_strategy_signals,
    run_simulation, INITIAL_BALANCE, DEFAULT_RISK_PCT, STRATEGY_DIR, RESULTS_DIR
)

# ──────────────────────────────────────────────
# Walk-forward parameters
# ──────────────────────────────────────────────
MIN_IS_BARS    = 20_000     # Minimum in-sample bars (~14 trading days at M1)
OOS_BARS       = 10_000     # Out-of-sample window (~7 trading days)
STEP_BARS      = 10_000     # Step forward between windows (= OOS size for no gaps)
MIN_OOS_TRADES = 30         # Below this, OOS window marked inconclusive
RISK_PCT       = DEFAULT_RISK_PCT


def build_windows(n_bars: int) -> List[Dict]:
    """
    Build anchored walk-forward windows.

    Anchored = IS always starts at bar 0, grows each step.
    OOS is always the next OOS_BARS after IS end.

    Returns list of dicts with is_start, is_end, oos_start, oos_end (indices).
    """
    windows = []
    is_end = MIN_IS_BARS

    while is_end + OOS_BARS <= n_bars:
        windows.append({
            "is_start":  0,
            "is_end":    is_end,
            "oos_start": is_end,
            "oos_end":   is_end + OOS_BARS,
        })
        is_end += STEP_BARS

    return windows


def run_on_slice(df_slice: pd.DataFrame, signals: pd.Series,
                 sl_prices: pd.Series, tp_prices: pd.Series,
                 start: int, end: int) -> dict:
    """Run simulation on a contiguous slice [start:end] of the data."""
    s = slice(start, end)
    d = df_slice.iloc[s].reset_index(drop=True)
    sig = signals.iloc[s].reset_index(drop=True)
    sl = sl_prices.iloc[s].reset_index(drop=True)
    tp = tp_prices.iloc[s].reset_index(drop=True)

    if len(d) < 50:
        return {"total_trades": 0, "win_rate": 0, "profit_factor": 0,
                "max_drawdown": 0, "x10_count": 0, "final_balance": INITIAL_BALANCE,
                "return_pct": 0, "blown_account": False, "equity_curve": []}

    return run_simulation(d, sig, sl, tp, sig, risk_pct=RISK_PCT)


def degradation_ratio(is_val: float, oos_val: float, metric: str) -> Optional[float]:
    """
    Compute OOS/IS ratio. For max_drawdown, invert (lower IS is better,
    so ratio >1 means OOS is worse).
    """
    if metric == "max_drawdown":
        # For DD: ratio = oos_dd / is_dd. >1 means worse OOS.
        if is_val == 0:
            return None
        return oos_val / is_val
    else:
        # For WR, PF: ratio = oos / is. <1 means degradation.
        if is_val == 0:
            return None
        return oos_val / is_val


def walk_forward_single(strategy_path: Path, df: pd.DataFrame,
                        windows: List[Dict]) -> Dict:
    """
    Run anchored walk-forward for a single strategy.

    Returns dict with per-window results and aggregate degradation.
    """
    sid = strategy_path.stem.upper().replace("STRATEGY_", "")

    # Load strategy and generate signals on full dataset
    try:
        module = load_strategy(strategy_path)
        signals, sl_prices, tp_prices = get_strategy_signals(module, df)
    except Exception as e:
        return {"strategy": sid, "error": str(e), "windows": [], "aggregate": {}}

    window_results = []

    for wi, w in enumerate(windows):
        # In-sample run
        is_metrics = run_on_slice(df, signals, sl_prices, tp_prices,
                                 w["is_start"], w["is_end"])
        # Out-of-sample run
        oos_metrics = run_on_slice(df, signals, sl_prices, tp_prices,
                                  w["oos_start"], w["oos_end"])

        oos_trades = oos_metrics["total_trades"]
        conclusive = oos_trades >= MIN_OOS_TRADES

        # Degradation ratios
        ratios = {}
        for m in ["win_rate", "profit_factor", "max_drawdown"]:
            ratios[f"{m}_ratio"] = degradation_ratio(
                is_metrics[m], oos_metrics[m], m
            )

        window_results.append({
            "window":        wi + 1,
            "is_bars":       w["is_end"] - w["is_start"],
            "oos_bars":      w["oos_end"] - w["oos_start"],
            "is_trades":     is_metrics["total_trades"],
            "oos_trades":    oos_trades,
            "conclusive":    conclusive,
            "is_wr":         is_metrics["win_rate"],
            "oos_wr":        oos_metrics["win_rate"],
            "is_pf":         is_metrics["profit_factor"],
            "oos_pf":        oos_metrics["profit_factor"],
            "is_dd":         is_metrics["max_drawdown"],
            "oos_dd":        oos_metrics["max_drawdown"],
            "is_return":     is_metrics["return_pct"],
            "oos_return":    oos_metrics["return_pct"],
            "is_blown":      is_metrics.get("blown_account", False),
            "oos_blown":     oos_metrics.get("blown_account", False),
            **ratios,
        })

    # Aggregate: mean degradation across conclusive windows only
    conclusive_windows = [wr for wr in window_results if wr["conclusive"]]
    n_conclusive = len(conclusive_windows)

    aggregate = {
        "strategy":           sid,
        "total_windows":      len(window_results),
        "conclusive_windows": n_conclusive,
    }

    if n_conclusive > 0:
        for m in ["win_rate", "profit_factor", "max_drawdown"]:
            key = f"{m}_ratio"
            vals = [w[key] for w in conclusive_windows if w[key] is not None]
            aggregate[f"mean_{key}"] = round(np.mean(vals), 4) if vals else None

        # Mean OOS metrics
        aggregate["mean_oos_wr"] = round(
            np.mean([w["oos_wr"] for w in conclusive_windows]), 4)
        aggregate["mean_oos_pf"] = round(
            np.mean([w["oos_pf"] for w in conclusive_windows]), 4)
        aggregate["mean_oos_dd"] = round(
            np.mean([w["oos_dd"] for w in conclusive_windows]), 4)
        aggregate["oos_blown_count"] = sum(
            1 for w in conclusive_windows if w["oos_blown"])

        # Verdict: survives walk-forward?
        mean_wr_ratio = aggregate.get("mean_win_rate_ratio")
        mean_pf_ratio = aggregate.get("mean_profit_factor_ratio")
        # Strategy survives if OOS retains ≥70% of IS performance
        survives = (
            mean_wr_ratio is not None and mean_wr_ratio >= 0.70 and
            mean_pf_ratio is not None and mean_pf_ratio >= 0.70 and
            aggregate["mean_oos_pf"] >= 1.0 and
            aggregate["oos_blown_count"] == 0
        )
        aggregate["survives_wf"] = bool(survives)
    else:
        aggregate["survives_wf"] = None  # inconclusive

    return {
        "strategy":  sid,
        "windows":   window_results,
        "aggregate": aggregate,
    }


def print_report(result: Dict):
    """Print human-readable walk-forward report for one strategy."""
    sid = result["strategy"]
    agg = result["aggregate"]

    if "error" in result and result["error"]:
        print(f"\n[{sid}] ERROR: {result['error']}")
        return

    print(f"\n{'='*70}")
    print(f"  WALK-FORWARD REPORT: {sid}")
    print(f"{'='*70}")
    print(f"  Windows: {agg['total_windows']} total, {agg['conclusive_windows']} conclusive"
          f" (min {MIN_OOS_TRADES} OOS trades)")

    if agg["conclusive_windows"] == 0:
        print("  ** ALL WINDOWS INCONCLUSIVE — not enough OOS trades **")
        return

    # Per-window table
    print(f"\n  {'Win':>3} | {'IS bars':>7} | {'IS tr':>5} | {'OOS tr':>6} | "
          f"{'IS WR':>6} {'OOS WR':>6} {'WR rat':>6} | "
          f"{'IS PF':>6} {'OOS PF':>6} {'PF rat':>6} | "
          f"{'OOS DD':>6} | {'Concl':>5} | {'Blown':>5}")
    print(f"  {'-'*3}-+-{'-'*7}-+-{'-'*5}-+-{'-'*6}-+-"
          f"{'-'*6}-{'-'*6}-{'-'*6}-+-"
          f"{'-'*6}-{'-'*6}-{'-'*6}-+-"
          f"{'-'*6}-+-{'-'*5}-+-{'-'*5}")

    for w in result["windows"]:
        wr_r = f"{w['win_rate_ratio']:.2f}" if w["win_rate_ratio"] is not None else "  n/a"
        pf_r = f"{w['profit_factor_ratio']:.2f}" if w["profit_factor_ratio"] is not None else "  n/a"
        concl = "  yes" if w["conclusive"] else "   NO"
        blown = " BLOWN" if w["oos_blown"] else "    ok"
        print(f"  {w['window']:>3} | {w['is_bars']:>7,} | {w['is_trades']:>5} | {w['oos_trades']:>6} | "
              f"{w['is_wr']:>5.1%} {w['oos_wr']:>5.1%} {wr_r:>6} | "
              f"{w['is_pf']:>6.2f} {w['oos_pf']:>6.2f} {pf_r:>6} | "
              f"{w['oos_dd']:>5.1%} | {concl} | {blown}")

    # Aggregate
    print(f"\n  AGGREGATE (conclusive windows only):")
    print(f"    Mean WR  ratio (OOS/IS): {agg.get('mean_win_rate_ratio', 'n/a')}")
    print(f"    Mean PF  ratio (OOS/IS): {agg.get('mean_profit_factor_ratio', 'n/a')}")
    print(f"    Mean DD  ratio (OOS/IS): {agg.get('mean_max_drawdown_ratio', 'n/a')}")
    print(f"    Mean OOS WR:  {agg.get('mean_oos_wr', 'n/a')}")
    print(f"    Mean OOS PF:  {agg.get('mean_oos_pf', 'n/a')}")
    print(f"    Mean OOS DD:  {agg.get('mean_oos_dd', 'n/a')}")
    print(f"    OOS blown:    {agg.get('oos_blown_count', 'n/a')}")

    verdict = agg.get("survives_wf")
    if verdict is True:
        print(f"\n  *** VERDICT: SURVIVES walk-forward ***")
    elif verdict is False:
        print(f"\n  *** VERDICT: FAILS walk-forward ***")
    else:
        print(f"\n  *** VERDICT: INCONCLUSIVE ***")


def main(strategy_ids: List[str] = None):
    print("Loading data...")
    df = load_data()
    df = add_regime_indicators(df)
    print(f"  {len(df):,} bars, {df['time'].min()} to {df['time'].max()}")

    windows = build_windows(len(df))
    print(f"  Walk-forward windows: {len(windows)}")
    for i, w in enumerate(windows):
        print(f"    W{i+1}: IS [0:{w['is_end']:,}] -> OOS [{w['oos_start']:,}:{w['oos_end']:,}]")

    # Discover strategies
    if strategy_ids:
        strategy_files = []
        for sid in strategy_ids:
            sid_lower = sid.lower().replace("s", "s")
            path = STRATEGY_DIR / f"strategy_s{sid_lower.replace('s', '')}.py"
            if not path.exists():
                path = STRATEGY_DIR / f"strategy_{sid_lower}.py"
            if path.exists():
                strategy_files.append(path)
            else:
                print(f"  WARNING: strategy file not found for {sid}")
    else:
        strategy_files = sorted(STRATEGY_DIR.glob("strategy_s*.py"))

    print(f"  Strategies to test: {len(strategy_files)}")

    all_results = []
    all_aggregates = []

    for sf in strategy_files:
        sid = sf.stem.upper().replace("STRATEGY_", "")
        print(f"\n  Running {sid}...", end="", flush=True)
        result = walk_forward_single(sf, df, windows)
        print_report(result)
        all_results.append(result)
        if result.get("aggregate"):
            all_aggregates.append(result["aggregate"])

    # Save aggregate summary
    if all_aggregates:
        agg_df = pd.DataFrame(all_aggregates)
        out_path = RESULTS_DIR / "walk_forward_summary.csv"
        agg_df.to_csv(out_path, index=False)
        print(f"\n\nSummary saved -> {out_path}")

        survivors = agg_df[agg_df.get("survives_wf", False) == True]
        print(f"\n{'='*70}")
        print(f"  FINAL: {len(survivors)}/{len(agg_df)} strategies survive walk-forward")
        print(f"{'='*70}")
        if len(survivors) > 0:
            print(survivors.to_string(index=False))

    return all_results


if __name__ == "__main__":
    # Parse strategy IDs from command line
    ids = sys.argv[1:] if len(sys.argv) > 1 else None
    main(ids)
