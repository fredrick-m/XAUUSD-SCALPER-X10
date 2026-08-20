"""Monte Carlo robustness agent for the X10 objective.

This module deliberately avoids reconstructing closed-trade P&Ls from the
floating equity curve. The equity curve contains mark-to-market changes while
a trade is open, so treating every non-zero bar delta as a trade corrupts the
Monte Carlo sample.

Instead we simulate a normalized fixed-fraction risk model from independently
validated strategy statistics:
- historical win rate
- reward/risk ratio (prefer strategy TP/SL params; otherwise implied by PF+WR)
- observed trade frequency
- configured risk per trade

The result is a MODEL ESTIMATE, not a promise of future performance. Its main
purpose is to compare strategies under the same $500 -> $5,000 / 10 trading-day
objective and expose combinations with unacceptable drawdown/ruin risk.
"""

import json
import math
import random
import traceback
from typing import Optional

from agents.base_agent import BaseAgent
from agents.backtest_runner import BacktestRunner
from core.config import (
    DEFAULT_RISK_PCT,
    INITIAL_BALANCE,
    X10_HORIZON_DAYS,
    X10_TARGET_MULTIPLE,
    MC_RUIN_BALANCE_FRACTION,
)


def _implied_reward_risk(win_rate: float, profit_factor: float) -> float:
    """Infer average win / average loss from PF and WR."""
    if win_rate <= 0 or win_rate >= 1 or profit_factor <= 0:
        return 1.0
    rr = profit_factor * (1.0 - win_rate) / win_rate
    return max(0.25, min(float(rr), 10.0))


def monte_carlo_x10(
    win_rate: float,
    reward_risk: float,
    risk_pct: float,
    trades_per_day: float,
    n_sims: int = 10000,
    initial_balance: float = INITIAL_BALANCE,
    horizon_days: int = X10_HORIZON_DAYS,
    target_multiple: float = X10_TARGET_MULTIPLE,
    ruin_balance_fraction: float = MC_RUIN_BALANCE_FRACTION,
) -> dict:
    """Estimate X10 and drawdown probabilities with fixed-fraction risk."""
    win_rate = max(0.0, min(float(win_rate), 1.0))
    reward_risk = max(0.01, float(reward_risk))
    risk_pct = max(0.0001, min(float(risk_pct), 0.50))
    trades_per_day = max(0.0, float(trades_per_day))
    horizon_trades = max(1, int(round(trades_per_day * horizon_days)))

    target = initial_balance * target_multiple
    ruin_floor = initial_balance * ruin_balance_fraction

    x10_hits = 0
    ruin_hits = 0
    max_dds = []
    final_balances = []

    for _ in range(int(n_sims)):
        balance = float(initial_balance)
        peak = balance
        max_dd = 0.0
        hit_target = False
        ruined = False

        for _trade in range(horizon_trades):
            if random.random() < win_rate:
                balance *= 1.0 + risk_pct * reward_risk
            else:
                balance *= 1.0 - risk_pct

            if balance > peak:
                peak = balance
            dd = (peak - balance) / peak if peak > 0 else 1.0
            max_dd = max(max_dd, dd)

            if balance >= target:
                hit_target = True
                break
            if balance <= ruin_floor:
                ruined = True
                break

        x10_hits += int(hit_target)
        ruin_hits += int(ruined)
        max_dds.append(max_dd)
        final_balances.append(balance)

    max_dds.sort()
    final_balances.sort()
    n = max(1, int(n_sims))

    def percentile(values: list[float], q: float) -> float:
        if not values:
            return 0.0
        idx = min(len(values) - 1, max(0, int(math.ceil(q * len(values))) - 1))
        return float(values[idx])

    p_x10_10d = round(x10_hits / n, 4)
    p_ruin_10d = round(ruin_hits / n, 4)
    median_dd_10d = round(percentile(max_dds, 0.50), 4)
    p95_dd_10d = round(percentile(max_dds, 0.95), 4)

    return {
        "model": "fixed_fraction_edge_model_v2",
        "initial_balance": round(initial_balance, 2),
        "target_balance": round(target, 2),
        "horizon_days": int(horizon_days),
        "horizon_trades": horizon_trades,
        "win_rate_input": round(win_rate, 6),
        "reward_risk_input": round(reward_risk, 4),
        "risk_pct_input": round(risk_pct, 6),
        "trades_per_day": round(trades_per_day, 4),
        "p_x10_10d": p_x10_10d,
        "p_ruin_10d": p_ruin_10d,
        "median_dd_10d": median_dd_10d,
        "p95_dd_10d": p95_dd_10d,
        "median_final_balance_10d": round(percentile(final_balances, 0.50), 2),
        "p05_final_balance_10d": round(percentile(final_balances, 0.05), 2),
        "p95_final_balance_10d": round(percentile(final_balances, 0.95), 2),
        "n_simulations": int(n_sims),
        "p_x10": p_x10_10d,
        "p_ruin": p_ruin_10d,
        "median_dd": median_dd_10d,
        "p95_dd": p95_dd_10d,
        "assumptions": [
            "independent trades",
            "stationary win rate and reward/risk",
            "fixed-fraction compounding",
            "trade frequency extrapolated from historical sample",
        ],
    }


