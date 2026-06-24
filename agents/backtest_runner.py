"""Backtest Runner agent: processes backtest tasks from the queue and runs strategy simulations."""
import hashlib
import importlib.util
import json
import traceback
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from agents.base_agent import BaseAgent
from core.config import DATA_DIR, STRATEGIES_DIR, DEFAULT_RISK_PCT
from engine.backtest import run_simulation, validate


class BacktestRunner(BaseAgent):
    """Runs backtests for candidate strategies and stores results."""

    name = "backtest_runner"

    def __init__(self, db):
        super().__init__(agent_id="backtest_runner", db=db)
        self._data_cache: Optional[pd.DataFrame] = None
        self._data_hash: Optional[str] = None

    # ──────────────────────────────────────────────────
    # BaseAgent interface
    # ──────────────────────────────────────────────────

    def setup(self):
        self.logger.info("Backtest Runner ready")

    def tick(self):
        """Process pending backtest tasks, then scan for untested candidates."""
        self._process_task_queue()
        self._process_untested_candidates()

    def tick_interval(self) -> float:
        return self.get_config("tick_interval", 60)

    # ──────────────────────────────────────────────────
    # Task queue processing
    # ──────────────────────────────────────────────────

    def _process_task_queue(self):
        tasks = self.get_pending_tasks()
        for task in tasks:
            task_id = task["id"]
            task_type = task.get("task_type", "")
            if task_type != "backtest":
                continue
            try:
                payload = json.loads(task["payload"]) if isinstance(task["payload"], str) else task["payload"]
                strategy_id = payload.get("strategy_id")
                if not strategy_id:
                    self.fail_task(task_id, "Missing strategy_id in payload")
                    continue
                result = self.run_single_backtest(strategy_id)
                self.complete_task(task_id, result or {})
            except Exception as exc:
                self.logger.error(f"Task {task_id} failed: {exc}")
                self.fail_task(task_id, traceback.format_exc())

    def _process_untested_candidates(self):
        """Find candidate strategies with no backtest_results and run them."""
        rows = self.db.fetchall(
            "SELECT s.id FROM strategies s "
            "LEFT JOIN backtest_results b ON s.id = b.strategy_id "
            "WHERE s.status = 'candidate' AND b.id IS NULL",
        )
        for row in rows:
            strategy_id = row["id"]
            try:
                self.run_single_backtest(strategy_id)
            except Exception as exc:
                self.logger.error(f"Auto-backtest for {strategy_id} failed: {exc}")

    # ──────────────────────────────────────────────────
    # Data loading
    # ──────────────────────────────────────────────────

    def _load_data(self) -> Optional[pd.DataFrame]:
        """Load XAUUSD M1 data, using the largest CSV in data/raw. Results are cached."""
        if self._data_cache is not None:
            return self._data_cache

        raw_dir = DATA_DIR / "raw"
        candidates = sorted(raw_dir.glob("XAUUSD_M1*.csv"), key=lambda p: p.stat().st_size, reverse=True)
        if not candidates:
            self.logger.warning("No XAUUSD_M1*.csv found in data/raw/")
            return None

        csv_path = candidates[0]
        self.logger.info(f"Loading data from {csv_path}")
        df = pd.read_csv(csv_path, parse_dates=["time"])

        # Normalise column names to capitalised form
        rename_map = {
            "open": "Open", "high": "High", "low": "Low",
            "close": "Close", "tick_volume": "Volume", "volume": "Volume",
        }
        df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})
        df = df.sort_values("time").reset_index(drop=True)

        # Compute a hash of the file for record-keeping
        h = hashlib.md5(csv_path.read_bytes()).hexdigest()
        self._data_hash = h
        self._data_cache = df
        return df

    # ──────────────────────────────────────────────────
    # Strategy loading
    # ──────────────────────────────────────────────────

    def _load_strategy_module(self, strategy_id: str):
        """Dynamically load a strategy module. Returns the module or None."""
        # First try the path stored in the DB
        row = self.db.fetchone("SELECT file_path FROM strategies WHERE id = ?", (strategy_id,))
        candidate_paths = []

        if row and row["file_path"]:
            db_path = Path(row["file_path"])
            # Try absolute, then relative to project root
            candidate_paths.append(db_path)
            candidate_paths.append(DATA_DIR.parent / db_path)

        # Fallback: STRATEGIES_DIR / strategy_{id.lower()}.py
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
    # Signal generation helpers
    # ──────────────────────────────────────────────────

    def _build_signal_series(self, df: pd.DataFrame, module) -> tuple:
        """
        Call module.generate_signals(df, module.PARAMS) and extract signal,
        SL and TP price series from ATR and sl_atr/tp_atr params.

        Returns (signals, sl_prices, tp_prices, directions) or None on failure.
        """
        params = getattr(module, "PARAMS", {})
        sl_atr = params.get("sl_atr", 1.5)
        tp_atr = params.get("tp_atr", 2.5)

        result_df = module.generate_signals(df.copy(), params)

        if "signal" not in result_df.columns:
            self.logger.error("generate_signals did not return a 'signal' column")
            return None

        if "ATR" not in result_df.columns:
            self.logger.error("generate_signals did not compute an 'ATR' column")
            return None

        signals = result_df["signal"]
        atr = result_df["ATR"]
        close = result_df["Close"]

        sl_prices = pd.Series(np.nan, index=df.index)
        tp_prices = pd.Series(np.nan, index=df.index)
        directions = pd.Series(0, index=df.index)

        long_mask = signals == 1
        short_mask = signals == -1

        sl_prices[long_mask]  = close[long_mask]  - sl_atr * atr[long_mask]
        tp_prices[long_mask]  = close[long_mask]  + tp_atr * atr[long_mask]
        sl_prices[short_mask] = close[short_mask] + sl_atr * atr[short_mask]
        tp_prices[short_mask] = close[short_mask] - tp_atr * atr[short_mask]
        directions[long_mask]  =  1
        directions[short_mask] = -1

        return signals, sl_prices, tp_prices, directions

    # ──────────────────────────────────────────────────
    # Core backtest entry point
    # ──────────────────────────────────────────────────

    def run_single_backtest(self, strategy_id: str) -> Optional[dict]:
        """
        Run a full backtest for strategy_id.

        Returns the metrics dict on success, None on hard failure.
        """
        self.logger.info(f"Running backtest for strategy {strategy_id}")

        df = self._load_data()
        if df is None:
            self.logger.warning(f"No data available — skipping backtest for {strategy_id}")
            return None

        module = self._load_strategy_module(strategy_id)
        if module is None:
            self.logger.warning(f"Could not load strategy module for {strategy_id}")
            return None

        signal_data = self._build_signal_series(df, module)
        if signal_data is None:
            return None

        signals, sl_prices, tp_prices, directions = signal_data

        try:
            metrics = run_simulation(
                df,
                signals,
                sl_prices,
                tp_prices,
                directions,
                risk_pct=DEFAULT_RISK_PCT,
                trailing_stop=True,
                max_bars_in_trade=60,
                session_filter=True,
                session_hours=(7, 21),
            )
        except Exception as exc:
            self.logger.error(f"run_simulation failed for {strategy_id}: {exc}")
            return None

        # Count how many distinct regimes were observed if ATR/regime not already computed
        regime_results = {}
        regimes_tested = 1  # at minimum we tested the full dataset as one regime

        self._store_results(strategy_id, metrics, regime_results)
        self._update_strategy_metrics(strategy_id, metrics)

        # Validation
        passed, fails = validate(metrics, regimes_tested=regimes_tested)
        if passed:
            self.db.execute(
                "UPDATE strategies SET status = 'validated' WHERE id = ?",
                (strategy_id,),
            )
            self.emit_event(
                "milestone",
                f"Strategy {strategy_id} passed validation",
                metadata={"strategy_id": strategy_id, "metrics": {k: v for k, v in metrics.items() if k != "equity_curve"}},
            )
            self.logger.info(f"Strategy {strategy_id} VALIDATED")
        else:
            self.logger.info(f"Strategy {strategy_id} did not pass: {fails}")

        return metrics

    # ──────────────────────────────────────────────────
    # Result persistence
    # ──────────────────────────────────────────────────

    def _store_results(self, strategy_id: str, metrics: dict, regime_results: dict):
        """Insert a new row into backtest_results."""
        self.db.execute(
            "INSERT INTO backtest_results "
            "(strategy_id, risk_pct, config, total_trades, win_rate, profit_factor, "
            "max_drawdown, x10_count, final_balance, return_pct, blown_account, "
            "regime_results, walk_forward, data_hash) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                strategy_id,
                DEFAULT_RISK_PCT,
                None,
                metrics.get("total_trades", 0),
                metrics.get("win_rate", 0.0),
                metrics.get("profit_factor", 0.0),
                metrics.get("max_drawdown", 0.0),
                metrics.get("x10_count", 0),
                metrics.get("final_balance", 0.0),
                metrics.get("return_pct", 0.0),
                1 if metrics.get("blown_account") else 0,
                json.dumps(regime_results),
                0,
                self._data_hash,
            ),
        )

    def _update_strategy_metrics(self, strategy_id: str, metrics: dict):
        """Update strategies table best metrics if this run improved them."""
        row = self.db.fetchone(
            "SELECT best_win_rate, best_profit_factor, best_max_drawdown, "
            "best_x10_count, best_final_balance FROM strategies WHERE id = ?",
            (strategy_id,),
        )
        if row is None:
            return

        current_pf = row["best_profit_factor"] or 0.0
        new_pf = metrics.get("profit_factor", 0.0)

        # Use profit factor as the primary improvement indicator
        if new_pf > current_pf:
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
                    None,
                    strategy_id,
                ),
            )
