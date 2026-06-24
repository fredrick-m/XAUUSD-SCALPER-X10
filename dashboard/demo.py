"""
Demo script - simulates a backtest running to test the dashboard.
Run dashboard/app.py first, then run this in a second terminal.
Usage: python -m dashboard.demo
"""

import time
import random
import math
import numpy as np
from dashboard.live_writer import LiveWriter


def run_demo():
    writer = LiveWriter()
    print("Demo backtest starting... Open http://localhost:8050")

    balance = 50.0
    equity_curve = [balance]
    trades = []
    wins = 0
    losses_val = 0
    gross_profit = 0.0
    gross_loss = 0.0
    peak = balance
    max_dd = 0.0
    x10_count = 0
    next_x10 = 500.0

    strategies = ["S028_ATR_Channel_20"]
    regimes = ["TREND", "RANGE", "HIGH_VOL"]
    stages = ["SCAN", "DETECT", "VALIDATE", "SIZE", "FILL", "SETTLE"]

    regime_stats = {
        "TREND": {"win_rate": 0, "profit_factor": 0, "max_drawdown": 0, "trades": 0, "wins": 0,
                  "gp": 0, "gl": 0},
        "RANGE": {"win_rate": 0, "profit_factor": 0, "max_drawdown": 0, "trades": 0, "wins": 0,
                  "gp": 0, "gl": 0},
        "HIGH_VOL": {"win_rate": 0, "profit_factor": 0, "max_drawdown": 0, "trades": 0, "wins": 0,
                     "gp": 0, "gl": 0},
    }

    # Simulate 200 trades
    for i in range(200):
        regime = random.choice(regimes)
        side = random.choice(["LONG", "SHORT"])
        entry_price = 4500 + random.uniform(-50, 50)

        # Pipeline animation
        for stage in stages:
            decision_tree = [
                {"condition": f"ADX > 25 ({regime})", "pass": regime == "TREND",
                 "confidence": random.uniform(0.6, 0.95)},
                {"condition": f"ATR breakout confirmed", "pass": random.random() > 0.3,
                 "confidence": random.uniform(0.5, 0.9)},
                {"condition": f"Volume filter", "pass": random.random() > 0.4,
                 "confidence": random.uniform(0.4, 0.85)},
                {"condition": f"Risk/reward >= 1.75", "pass": True,
                 "confidence": random.uniform(0.7, 0.99)},
            ]
            writer.update(
                balance=balance, equity_curve=equity_curve, trades=trades,
                strategy=strategies[0], pipeline_stage=stage, regime=regime,
                decision_tree=decision_tree,
                metrics={"total_trades": i, "win_rate": wins / max(i, 1),
                         "profit_factor": gross_profit / max(gross_loss, 0.01),
                         "max_drawdown": max_dd, "x10_count": x10_count},
                regime_stats={k: {"win_rate": v["wins"] / max(v["trades"], 1),
                                  "profit_factor": v["gp"] / max(v["gl"], 0.01),
                                  "max_drawdown": v["max_drawdown"]}
                              for k, v in regime_stats.items()},
            )
            time.sleep(0.08)

        # Resolve trade
        win = random.random() < 0.42  # ~42% WR like S028
        if win:
            pnl = random.uniform(0.5, 8.0) * (balance / 50)
            wins += 1
            gross_profit += pnl
        else:
            pnl = -random.uniform(0.3, 4.0) * (balance / 50)
            gross_loss += abs(pnl)

        balance += pnl
        equity_curve.append(balance)

        # Regime stats
        rs = regime_stats[regime]
        rs["trades"] += 1
        if win:
            rs["wins"] += 1
            rs["gp"] += pnl
        else:
            rs["gl"] += abs(pnl)

        # Drawdown
        if balance > peak:
            peak = balance
        dd = (peak - balance) / peak if peak > 0 else 0
        if dd > max_dd:
            max_dd = dd
        rs["max_drawdown"] = max(rs["max_drawdown"], dd)

        # x10
        while balance >= next_x10:
            x10_count += 1
            next_x10 *= 10

        trade = {
            "side": side,
            "entry": round(entry_price, 2),
            "pnl": round(pnl, 2),
            "regime": regime,
            "bar": i * 50,
        }
        trades.append(trade)

        n = len(trades)
        wr = wins / n
        pf = gross_profit / max(gross_loss, 0.01)

        writer.update(
            balance=balance, equity_curve=equity_curve, trades=trades,
            strategy=strategies[0], pipeline_stage="SETTLE", regime=regime,
            decision_tree=decision_tree,
            metrics={"total_trades": n, "win_rate": wr, "profit_factor": pf,
                     "max_drawdown": max_dd, "x10_count": x10_count},
            regime_stats={k: {"win_rate": v["wins"] / max(v["trades"], 1),
                              "profit_factor": v["gp"] / max(v["gl"], 0.01),
                              "max_drawdown": v["max_drawdown"]}
                          for k, v in regime_stats.items()},
        )

        if i % 20 == 0:
            print(f"  Trade {i+1}/200  bal=${balance:.2f}  WR={wr:.1%}  PF={pf:.2f}  DD={max_dd:.1%}")

        time.sleep(0.15)

        if balance <= 0:
            print(f"  BLOWN at trade {i+1}")
            break

    # Monte Carlo simulation
    print("Running Monte Carlo (500 paths)...")
    trade_pnls = [t["pnl"] for t in trades if isinstance(t, dict)]
    mc_paths = []
    mc_finals = []
    for _ in range(500):
        shuffled = random.sample(trade_pnls, len(trade_pnls))
        path = [50.0]
        b = 50.0
        for p in shuffled:
            b += p
            path.append(max(b, 0))
            if b <= 0:
                break
        mc_paths.append(path)
        mc_finals.append(path[-1])

    mc_finals.sort()
    var95 = mc_finals[int(0.05 * len(mc_finals))]
    p_profit = sum(1 for f in mc_finals if f > 50) / len(mc_finals)
    median_path = []
    max_len = max(len(p) for p in mc_paths)
    for j in range(max_len):
        vals = [p[j] for p in mc_paths if j < len(p)]
        median_path.append(float(np.median(vals)))

    writer.update(
        balance=balance, equity_curve=equity_curve, trades=trades,
        strategy=strategies[0], pipeline_stage="SETTLE", regime=regime,
        decision_tree=decision_tree,
        metrics={"total_trades": len(trades), "win_rate": wins / max(len(trades), 1),
                 "profit_factor": gross_profit / max(gross_loss, 0.01),
                 "max_drawdown": max_dd, "x10_count": x10_count},
        regime_stats={k: {"win_rate": v["wins"] / max(v["trades"], 1),
                          "profit_factor": v["gp"] / max(v["gl"], 0.01),
                          "max_drawdown": v["max_drawdown"]}
                      for k, v in regime_stats.items()},
        monte_carlo={"paths": mc_paths[:100], "median": median_path,
                     "var95": var95, "p_profit": p_profit,
                     "expected": float(np.mean(mc_finals))},
        status="COMPLETE",
    )

    writer.close()
    print(f"\nDemo complete. Final balance: ${balance:.2f}")
    print(f"Monte Carlo: VaR95=${var95:.2f}, P(profit)={p_profit:.1%}, E[final]=${np.mean(mc_finals):.2f}")


if __name__ == "__main__":
    run_demo()