class MonteCarlo(BaseAgent):
    """Scores WF+holdout survivors against the $500 -> $5,000 / 10-day goal."""

    name = "monte_carlo"

    def __init__(self, db):
        super().__init__(agent_id="monte_carlo", db=db)
        self._bt_runner: Optional[BacktestRunner] = None

    def setup(self):
        self._bt_runner = BacktestRunner(self.db)
        self._bt_runner.setup()
        self.logger.info("Monte Carlo V2 ready — $500 -> $5,000 / 10-day model")

    def tick(self):
        strategies = self._get_untested_strategies()
        if not strategies:
            return
        for strategy in strategies:
            try:
                self._run_mc_for_strategy(strategy["id"])
            except Exception as exc:
                self.logger.error(
                    f"Monte Carlo failed for {strategy['id']}: {exc}\n"
                    f"{traceback.format_exc()}"
                )

    def tick_interval(self) -> float:
        return self.get_config("tick_interval", 300)

    def _get_untested_strategies(self) -> list:
        """Top WF variants per family needing MC, including portfolio reserves.

        Portfolio V5 may reserve a strategy specifically because MC evidence is
        still missing. Reserves must therefore remain visible to this agent or
        the pipeline deadlocks permanently.
        """
        rows = self.db.fetchall(
            "SELECT id, best_config FROM ("
            "  SELECT id, best_config, ROW_NUMBER() OVER ("
            "    PARTITION BY family ORDER BY best_profit_factor DESC"
            "  ) AS rn FROM strategies "
            "  WHERE status IN ('validated','portfolio_reserve') "
            "  AND walk_forward_passed = 1"
            ") WHERE rn <= 3"
        )
        untested = []
        for row in rows:
            config = {}
            if row["best_config"]:
                try:
                    config = (
                        json.loads(row["best_config"])
                        if isinstance(row["best_config"], str)
                        else row["best_config"]
                    )
                except (json.JSONDecodeError, TypeError):
                    config = {}
            validation = config.get("validation_v2", {})
            if not validation.get("passed", False):
                continue
            mc = config.get("monte_carlo", {})
            if mc.get("model") != "fixed_fraction_edge_model_v2":
                untested.append(dict(row))
        return untested

    def _latest_metrics(self, strategy_id: str) -> Optional[dict]:
        row = self.db.fetchone(
            "SELECT total_trades, win_rate, profit_factor, risk_pct "
            "FROM backtest_results WHERE strategy_id = ? "
            "ORDER BY run_at DESC, id DESC LIMIT 1",
            (strategy_id,),
        )
        return dict(row) if row else None

    def _reward_risk(self, strategy_id: str, wr: float, pf: float) -> float:
        try:
            module = self._bt_runner._load_strategy_module(strategy_id)
            params = getattr(module, "PARAMS", {}) if module else {}
            sl_atr = float(params.get("sl_atr", 0.0))
            tp_atr = float(params.get("tp_atr", 0.0))
            if sl_atr > 0 and tp_atr > 0:
                return max(0.25, min(tp_atr / sl_atr, 10.0))
        except Exception:
            pass
        return _implied_reward_risk(wr, pf)

    def _trading_days_in_dataset(self) -> int:
        try:
            df = self._bt_runner._load_data_m5()
            if df is None or "time" not in df.columns or len(df) == 0:
                return 0
            dates = df.loc[df["time"].dt.weekday < 5, "time"].dt.date
            return max(1, int(dates.nunique()))
        except Exception:
            return 0

    def _run_mc_for_strategy(self, strategy_id: str):
        metrics = self._latest_metrics(strategy_id)
        if not metrics:
            self.logger.warning(f"No backtest metrics for {strategy_id}; MC skipped")
            return

        trades = int(metrics.get("total_trades") or 0)
        wr = float(metrics.get("win_rate") or 0.0)
        pf = float(metrics.get("profit_factor") or 0.0)
        if trades < 5 or wr <= 0 or pf <= 0:
            self.logger.warning(f"Insufficient metrics for {strategy_id}; MC skipped")
            return

        trading_days = self._trading_days_in_dataset()
        if trading_days <= 0:
            self.logger.warning(f"No trading-day denominator for {strategy_id}; MC skipped")
            return

        reward_risk = self._reward_risk(strategy_id, wr, pf)
        trades_per_day = trades / trading_days
        risk_pct = float(metrics.get("risk_pct") or DEFAULT_RISK_PCT)
        n_sims = int(self.get_config("n_simulations", 10000))

        result = monte_carlo_x10(
            win_rate=wr,
            reward_risk=reward_risk,
            risk_pct=risk_pct,
            trades_per_day=trades_per_day,
            n_sims=n_sims,
            initial_balance=float(self.get_config("initial_balance", INITIAL_BALANCE)),
            horizon_days=int(self.get_config("horizon_days", X10_HORIZON_DAYS)),
            target_multiple=float(self.get_config("target_multiple", X10_TARGET_MULTIPLE)),
            ruin_balance_fraction=MC_RUIN_BALANCE_FRACTION,
        )

        row = self.db.fetchone(
            "SELECT best_config FROM strategies WHERE id = ?", (strategy_id,)
        )
        config = {}
        if row and row["best_config"]:
            try:
                config = (
                    json.loads(row["best_config"])
                    if isinstance(row["best_config"], str)
                    else row["best_config"]
                )
            except (json.JSONDecodeError, TypeError):
                config = {}
        config["monte_carlo"] = result
        self.db.execute(
            "UPDATE strategies SET best_config = ? WHERE id = ?",
            (json.dumps(config), strategy_id),
        )

        is_fragile = result["p95_dd_10d"] > 0.50 or result["p_ruin_10d"] > 0.10
        event_type = "warning" if is_fragile else "milestone"
        self.emit_event(
            event_type,
            f"Monte Carlo V2 {strategy_id}: P(x10/10d)={result['p_x10_10d']:.1%}, "
            f"P(ruin/10d)={result['p_ruin_10d']:.1%}, "
            f"P95 DD={result['p95_dd_10d']:.1%}",
            metadata={"strategy_id": strategy_id, "monte_carlo": result},
        )
