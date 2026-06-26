"""Parameter Optimizer agent: grid-searches SL/TP parameters for strategies with good signals but poor PF."""
import importlib.util
import json
import time
import traceback
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from agents.base_agent import BaseAgent
from core.config import DATA_DIR, STRATEGIES_DIR, DEFAULT_RISK_PCT


class ParamOptimizer(BaseAgent):
    """Automated grid-search of SL/TP parameters for candidate strategies with subpar profit factor."""

    name = "param_optimizer"

    # ── Grid search parameter space ──────────────────
    SL_ATR_GRID = [1.5, 2.0, 2.5, 3.0, 3.5, 4.0]
    TP_ATR_GRID = [1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0, 6.0]
    TRAILING_GRID = [True, False]

    # ── Grid search result filters ───────────────────
    MIN_WIN_RATE_GRID = 0.50
    MIN_TRADES_GRID = 100

    # ── Validation thresholds (promotion to validated) ─
    VALIDATE_WIN_RATE = 0.62
    VALIDATE_PF = 2.0
    VALIDATE_MAX_DD = 0.35
    VALIDATE_X10 = 5
    VALIDATE_TRADES = 200

    def __init__(self, db):
        super().__init__(agent_id="param_optimizer", db=db)
        self._data_cache: Optional[pd.DataFrame] = None
        self._data_cache_m5: Optional[pd.DataFrame] = None

    # ──────────────────────────────────────────────────
    # BaseAgent interface
    # ──────────────────────────────────────────────────

    def setup(self):
        self.logger.info("ParamOptimizer ready")

    def tick(self):
        strategy = self._find_optimization_candidate()
        if strategy is None:
            return
        strategy_id = strategy["id"]
        self.logger.info(f"Starting grid-search optimization for {strategy_id}")
        try:
            self._optimize_strategy(strategy_id)
        except Exception as exc:
            self.logger.error(f"Optimization failed for {strategy_id}: {exc}\n{traceback.format_exc()}")
            self.emit_event("error", f"ParamOptimizer failed for {strategy_id}: {exc}")

    def tick_interval(self) -> float:
        return self.get_config("tick_interval", 60)

    # ──────────────────────────────────────────────────
    # Candidate selection
    # ──────────────────────────────────────────────────

    def _find_optimization_candidate(self) -> Optional[dict]:
        """
        Find a candidate strategy that has been backtested but has PF < 2.0
        and has not already been optimized by this agent.
        Returns at most one strategy dict per tick to conserve CPU.
        """
        already_optimized = self.get_config("optimized_strategies", [])

        # Find candidates with existing backtest results where best PF < 2.0
        rows = self.db.fetchall(
            "SELECT s.id, s.file_path, s.best_profit_factor "
            "FROM strategies s "
            "INNER JOIN backtest_results b ON s.id = b.strategy_id "
            "WHERE s.status = 'candidate' "
            "  AND s.best_profit_factor IS NOT NULL "
            "  AND s.best_profit_factor < 2.0 "
            "GROUP BY s.id "
            "ORDER BY s.best_profit_factor DESC "
            "LIMIT 10",
        )

        for row in rows:
            if row["id"] not in already_optimized:
                return dict(row)
        return None

    # ──────────────────────────────────────────────────
    # Data loading (cached)
    # ──────────────────────────────────────────────────

    def _load_data(self) -> Optional[pd.DataFrame]:
        """Load XAUUSD M1 data from data/raw, caching in memory."""
        if self._data_cache is not None:
            return self._data_cache

        raw_dir = DATA_DIR / "raw"
        candidates = sorted(raw_dir.glob("XAUUSD_M1*.csv"), key=lambda p: p.stat().st_size, reverse=True)
        if not candidates:
            self.logger.warning("No XAUUSD_M1*.csv found in data/raw/")
            return None

        csv_path = candidates[0]
        self.logger.info(f"Loading data from {csv_path} (this may take a moment)")
        df = pd.read_csv(csv_path, parse_dates=["time"])

        rename_map = {
            "open": "Open", "high": "High", "low": "Low",
            "close": "Close", "tick_volume": "Volume", "volume": "Volume",
        }
        df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})
        df = df.sort_values("time").reset_index(drop=True)

        self._data_cache = df
        self.logger.info(f"Data loaded: {len(df)} bars")
        return df

    def _load_data_m5(self) -> Optional[pd.DataFrame]:
        """Resample M1 to M5 for C/D-series strategies. Cached."""
        if self._data_cache_m5 is not None:
            return self._data_cache_m5
        df_m1 = self._load_data()
        if df_m1 is None:
            return None
        self.logger.info("Resampling M1 → M5 for optimizer...")
        df = df_m1.copy()
        df.set_index("time", inplace=True)
        df_m5 = df.resample("5min").agg({
            "Open": "first", "High": "max", "Low": "min",
            "Close": "last", "Volume": "sum",
        }).dropna().reset_index()
        self._data_cache_m5 = df_m5
        self.logger.info(f"M5 data: {len(df_m5)} bars")
        return df_m5

    @staticmethod
    def _is_m5_strategy(strategy_id: str) -> bool:
        sid = strategy_id.lower()
        return sid.startswith("c") or sid.startswith("d")

    # ──────────────────────────────────────────────────
    # Strategy module loading
    # ──────────────────────────────────────────────────

    def _load_strategy_module(self, strategy_id: str):
        """Dynamically load a strategy module. Returns the module or None."""
        row = self.db.fetchone("SELECT file_path FROM strategies WHERE id = ?", (strategy_id,))
        candidate_paths = []

        if row and row["file_path"]:
            db_path = Path(row["file_path"])
            candidate_paths.append(db_path)
            candidate_paths.append(DATA_DIR.parent / db_path)

        candidate_paths.append(STRATEGIES_DIR / f"strategy_{strategy_id.lower()}.py")

        module_path = None
        for p in candidate_paths:
            if p.exists():
                module_path = p
                break

        if module_path is None:
            self.logger.warning(f"Strategy file not found for {strategy_id}; tried {candidate_paths}")
            return None

        try:
            spec = importlib.util.spec_from_file_location(
                f"strategy_{strategy_id.lower()}", str(module_path)
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
        except Exception as exc:
            self.logger.error(f"Failed to load strategy module {module_path}: {exc}")
            return None

    # ──────────────────────────────────────────────────
    # Core optimization
    # ──────────────────────────────────────────────────

    def _optimize_strategy(self, strategy_id: str):
        """Run a full grid-search of SL/TP/trailing params for one strategy."""
        from engine.backtest import run_simulation

        if self._is_m5_strategy(strategy_id):
            df = self._load_data_m5()
            risk_pct = 0.10
        else:
            df = self._load_data()
            risk_pct = DEFAULT_RISK_PCT

        if df is None:
            self.logger.warning(f"No data available -- skipping optimization for {strategy_id}")
            return

        module = self._load_strategy_module(strategy_id)
        if module is None:
            self.logger.warning(f"Could not load strategy module for {strategy_id}")
            return

        # Generate signals once (expensive)
        params = getattr(module, "PARAMS", {})
        self.logger.info(f"Generating signals for {strategy_id}...")
        t0 = time.time()
        try:
            result_df = module.generate_signals(df.copy(), params)
        except Exception as exc:
            self.logger.error(f"Signal generation failed for {strategy_id}: {exc}")
            return
        signal_time = time.time() - t0
        self.logger.info(f"Signal generation took {signal_time:.1f}s")

        if "signal" not in result_df.columns or "ATR" not in result_df.columns:
            self.logger.error(f"Strategy {strategy_id} missing 'signal' or 'ATR' column")
            return

        signals = result_df["signal"]
        atr = result_df["ATR"]
        close = result_df["Close"]

        # Pre-compute masks once
        long_mask = signals == 1
        short_mask = signals == -1

        total_combos = len(self.SL_ATR_GRID) * len(self.TP_ATR_GRID) * len(self.TRAILING_GRID)
        self.logger.info(f"Starting grid search: {total_combos} combinations")

        best_result = None
        best_pf = 0.0
        best_params = {}
        tested = 0

        for sl_atr in self.SL_ATR_GRID:
            for tp_atr in self.TP_ATR_GRID:
                # Build SL/TP price series for this SL/TP ATR combo (reuse across trailing variants)
                sl_prices = pd.Series(np.nan, index=df.index)
                tp_prices = pd.Series(np.nan, index=df.index)
                directions = pd.Series(0, index=df.index)

                sl_prices[long_mask] = close[long_mask] - sl_atr * atr[long_mask]
                tp_prices[long_mask] = close[long_mask] + tp_atr * atr[long_mask]
                sl_prices[short_mask] = close[short_mask] + sl_atr * atr[short_mask]
                tp_prices[short_mask] = close[short_mask] - tp_atr * atr[short_mask]
                directions[long_mask] = 1
                directions[short_mask] = -1

                for trailing in self.TRAILING_GRID:
                    tested += 1
                    try:
                        metrics = run_simulation(
                            df,
                            signals,
                            sl_prices,
                            tp_prices,
                            directions,
                            risk_pct=risk_pct,
                            trailing_stop=trailing,
                            session_filter=True,
                            session_hours=(7, 21),
                        )
                    except Exception as exc:
                        self.logger.warning(
                            f"  [{tested}/{total_combos}] sl={sl_atr} tp={tp_atr} trail={trailing} FAILED: {exc}"
                        )
                        continue

                    wr = metrics.get("win_rate", 0.0)
                    pf = metrics.get("profit_factor", 0.0)
                    trades = metrics.get("total_trades", 0)

                    # Filter: must have minimum quality to be considered
                    if wr < self.MIN_WIN_RATE_GRID or trades < self.MIN_TRADES_GRID:
                        continue

                    if pf > best_pf:
                        best_pf = pf
                        best_result = metrics
                        best_params = {
                            "sl_atr": sl_atr,
                            "tp_atr": tp_atr,
                            "trailing_stop": trailing,
                        }

                    if tested % 12 == 0:
                        self.logger.info(
                            f"  [{tested}/{total_combos}] current best PF={best_pf:.2f} "
                            f"(sl={best_params.get('sl_atr', '-')} tp={best_params.get('tp_atr', '-')} "
                            f"trail={best_params.get('trailing_stop', '-')})"
                        )

        self.logger.info(
            f"Grid search complete for {strategy_id}: {tested}/{total_combos} combos tested"
        )

        # Mark strategy as optimized regardless of outcome
        self._mark_optimized(strategy_id)

        if best_result is None:
            self.logger.info(f"No valid parameter combination found for {strategy_id}")
            self.emit_event(
                "info",
                f"ParamOptimizer: no viable params found for {strategy_id}",
                metadata={"strategy_id": strategy_id},
            )
            return

        # Check if we improved over current best
        current_row = self.db.fetchone(
            "SELECT best_profit_factor FROM strategies WHERE id = ?", (strategy_id,)
        )
        current_pf = (current_row["best_profit_factor"] or 0.0) if current_row else 0.0

        self.logger.info(
            f"Best params for {strategy_id}: {best_params} -> "
            f"PF={best_pf:.2f} WR={best_result['win_rate']:.2%} "
            f"DD={best_result['max_drawdown']:.2%} x10={best_result['x10_count']} "
            f"trades={best_result['total_trades']} "
            f"(was PF={current_pf:.2f})"
        )

        if best_pf > current_pf:
            self._update_strategy(strategy_id, best_result, best_params)
        else:
            self.logger.info(f"No improvement for {strategy_id} (current PF={current_pf:.2f} >= best grid PF={best_pf:.2f})")

    # ──────────────────────────────────────────────────
    # Result persistence
    # ──────────────────────────────────────────────────

    def _update_strategy(self, strategy_id: str, metrics: dict, best_params: dict):
        """Update strategy with optimized params and check for promotion to validated."""
        config_json = json.dumps(best_params)

        self.db.execute(
            "UPDATE strategies SET "
            "best_win_rate = ?, best_profit_factor = ?, best_max_drawdown = ?, "
            "best_x10_count = ?, best_final_balance = ?, best_config = ? "
            "WHERE id = ?",
            (
                metrics.get("win_rate"),
                metrics.get("profit_factor"),
                metrics.get("max_drawdown"),
                metrics.get("x10_count"),
                metrics.get("final_balance"),
                config_json,
                strategy_id,
            ),
        )

        # Store a backtest_results row for the optimized run
        self.db.execute(
            "INSERT INTO backtest_results "
            "(strategy_id, risk_pct, config, total_trades, win_rate, profit_factor, "
            "max_drawdown, x10_count, final_balance, return_pct, blown_account, "
            "regime_results, walk_forward) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                strategy_id,
                DEFAULT_RISK_PCT,
                config_json,
                metrics.get("total_trades", 0),
                metrics.get("win_rate", 0.0),
                metrics.get("profit_factor", 0.0),
                metrics.get("max_drawdown", 0.0),
                metrics.get("x10_count", 0),
                metrics.get("final_balance", 0.0),
                metrics.get("return_pct", 0.0),
                1 if metrics.get("blown_account") else 0,
                json.dumps({"source": "param_optimizer", "params": best_params}),
                0,
            ),
        )

        # Check if strategy qualifies for promotion to validated
        wr = metrics.get("win_rate", 0.0)
        pf = metrics.get("profit_factor", 0.0)
        dd = metrics.get("max_drawdown", 1.0)
        x10 = metrics.get("x10_count", 0)
        trades = metrics.get("total_trades", 0)

        if (
            wr > self.VALIDATE_WIN_RATE
            and pf > self.VALIDATE_PF
            and dd < self.VALIDATE_MAX_DD
            and x10 >= self.VALIDATE_X10
            and trades >= self.VALIDATE_TRADES
        ):
            self.db.execute(
                "UPDATE strategies SET status = 'validated' WHERE id = ?",
                (strategy_id,),
            )
            self.logger.info(f"Strategy {strategy_id} PROMOTED to validated after optimization")
            self.emit_event(
                "milestone",
                f"ParamOptimizer: {strategy_id} promoted to validated "
                f"(PF={pf:.2f} WR={wr:.2%} DD={dd:.2%} x10={x10})",
                metadata={
                    "strategy_id": strategy_id,
                    "best_params": best_params,
                    "metrics": {k: v for k, v in metrics.items() if k != "equity_curve"},
                },
            )
        else:
            self.emit_event(
                "info",
                f"ParamOptimizer: {strategy_id} improved PF={pf:.2f} WR={wr:.2%} "
                f"(not yet validated)",
                metadata={
                    "strategy_id": strategy_id,
                    "best_params": best_params,
                    "profit_factor": pf,
                    "win_rate": wr,
                },
            )

    # ──────────────────────────────────────────────────
    # Optimization tracking
    # ──────────────────────────────────────────────────

    def _mark_optimized(self, strategy_id: str):
        """Record that a strategy has been grid-searched to avoid re-processing."""
        already = self.get_config("optimized_strategies", [])
        if strategy_id not in already:
            already.append(strategy_id)
            self.set_config("optimized_strategies", already)
