"""
Batch2 Runner — runs all 50 batch2 strategies through the engine.
Usage: python run_batch2.py
"""
import sys
from pathlib import Path

BASE_DIR = Path(r"C:\Users\hp\XAUUSD-SCALPER-X10")
sys.path.insert(0, str(BASE_DIR / "backtests"))

import engine

# Override strategy directory and results path for batch2
engine.STRATEGY_DIR = BASE_DIR / "strategies" / "batch2"
engine.RESULTS_DIR  = BASE_DIR / "backtests" / "results"
engine.RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# Patch run_batch to use b*.py glob instead of strategy_s*.py
_orig_run_batch = engine.run_batch

def run_batch2():
    """Run batch2 strategies (b001.py - b050.py)."""
    import pandas as pd
    import numpy as np
    import math

    print("=" * 60)
    print("XAUUSD-SCALPER-X10  |  Batch 2 Backtest")
    print(f"Balance : ${engine.INITIAL_BALANCE:,.0f}  |  Dynamic lot sizing")
    print(f"Risk %  : {[f'{r*100:.0f}%' for r in engine.RISK_PERCENTS]}")
    print("=" * 60)

    print("\nLoading M1 data...")
    df = engine.load_data()
    df = engine.add_regime_indicators(df)
    print(f"  Bars loaded : {len(df):,}")
    print(f"  Date range  : {df['time'].min()} to {df['time'].max()}")

    regime_counts = df["regime"].value_counts()
    print(f"\nRegime distribution:")
    for r, c in regime_counts.items():
        print(f"  {r:<20}: {c:,} bars ({c/len(df):.1%})")

    known_regimes = [r for r in ["TREND", "RANGE", "HIGH_VOLATILITY"] if r in df["regime"].values]
    regime_masks  = {r: df["regime"] == r for r in known_regimes}

    strategy_files = sorted(engine.STRATEGY_DIR.glob("b*.py"))
    print(f"\nBatch2 strategies found: {len(strategy_files)}")

    rows      = []
    validated = []

    for sf in strategy_files:
        sid = sf.stem.upper()
        print(f"\n  [{sid}] {sf.name}")

        try:
            module = engine.load_strategy(sf)
        except Exception as e:
            print(f"    LOAD ERROR: {e}")
            rows.append({"strategy": sid, "risk_pct": None, "error": str(e)})
            continue

        try:
            signals, sl_prices, tp_prices = engine.get_strategy_signals(module, df)
        except Exception as e:
            print(f"    SIGNAL ERROR: {e}")
            rows.append({"strategy": sid, "risk_pct": None, "error": f"signal: {e}"})
            continue

        for risk_pct in engine.RISK_PERCENTS:
            label = f"{risk_pct*100:.0f}%"
            print(f"    risk={label:<4}", end="  ")

            try:
                full_metrics = engine.run_simulation(df, signals, sl_prices, tp_prices,
                                                     signals, risk_pct=risk_pct)
            except Exception as e:
                print(f"SIM ERROR: {e}")
                rows.append({"strategy": sid, "risk_pct": label, "error": f"sim: {e}"})
                continue

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
                    rm = engine.run_simulation(r_df, r_sig, r_sl, r_tp, r_sig,
                                               risk_pct=risk_pct)
                    regime_results[regime_name] = rm
                    if rm["total_trades"] > 0:
                        regimes_with_trades += 1
                except Exception:
                    pass

            regimes_tested = regimes_with_trades
            passed, fails  = engine.validate(full_metrics, regimes_tested)
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
            for r in ["TREND", "RANGE", "HIGH_VOLATILITY"]:
                rm = regime_results.get(r, {})
                row[f"{r}_trades"] = rm.get("total_trades", 0)
                row[f"{r}_wr"]     = rm.get("win_rate", None)
                row[f"{r}_pf"]     = rm.get("profit_factor", None)
                row[f"{r}_dd"]     = rm.get("max_drawdown", None)

            rows.append(row)
            if passed:
                validated.append(row)

    results_df   = pd.DataFrame(rows)
    results_path = engine.RESULTS_DIR / "batch2_results.csv"
    results_df.to_csv(results_path, index=False)
    print(f"\n\nResults saved -> {results_path}")

    passed_count = len(validated)
    print(f"\n{'='*60}")
    print(f"SUMMARY: {passed_count} strategy/risk_pct combos PASSED validation")
    print(f"{'='*60}")

    if passed_count > 0:
        val_df   = pd.DataFrame(validated)
        val_path = engine.RESULTS_DIR / "batch2_validated.csv"
        val_df.to_csv(val_path, index=False)
        print(f"\nValidated strategies saved -> {val_path}")
        for v in validated:
            print(f"  {v['strategy']} risk={v['risk_pct']}"
                  f"  WR={v['win_rate']:.1%}  PF={v['profit_factor']:.2f}"
                  f"  DD={v['max_drawdown']:.1%}  x10={v['x10_count']}"
                  f"  trades={v['total_trades']}")

    return {"passed": validated, "all": rows}


if __name__ == "__main__":
    run_batch2()
