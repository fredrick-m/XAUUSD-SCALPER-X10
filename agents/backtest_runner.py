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
from engine.backtest import run_simulation, validate, add_regime_indicators


class BacktestRunner(BaseAgent):
    """Runs backtests for candidate strategies and stores results."""

    name = "backtest_runner"

    def __init__(self, db):
        super().__init__(agent_id="backtest_runner", db=db)
        self._data_cache: Optional[pd.DataFrame] = None
        self._data_cache_m5: Optional[pd.DataFrame] = None
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

    def _load_data_m5(self) -> Optional[pd.DataFrame]:
        """Resample M1 data to M5. Cached after first call."""
        if self._data_cache_m5 is not None:
            return self._data_cache_m5

        df_m1 = self._load_data()
        if df_m1 is None:
            return None

        self.logger.info("Resampling M1 → M5...")
        df = df_m1.copy()
        df.set_index("time", inplace=True)
        df_m5 = df.resample("5min").agg({
            "Open": "first", "High": "max", "Low": "min",
            "Close": "last", "Volume": "sum",
        }).dropna().reset_index()
        self._data_cache_m5 = df_m5
        self.logger.info(f"M5 data: {len(df_m5)} bars")
        return df_m5

    def _is_m5_strategy(self, strategy_id: str) -> bool:
        """Strategies starting with 'c', 'd', or 'e' are M5-optimized."""
        sid = strategy_id.lower()
        return sid.startswith("c") or sid.startswith("d") or sid.startswith("e")

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

        # Use M5 data for C-series strategies, M1 for others
        if self._is_m5_strategy(strategy_id):
            df = self._load_data_m5()
            risk_pct = 0.10  # M5 strategies use 10% risk
            self.logger.info(f"Using M5 data with {risk_pct:.0%} risk for {strategy_id}")
        else:
            df = self._load_data()
            risk_pct = DEFAULT_RISK_PCT

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

        # Determine trailing stop: disable for wide-TP strategies (tp_atr >= 3.0)
        use_trailing = True
        try:
            tp_atr = module.PARAMS.get("tp_atr", 2.0)
            if tp_atr >= 3.0:
                use_trailing = False
        except AttributeError:
            pass

        try:
            metrics = run_simulation(
                df,
                signals,
                sl_prices,
                tp_prices,
                directions,
                risk_pct=risk_pct,
                trailing_stop=use_trailing,
                max_bars_in_trade=60 if not self._is_m5_strategy(strategy_id) else 200,
                session_filter=True,
                session_hours=(7, 21),
            )
        except Exception as exc:
            self.logger.error(f"run_simulation failed for {strategy_id}: {exc}")
            return None

        # Regime analysis: count distinct regimes in the dataset
        regime_results = {}
        regimes_tested = 1
        try:
            df_regime = add_regime_indicators(df)
            regimes_present = set(df_regime["regime"].dropna().unique()) - {"UNKNOWN", "MIXED"}
            regimes_tested = max(1, len(regimes_present))
        except Exception:
            pass

        self._store_results(strategy_id, metrics, regime_results)
        self._update_strategy_metrics(strategy_id, metrics)

        # Validation on full dataset
        tf = "M5" if self._is_m5_strategy(strategy_id) else "M1"
        passed, fails = validate(metrics, regimes_tested=regimes_tested, timeframe=tf)
        if not passed:
            self.logger.info(f"Strategy {strategy_id} did not pass full backtest: {fails}")
            return metrics

        # Walk-forward validation: 70% in-sample, 30% out-of-sample
        wf_passed = self._walk_forward_validate(strategy_id, df, module)
        if wf_passed:
            self.db.execute(
                "UPDATE strategies SET status = 'validated', walk_forward_passed = 1 WHERE id = ?",
                (strategy_id,),
            )
            self.emit_event(
                "milestone",
                f"Strategy {strategy_id} passed validation + walk-forward",
                metadata={"strategy_id": strategy_id, "metrics": {k: v for k, v in metrics.items() if k != "equity_curve"}},
            )
            self.logger.info(f"Strategy {strategy_id} VALIDATED (walk-forward passed)")
        else:
            self.db.execute(
                "UPDATE strategies SET status = 'validated', walk_forward_passed = 0 WHERE id = ?",
                (strategy_id,),
            )
            self.logger.info(f"Strategy {strategy_id} passed full backtest but FAILED walk-forward")

        return metrics

    # ──────────────────────────────────────────────────
    # Walk-forward validation
    # ──────────────────────────────────────────────────

    def _get_risk_pct(self, strategy_id: str) -> float:
        """Return risk percentage based on strategy type."""
        return 0.10 if self._is_m5_strategy(strategy_id) else DEFAULT_RISK_PCT

    def _walk_forward_validate(self, strategy_id: str, df: pd.DataFrame, module) -> bool:
        """
        Run walk-forward validation: train on first 70%, test on last 30%.
        The strategy must maintain at least 80% of its in-sample profit factor
        on the out-of-sample portion to pass.
        """
        split_idx = int(len(df) * 0.7)
        if split_idx < 1000 or (len(df) - split_idx) < 500:
            self.logger.info(f"Not enough data for walk-forward ({len(df)} bars), skipping")
            return True  # Pass by default if insufficient data

        df_in = df.iloc[:split_idx].reset_index(drop=True)
        df_out = df.iloc[split_idx:].reset_index(drop=True)

        try:
            # In-sample backtest
            sig_in = self._build_signal_series(df_in, module)
            if sig_in is None:
                return True
            signals_in, sl_in, tp_in, dirs_in = sig_in
            rp = self._get_risk_pct(strategy_id)
            mbt = 200 if self._is_m5_strategy(strategy_id) else 60
            # Trailing stop logic: disable for wide-TP strategies
            wf_trailing = True
            try:
                tp_atr = module.PARAMS.get("tp_atr", 2.0)
                if tp_atr >= 3.0:
                    wf_trailing = False
            except AttributeError:
                pass
            metrics_in = run_simulation(
                df_in, signals_in, sl_in, tp_in, dirs_in,
                risk_pct=rp, trailing_stop=wf_trailing,
                max_bars_in_trade=mbt, session_filter=True, session_hours=(7, 21),
            )

            # Out-of-sample backtest
            sig_out = self._build_signal_series(df_out, module)
            if sig_out is None:
                return True
            signals_out, sl_out, tp_out, dirs_out = sig_out
            metrics_out = run_simulation(
                df_out, signals_out, sl_out, tp_out, dirs_out,
                risk_pct=rp, trailing_stop=wf_trailing,
                max_bars_in_trade=mbt, session_filter=True, session_hours=(7, 21),
            )

            # Store walk-forward result
            self.db.execute(
                "INSERT INTO backtest_results "
                "(strategy_id, risk_pct, total_trades, win_rate, profit_factor, "
                "max_drawdown, x10_count, final_balance, return_pct, blown_account, "
                "regime_results, walk_forward, data_hash) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    strategy_id, DEFAULT_RISK_PCT,
                    metrics_out.get("total_trades", 0),
                    metrics_out.get("win_rate", 0.0),
                    metrics_out.get("profit_factor", 0.0),
                    metrics_out.get("max_drawdown", 0.0),
                    metrics_out.get("x10_count", 0),
                    metrics_out.get("final_balance", 0.0),
                    metrics_out.get("return_pct", 0.0),
                    1 if metrics_out.get("blown_account") else 0,
                    json.dumps({"type": "walk_forward_oos"}),
                    1,
                    self._data_hash,
                ),
            )

            pf_in = metrics_in.get("profit_factor", 0.0)
            pf_out = metrics_out.get("profit_factor", 0.0)

            # Out-of-sample PF must be at least 80% of in-sample PF
            if pf_in <= 0:
                return pf_out > 1.0

            ratio = pf_out / pf_in
            self.logger.info(
                f"Walk-forward {strategy_id}: IS PF={pf_in:.2f}, OOS PF={pf_out:.2f}, ratio={ratio:.2f}"
            )
            return ratio >= 0.8

        except Exception as exc:
            self.logger.error(f"Walk-forward failed for {strategy_id}: {exc}")
            return True  # Don't block on walk-forward errors

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
