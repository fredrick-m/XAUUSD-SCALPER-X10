"""Monte Carlo agent: runs robustness simulations on validated strategies."""
import json
import random
import statistics
import traceback
from typing import Optional

from agents.base_agent import BaseAgent
from agents.backtest_runner import BacktestRunner


def monte_carlo_trades(
    trades: list,
    n_sims: int = 10000,
    initial_balance: float = 50.0,
) -> dict:
    """
    Shuffle trade sequence n_sims times, compute distribution of outcomes.

    Parameters
    ----------
    trades          : list of individual trade P&Ls (floats).
    n_sims          : number of Monte Carlo iterations.
    initial_balance : starting account balance.

    Returns
    -------
    dict with keys: median_dd, p95_dd, p_x10, p_ruin, n_simulations
    """
    if not trades:
        return {
            "median_dd": 0.0,
            "p95_dd": 0.0,
            "p_x10": 0.0,
            "p_ruin": 0.0,
            "n_simulations": n_sims,
        }

    max_dds: list[float] = []
    final_bals: list[float] = []
    x10_count = 0
    ruin_count = 0
    target = initial_balance * 10

    for _ in range(n_sims):
        shuffled = trades.copy()
        random.shuffle(shuffled)

        balance = initial_balance
        peak = initial_balance
        max_dd = 0.0
        ruined = False

        for pnl in shuffled:
            balance += pnl
            if balance <= 0:
                balance = 0.0
                ruined = True
                max_dd = 1.0
                break
            if balance > peak:
                peak = balance
            dd = (peak - balance) / peak
            if dd > max_dd:
                max_dd = dd

        max_dds.append(max_dd)
        final_bals.append(balance)
        if ruined:
            ruin_count += 1
        if balance >= target:
            x10_count += 1

    # Compute statistics
    sorted_dds = sorted(max_dds)
    median_dd = statistics.median(sorted_dds)
    p95_idx = int(len(sorted_dds) * 0.95)
    p95_dd = sorted_dds[min(p95_idx, len(sorted_dds) - 1)]
    p_x10 = x10_count / n_sims
    p_ruin = ruin_count / n_sims

    return {
        "median_dd": round(median_dd, 4),
        "p95_dd": round(p95_dd, 4),
        "p_x10": round(p_x10, 4),
        "p_ruin": round(p_ruin, 4),
        "n_simulations": n_sims,
    }


