"""Monte Carlo robustness agent for the X10 research objective.

The model uses normalized fixed-fraction outcomes inferred from validated
strategy statistics. It is comparative robustness evidence, not a promise of
future returns. Results are deterministic for the same strategy/data/metrics
and trade frequency is measured on the same selection window as backtesting.
"""

import hashlib
import json
import math
import random
import traceback
from typing import Optional

import pandas as pd

from agents.base_agent import BaseAgent
from agents.backtest_runner import BacktestRunner
from core.config import (
    DEFAULT_RISK_PCT,
    INITIAL_BALANCE,
    X10_HORIZON_DAYS,
    X10_TARGET_MULTIPLE,
    MC_RUIN_BALANCE_FRACTION,
    HOLDOUT_MONTHS,
)

ANALYSIS_PER_FAMILY = 8
MC_MAX_PER_TICK = 8


def _implied_reward_risk(win_rate: float, profit_factor: float) -> float:
    if win_rate <= 0 or win_rate >= 1 or profit_factor <= 0:
        return 1.0
    rr = profit_factor * (1.0 - win_rate) / win_rate
    return max(0.25, min(float(rr), 10.0))


def selection_trading_days(df: pd.DataFrame) -> int:
    """Count weekdays in the exact pre-holdout selection window."""
    if df is None or len(df) == 0 or "time" not in df.columns:
        return 0
    times = pd.to_datetime(df["time"], errors="coerce")
    if times.isna().any():
        return 0
    holdout_start = times.iloc[-1] - pd.DateOffset(months=HOLDOUT_MONTHS)
    h_idx = int((times < holdout_start).sum())
    if h_idx < 5000 or (len(df) - h_idx) < 1000:
        return 0
    selection = times.iloc[:h_idx]
    weekdays = selection[selection.dt.weekday < 5].dt.date
    return max(1, int(pd.Series(weekdays).nunique())) if len(weekdays) else 0


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
    seed: Optional[int] = None,
) -> dict:
    """Estimate X10 and drawdown probabilities with fixed-fraction risk."""
    win_rate = max(0.0, min(float(win_rate), 1.0))
    reward_risk = max(0.01, float(reward_risk))
    risk_pct = max(0.0001, min(float(risk_pct), 0.50))
    trades_per_day = max(0.0, float(trades_per_day))
    horizon_trades = max(1, int(round(trades_per_day * horizon_days)))
    rng = random.Random(seed)

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
            if rng.random() < win_rate:
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
        "seed": seed,
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
            "trade frequency from pre-holdout selection history",
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
        self.logger.info(
            f"Monte Carlo V2 ready — deterministic, up to {ANALYSIS_PER_FAMILY} variants/family"
        )

    def tick(self):
        strategies = self._get_untested_strategies()
        if not strategies:
            return
        max_per_tick = max(1, int(self.get_config("max_per_tick", MC_MAX_PER_TICK)))
        for strategy in strategies[:max_per_tick]:
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
        per_family = max(1, int(self.get_config("analysis_per_family", ANALYSIS_PER_FAMILY)))
        rows = self.db.fetchall(
            "SELECT id, best_config FROM ("
            "  SELECT id, best_config, ROW_NUMBER() OVER ("
            "    PARTITION BY family ORDER BY best_profit_factor DESC"
            "  ) AS rn FROM strategies "
            "  WHERE status IN ('validated','portfolio_reserve') "
            "  AND walk_forward_passed = 1"
            ") WHERE rn <= ? ORDER BY rn, id",
            (per_family,),
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
            "SELECT total_trades, win_rate, profit_factor, risk_pct, data_hash "
            "FROM backtest_results WHERE strategy_id = ? "
            "ORDER BY run_at DESC, id DESC LIMIT 1",
            (strategy_id,),
        )
        return dict(row) if row else None

    def _reward_risk(self, strategy_id: str, wr: float, pf: float) -> float:
        # Realized PF/WR better represents the full validated exit machinery
        # (time exits, trailing, spread/slippage) than the nominal TP/SL ratio.
        return _implied_reward_risk(wr, pf)

    def _trading_days_in_selection(self) -> int:
        try:
            df = self._bt_runner._load_data_m5()
            return selection_trading_days(df)
        except Exception:
            return 0

    @staticmethod
    def _seed_for(strategy_id: str, metrics: dict) -> int:
        material = "|".join(
            [
                strategy_id,
                str(metrics.get("data_hash") or ""),
                str(metrics.get("total_trades") or 0),
                f"{float(metrics.get('win_rate') or 0.0):.8f}",
                f"{float(metrics.get('profit_factor') or 0.0):.8f}",
                f"{float(metrics.get('risk_pct') or 0.0):.8f}",
            ]
        )
        return int(hashlib.sha256(material.encode("utf-8")).hexdigest()[:16], 16)

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

        trading_days = self._trading_days_in_selection()
        if trading_days <= 0:
            self.logger.warning(f"No selection-window trading-day denominator for {strategy_id}; MC skipped")
            return

        reward_risk = self._reward_risk(strategy_id, wr, pf)
        trades_per_day = trades / trading_days
        risk_pct = float(metrics.get("risk_pct") or DEFAULT_RISK_PCT)
        n_sims = int(self.get_config("n_simulations", 10000))
        seed = self._seed_for(strategy_id, metrics)
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
            seed=seed,
        )

        row = self.db.fetchone("SELECT best_config FROM strategies WHERE id = ?", (strategy_id,))
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
            f"P(ruin/10d)={result['p_ruin_10d']:.1%}, P95 DD={result['p95_dd_10d']:.1%}",
            metadata={"strategy_id": strategy_id, "monte_carlo": result},
        )
