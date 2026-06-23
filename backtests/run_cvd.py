"""
Runner: CVD_Divergence strategy on XAUUSD M1
Tests risk_pct: 5%, 10%, 20% using the existing engine.
"""
import sys
from pathlib import Path

BASE_DIR = Path(r"C:\Users\hp\XAUUSD-SCALPER-X10")
sys.path.insert(0, str(BASE_DIR / "backtests"))

from engine import (
    load_data, add_regime_indicators, load_strategy,
    get_strategy_signals, run_simulation, validate,
    MIN_WIN_RATE, MIN_PF, MAX_DD, MIN_X10_COUNT, MIN_TRADES, MIN_REGIMES,
    INITIAL_BALANCE,
)

CVD_PATH   = BASE_DIR / "strategies" / "batch3" / "cvd_strategy.py"
RISK_PCTS  = [0.05, 0.10, 0.20]   # 5%, 10%, 20% as requested

print("=" * 60)
print("XAUUSD-SCALPER-X10  |  CVD Strategy Backtest")
print(f"Strategy : {CVD_PATH.name}")
print(f"Balance  : ${INITIAL_BALANCE:,.0f}  |  Risk%: {[f'{r*100:.0f}%' for r in RISK_PCTS]}")
print("=" * 60)

print("\nLoading M1 data...")
df = load_data()
df = add_regime_indicators(df)
print(f"  Bars      : {len(df):,}")
print(f"  Date range: {df['time'].min()} to {df['time'].max()}")

known_regimes = [r for r in ["TREND", "RANGE", "HIGH_VOLATILITY"] if r in df["regime"].values]
regime_masks  = {r: df["regime"] == r for r in known_regimes}
print(f"  Regimes   : {known_regimes}")

print("\nLoading CVD strategy...")
module = load_strategy(CVD_PATH)
signals, sl_prices, tp_prices = get_strategy_signals(module, df)
n_sig = (signals != 0).sum()
print(f"  Total signals: {n_sig} ({(signals==1).sum()} long, {(signals==-1).sum()} short)")

print()
print("-" * 60)
print(f"{'Risk%':<8} {'Trades':<8} {'WR':<8} {'PF':<8} {'MaxDD':<8} {'x10':<6} {'Result'}")
print("-" * 60)

all_results = []
for risk_pct in RISK_PCTS:
    label = f"{risk_pct*100:.0f}%"

    m = run_simulation(df, signals, sl_prices, tp_prices, signals, risk_pct=risk_pct)

    # Count regimes with trades
    regimes_with_trades = 0
    for regime_name, mask in regime_masks.items():
        r_df  = df[mask].reset_index(drop=True)
        r_sig = signals[mask].reset_index(drop=True)
        r_sl  = sl_prices[mask].reset_index(drop=True)
        r_tp  = tp_prices[mask].reset_index(drop=True)
        if len(r_df) < 50:
            continue
        try:
            rm = run_simulation(r_df, r_sig, r_sl, r_tp, r_sig, risk_pct=risk_pct)
            if rm["total_trades"] > 0:
                regimes_with_trades += 1
        except Exception:
            pass

    passed, fails = validate(m, regimes_with_trades)
    status = "PASS" if passed else "FAIL"

    print(f"{label:<8} {m['total_trades']:<8} {m['win_rate']:.1%}   "
          f"{m['profit_factor']:<8.2f} {m['max_drawdown']:.1%}   "
          f"{m['x10_count']:<6} {status}")
    if fails:
        for f in fails:
            print(f"         FAIL: {f}")

    all_results.append({
        "risk_pct": label,
        "total_trades": m["total_trades"],
        "win_rate": m["win_rate"],
        "profit_factor": m["profit_factor"],
        "max_drawdown": m["max_drawdown"],
        "x10_count": m["x10_count"],
        "regimes_tested": regimes_with_trades,
        "final_balance": m["final_balance"],
        "passed": passed,
        "fail_reasons": "; ".join(fails),
    })

print("-" * 60)

# Best result summary
best = max(all_results, key=lambda r: sum([
    r["win_rate"] > MIN_WIN_RATE,
    r["profit_factor"] >= MIN_PF,
    r["max_drawdown"] < MAX_DD,
    r["x10_count"] >= MIN_X10_COUNT,
    r["total_trades"] >= MIN_TRADES,
    r["regimes_tested"] >= MIN_REGIMES,
]))

print(f"\nBest combo : risk={best['risk_pct']}  "
      f"WR={best['win_rate']:.1%}  PF={best['profit_factor']:.2f}  "
      f"DD={best['max_drawdown']:.1%}  x10={best['x10_count']}  "
      f"trades={best['total_trades']}")
print()