class MonteCarlo(BaseAgent):
    """Runs Monte Carlo simulations on validated strategies to test robustness."""

    name = "monte_carlo"

    def __init__(self, db):
        super().__init__(agent_id="monte_carlo", db=db)
        self._bt_runner: Optional[BacktestRunner] = None

    # ──────────────────────────────────────────────
    # BaseAgent interface
    # ──────────────────────────────────────────────

    def setup(self):
        self._bt_runner = BacktestRunner(self.db)
        self._bt_runner.setup()
        self.logger.info("Monte Carlo agent ready")

    def tick(self):
        """Find validated strategies that haven't been MC-tested and process them."""
        strategies = self._get_untested_strategies()
        if not strategies:
            return

        for strategy in strategies:
            strategy_id = strategy["id"]
            try:
                self._run_mc_for_strategy(strategy_id)
            except Exception as exc:
                self.logger.error(
                    f"Monte Carlo failed for {strategy_id}: {exc}\n"
                    f"{traceback.format_exc()}"
                )

    def tick_interval(self) -> float:
        return self.get_config("tick_interval", 300)

    # ──────────────────────────────────────────────
    # Internals
    # ──────────────────────────────────────────────

    def _get_untested_strategies(self) -> list:
        """Return validated strategies that have not been Monte Carlo tested."""
        rows = self.db.fetchall(
            "SELECT id, best_config FROM strategies WHERE status = 'validated'"
        )
        untested = []
        for row in rows:
            config = {}
            if row["best_config"]:
                config = (
                    json.loads(row["best_config"])
                    if isinstance(row["best_config"], str)
                    else row["best_config"]
                )
            if not config.get("monte_carlo_tested"):
                untested.append(dict(row))
        return untested

    def _extract_trades_from_equity_curve(self, equity_curve: list) -> list:
        """
        Extract individual trade P&Ls from an equity curve.

        The equity curve records balance after every bar. Trades produce
        non-zero changes in balance; flat periods (no trade closing) show
        zero change. We extract only the non-zero deltas.
        """
        if not equity_curve or len(equity_curve) < 2:
            return []
        trades = []
        for i in range(1, len(equity_curve)):
            delta = equity_curve[i] - equity_curve[i - 1]
            if abs(delta) > 1e-10:
                trades.append(round(delta, 6))
        return trades

    def _run_mc_for_strategy(self, strategy_id: str):
        """Run a full backtest to capture trades, then run Monte Carlo."""
        self.logger.info(f"Running Monte Carlo analysis for {strategy_id}")

        # Re-run the backtest to capture the equity curve and extract trades
        metrics = self._bt_runner.run_single_backtest(strategy_id)
        if metrics is None:
            self.logger.warning(f"Could not run backtest for {strategy_id}, skipping MC")
            self._mark_tested(strategy_id, None)
            return

        equity_curve = metrics.get("equity_curve", [])
        trades = self._extract_trades_from_equity_curve(equity_curve)

        if len(trades) < 5:
            self.logger.warning(
                f"Strategy {strategy_id} has only {len(trades)} trades, "
                "too few for meaningful MC simulation"
            )
            self._mark_tested(strategy_id, None)
            return

        # Run Monte Carlo simulations
        n_sims = self.get_config("n_simulations", 10000)
        initial_balance = self.get_config("initial_balance", 50.0)
        mc_results = monte_carlo_trades(trades, n_sims=n_sims, initial_balance=initial_balance)

        # Store results in strategy's best_config
        self._store_mc_results(strategy_id, mc_results)

        # Check fragility thresholds
        is_fragile = mc_results["p95_dd"] > 0.50 or mc_results["p_ruin"] > 0.10
        if is_fragile:
            self.db.execute(
                "UPDATE strategies SET status = 'fragile' WHERE id = ?",
                (strategy_id,),
            )
            self.emit_event(
                "warning",
                f"Strategy {strategy_id} marked FRAGILE: "
                f"p95_dd={mc_results['p95_dd']:.2%}, p_ruin={mc_results['p_ruin']:.2%}",
                metadata={"strategy_id": strategy_id, "monte_carlo": mc_results},
            )
            self.logger.warning(f"Strategy {strategy_id} is FRAGILE")

        # Emit milestone with results summary
        self.emit_event(
            "milestone",
            f"Monte Carlo complete for {strategy_id}: "
            f"median_dd={mc_results['median_dd']:.2%}, "
            f"p95_dd={mc_results['p95_dd']:.2%}, "
            f"p_x10={mc_results['p_x10']:.2%}, "
            f"p_ruin={mc_results['p_ruin']:.2%} "
            f"({mc_results['n_simulations']} sims)",
            metadata={"strategy_id": strategy_id, "monte_carlo": mc_results},
        )
        self.logger.info(
            f"MC results for {strategy_id}: "
            f"median_dd={mc_results['median_dd']:.4f}, "
            f"p95_dd={mc_results['p95_dd']:.4f}, "
            f"p_x10={mc_results['p_x10']:.4f}, "
            f"p_ruin={mc_results['p_ruin']:.4f}"
        )

    def _store_mc_results(self, strategy_id: str, mc_results: dict):
        """Store Monte Carlo results in strategy's best_config JSON."""
        row = self.db.fetchone(
            "SELECT best_config FROM strategies WHERE id = ?", (strategy_id,)
        )
        config = {}
        if row and row["best_config"]:
            config = (
                json.loads(row["best_config"])
                if isinstance(row["best_config"], str)
                else row["best_config"]
            )
        config["monte_carlo"] = mc_results
        config["monte_carlo_tested"] = True
        self.db.execute(
            "UPDATE strategies SET best_config = ? WHERE id = ?",
            (json.dumps(config), strategy_id),
        )

    def _mark_tested(self, strategy_id: str, mc_results: Optional[dict]):
        """Mark a strategy as MC-tested even if no results (e.g. too few trades)."""
        row = self.db.fetchone(
            "SELECT best_config FROM strategies WHERE id = ?", (strategy_id,)
        )
        config = {}
        if row and row["best_config"]:
            config = (
                json.loads(row["best_config"])
                if isinstance(row["best_config"], str)
                else row["best_config"]
            )
        config["monte_carlo_tested"] = True
        if mc_results is not None:
            config["monte_carlo"] = mc_results
        self.db.execute(
            "UPDATE strategies SET best_config = ? WHERE id = ?",
            (json.dumps(config), strategy_id),
        )
