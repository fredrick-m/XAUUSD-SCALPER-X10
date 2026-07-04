"""Backtest Runner agent: processes backtest tasks from the queue and runs strategy simulations.

Uses multiprocessing to run backtests in parallel across CPU cores.
"""
import hashlib
import importlib.util
import json
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from agents.base_agent import BaseAgent
from core.config import (
    DATA_DIR, STRATEGIES_DIR, DEFAULT_RISK_PCT,
    HOLDOUT_MONTHS, HOLDOUT_MIN_PF, HOLDOUT_MIN_TRADES,
    PROBATION_MIN_TRADES, PROBATION_MIN_PF, PROBATION_MAX_DD,
    PROBATION_MIN_WR_LB, PROBATION_HOLDOUT_MIN_TRADES, PROBATION_HOLDOUT_MIN_PF,
)
from engine.backtest import run_simulation, validate, add_regime_indicators


def _probation_ok(metrics: dict) -> bool:
    """Small sample, exceptional quality: stricter bars compensate low n.

    The 95% lower confidence bound on the win rate must still beat 50%,
    so the required WR rises automatically as the sample shrinks.
    """
    import math as _math

    n = metrics.get("total_trades", 0)
    wr = metrics.get("win_rate", 0.0)
    pf = metrics.get("profit_factor", 0.0)
    dd = metrics.get("max_drawdown", 1.0)

    if n < PROBATION_MIN_TRADES:
        return False
    if pf < PROBATION_MIN_PF or dd > PROBATION_MAX_DD:
        return False
    wr_lb = wr - 1.96 * _math.sqrt(max(wr * (1 - wr), 1e-9) / n)
    return wr_lb >= PROBATION_MIN_WR_LB


# ══════════════════════════════════════════════
# Standalone worker function (runs in subprocess)
# ══════════════════════════════════════════════

def _backtest_worker(strategy_id: str, file_path: str, df_m5_bytes: bytes, data_hash: str) -> dict:
    """Run a single backtest in an isolated process.

    Returns a result dict with status and metrics/reason.
    """
    import pickle
    df = pickle.loads(df_m5_bytes)

    # Load strategy module
    p = Path(file_path)
    if not p.exists():
        return {"strategy_id": strategy_id, "status": "rejected", "reason": "file_missing"}

    try:
        spec = importlib.util.spec_from_file_location(f"strategy_{strategy_id.lower()}", str(p))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except Exception as exc:
        return {"strategy_id": strategy_id, "status": "rejected", "reason": f"load_failed: {exc}"}

    # Generate signals
    params = getattr(module, "PARAMS", {})
    sl_atr = params.get("sl_atr", 1.5)
    tp_atr_val = params.get("tp_atr", 2.5)

    try:
        result_df = module.generate_signals(df.copy(), params)
    except Exception as exc:
        return {"strategy_id": strategy_id, "status": "rejected", "reason": f"signal_gen_failed: {exc}"}

    if "signal" not in result_df.columns or "ATR" not in result_df.columns:
        return {"strategy_id": strategy_id, "status": "rejected", "reason": "signal_gen_failed"}

    signals = result_df["signal"]
    atr = result_df["ATR"]
    close = result_df["Close"]

    sl_prices = pd.Series(np.nan, index=df.index)
    tp_prices = pd.Series(np.nan, index=df.index)
    directions = pd.Series(0, index=df.index)

    long_mask = signals == 1
    short_mask = signals == -1
    sl_prices[long_mask] = close[long_mask] - sl_atr * atr[long_mask]
    tp_prices[long_mask] = close[long_mask] + tp_atr_val * atr[long_mask]
    sl_prices[short_mask] = close[short_mask] + sl_atr * atr[short_mask]
    tp_prices[short_mask] = close[short_mask] - tp_atr_val * atr[short_mask]
    directions[long_mask] = 1
    directions[short_mask] = -1

    # Trailing stop logic
    use_trailing = True
    try:
        if params.get("tp_atr", 2.0) >= 3.0:
            use_trailing = False
    except Exception:
        pass

    # Per-strategy trading session (new search dimension; defaults keep old
    # behaviour for strategies generated before sessions were parameterized)
    sess_start = int(params.get("session_start", 7))
    sess_end = int(params.get("session_end", 21))
    if not (0 <= sess_start < sess_end <= 24):
        sess_start, sess_end = 7, 21

    def _sim(a: int, b: int) -> dict:
        """Run the simulator on bar range [a:b). Indicators/signals were
        computed once on the full series (they are causal), so slices keep
        their warm-up — no per-segment regeneration needed."""
        return run_simulation(
            df.iloc[a:b], signals.iloc[a:b], sl_prices.iloc[a:b],
            tp_prices.iloc[a:b], directions.iloc[a:b],
            risk_pct=DEFAULT_RISK_PCT, trailing_stop=use_trailing,
            max_bars_in_trade=200, session_filter=True,
            session_hours=(sess_start, sess_end),
        )

    # ── Final holdout split: the last HOLDOUT_MONTHS are NEVER used for
    # selection. Validation + walk-forward run on the selection window only;
    # the holdout is evaluated once, at the very end, as a deploy gate. ──
    times = pd.to_datetime(df["time"])
    holdout_start = times.iloc[-1] - pd.DateOffset(months=HOLDOUT_MONTHS)
    h_idx = int((times < holdout_start).sum())
    if h_idx < 5000 or (len(df) - h_idx) < 1000:
        h_idx = len(df)  # dataset too small to split — no holdout gate

    # Quick reject: signal count (on the selection window).
    # < 30 signals can NEVER produce the 30 trades even probation requires —
    # rejecting here skips 4 full simulations per hopeless strategy, which is
    # where most of the compute budget was being burned.
    signal_count = int((signals.iloc[:h_idx] != 0).sum())
    if signal_count < 30:
        return {"strategy_id": strategy_id, "status": "rejected",
                "reason": f"too_few_signals ({signal_count} < 30)",
                "signal_count": signal_count}
    if signal_count > 500:
        return {"strategy_id": strategy_id, "status": "rejected", "reason": "too_many_signals",
                "signal_count": signal_count}

    # Run simulation on the selection window
    try:
        metrics = _sim(0, h_idx)
    except Exception as exc:
        return {"strategy_id": strategy_id, "status": "error", "reason": f"simulation_failed: {exc}"}

    # Regime count (selection window)
    regimes_tested = 1
    try:
        df_regime = add_regime_indicators(df.iloc[:h_idx])
        regimes_present = set(df_regime["regime"].dropna().unique()) - {"UNKNOWN", "MIXED"}
        regimes_tested = max(1, len(regimes_present))
    except Exception:
        pass

    # Validate — with a probation path: if the ONLY failing criterion is the
    # trade count and the strategy shows exceptional quality (stricter PF/DD/
    # WR-lower-bound), it continues to WF + holdout and deploys at reduced size.
    probation = False
    passed, fails = validate(metrics, regimes_tested=regimes_tested, timeframe="M5")
    if not passed:
        only_trades_fail = all(f.startswith("trades") for f in fails)
        if only_trades_fail and _probation_ok(metrics):
            probation = True
        else:
            return {"strategy_id": strategy_id, "status": "failed_validation",
                    "metrics": metrics, "fails": fails, "data_hash": data_hash}

    # Walk-forward validation (70/30 split inside the selection window)
    split_idx = int(h_idx * 0.7)
    wf_passed = True
    if split_idx >= 1000 and (h_idx - split_idx) >= 500:
        try:
            metrics_in = _sim(0, split_idx)
            metrics_out = _sim(split_idx, h_idx)

            pf_in = metrics_in.get("profit_factor", 0.0)
            pf_out = metrics_out.get("profit_factor", 0.0)

            if pf_in > 0:
                wf_passed = (pf_out / pf_in) >= 0.8
            else:
                wf_passed = pf_out > 1.0

        except Exception:
            wf_passed = False  # A walk-forward that cannot run is a fail, not a pass

    # ── Holdout gate: only evaluated for strategies that already passed
    # validation + walk-forward, on data no selection step ever touched.
    # Probation strategies signal rarely, so the holdout naturally has few
    # trades: the bar is "enough activity and not losing" instead. ──
    holdout_passed = True
    holdout_clean = None
    if wf_passed and h_idx < len(df):
        min_h_trades = PROBATION_HOLDOUT_MIN_TRADES if probation else HOLDOUT_MIN_TRADES
        min_h_pf = PROBATION_HOLDOUT_MIN_PF if probation else HOLDOUT_MIN_PF
        try:
            hm = _sim(h_idx, len(df))
            holdout_passed = (
                hm.get("total_trades", 0) >= min_h_trades
                and hm.get("profit_factor", 0.0) >= min_h_pf
                and not hm.get("blown_account", False)
            )
            holdout_clean = {k: v for k, v in hm.items() if k != "equity_curve"}
        except Exception:
            holdout_passed = False

    # Strip equity_curve for serialization
    metrics_clean = {k: v for k, v in metrics.items() if k != "equity_curve"}

    return {
        "strategy_id": strategy_id,
        "status": "validated",
        # Deployable = walk-forward AND holdout survived
        "wf_passed": wf_passed and holdout_passed,
        "wf_only": wf_passed,
        "holdout_passed": holdout_passed,
        "holdout_metrics": holdout_clean,
        "probation": probation,
        "metrics": metrics,
        "metrics_clean": metrics_clean,
        "data_hash": data_hash,
        "regimes_tested": regimes_tested,
    }


class BacktestRunner(BaseAgent):
    """Runs backtests for candidate strategies using parallel processing."""

    name = "backtest_runner"

    def __init__(self, db):
        super().__init__(agent_id="backtest_runner", db=db)
        self._data_cache: Optional[pd.DataFrame] = None
        self._data_cache_m5: Optional[pd.DataFrame] = None
        self._data_hash: Optional[str] = None
        self._df_m5_pickle: Optional[bytes] = None  # Serialized M5 data for workers
        self._regime_cache: Optional[int] = None

    # ──────────────────────────────────────────────────
    # BaseAgent interface
    # ──────────────────────────────────────────────────

    def setup(self):
        self.logger.info("Backtest Runner ready (parallel mode, 3 workers)")

    def tick(self):
        """Process untested candidates in parallel, then limited task queue."""
        self._process_untested_parallel(batch_size=12)
        self._process_task_queue(max_per_tick=5)
        self._revalidate_deployed()

    def tick_interval(self) -> float:
        return self.get_config("tick_interval", 5)

    # ──────────────────────────────────────────────────
    # Task queue processing
    # ──────────────────────────────────────────────────

    def _process_task_queue(self, max_per_tick: int = 5):
        tasks = self.get_pending_tasks()
        processed = 0
        for task in tasks:
            if processed >= max_per_tick:
                break
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
                processed += 1
            except Exception as exc:
                self.logger.error(f"Task {task_id} failed: {exc}")
                self.fail_task(task_id, traceback.format_exc())
                processed += 1

    # ──────────────────────────────────────────────────
    # Parallel batch processing
    # ──────────────────────────────────────────────────

    def _process_untested_parallel(self, batch_size: int = 12):
        """Fetch a batch of untested candidates and backtest them in parallel."""
        # Ensure data is loaded
        df_m5 = self._load_data_m5()
        if df_m5 is None:
            return

        if self._df_m5_pickle is None:
            import pickle
            self._df_m5_pickle = pickle.dumps(df_m5)
            self.logger.info(f"M5 data serialized: {len(self._df_m5_pickle) / 1024 / 1024:.1f} MB")

        rows = self.db.fetchall(
            "SELECT s.id, s.file_path FROM strategies s "
            "LEFT JOIN backtest_results b ON s.id = b.strategy_id "
            "WHERE s.status = 'candidate' AND b.id IS NULL "
            "ORDER BY CASE WHEN s.id LIKE 'T%' THEN 0 "
            "              WHEN s.id LIKE 'G%' THEN 1 "
            "              ELSE 2 END, s.id DESC "
            f"LIMIT {batch_size}",
        )

        if not rows:
            return

        # Filter out missing files before submitting
        jobs = []
        for row in rows:
            fp = row["file_path"]
            if fp and not Path(fp).exists():
                self._mark_rejected(row["id"], "file_missing")
                continue
            jobs.append((row["id"], fp))

        if not jobs:
            return

        self.logger.info(f"Submitting {len(jobs)} backtests to parallel pool")

        # Use 3 workers (leave 1 core for main thread + other agents)
        results = []
        try:
            with ProcessPoolExecutor(max_workers=3) as pool:
                futures = {
                    pool.submit(
                        _backtest_worker,
                        sid, fp, self._df_m5_pickle, self._data_hash
                    ): sid
                    for sid, fp in jobs
                }
                for future in as_completed(futures, timeout=300):
                    sid = futures[future]
                    try:
                        result = future.result(timeout=60)
                        results.append(result)
                    except Exception as exc:
                        self.logger.error(f"Worker failed for {sid}: {exc}")
                        self._mark_rejected(sid, str(exc)[:200])
        except Exception as exc:
            self.logger.error(f"ProcessPool error: {exc}")
            return

        # Process results in main thread (DB writes)
        validated = 0
        rejected = 0
        for r in results:
            status = self._apply_worker_result(r)
            if status == "validated" and r.get("wf_passed", False):
                validated += 1
            else:
                rejected += 1

        if validated > 0 or rejected > 0:
            self.logger.info(f"Batch complete: {validated} validated, {rejected} rejected/failed")

    def _apply_worker_result(self, r: dict) -> str:
        """Persist a _backtest_worker result to the DB. Returns the result status."""
        sid = r["strategy_id"]
        status = r["status"]

        if status in ("rejected", "error"):
            self._mark_rejected(sid, r.get("reason", "unknown"))
            self.logger.info(f"Strategy {sid} rejected: {r.get('reason', 'unknown')}")
        elif status == "failed_validation":
            metrics = r.get("metrics", {})
            self._store_results(sid, metrics, {})
            self._update_strategy_metrics(sid, metrics)
            self.logger.info(f"Strategy {sid} did not pass validation: {r.get('fails')}")
        elif status == "validated":
            metrics = r.get("metrics", {})
            self._store_results(sid, metrics, {})
            self._update_strategy_metrics(sid, metrics)

            if r.get("wf_passed", False):
                self.db.execute(
                    "UPDATE strategies SET status = 'validated', walk_forward_passed = 1 WHERE id = ?",
                    (sid,),
                )
                probation = r.get("probation", False)
                if probation:
                    self._mark_probation(sid)
                label = "PROBATION (reduced size)" if probation else "full"
                self.emit_event(
                    "milestone",
                    f"Strategy {sid} passed validation + walk-forward + holdout [{label}]",
                    metadata={"strategy_id": sid,
                              "probation": probation,
                              "metrics": r.get("metrics_clean", {}),
                              "holdout_metrics": r.get("holdout_metrics")},
                )
                self.logger.info(f"Strategy {sid} VALIDATED [{label}] (walk-forward + holdout passed)")
            else:
                self.db.execute(
                    "UPDATE strategies SET status = 'validated', walk_forward_passed = 0 WHERE id = ?",
                    (sid,),
                )
                if r.get("wf_only", False) and not r.get("holdout_passed", True):
                    hm = r.get("holdout_metrics") or {}
                    self.logger.info(
                        f"Strategy {sid} passed backtest+WF but FAILED holdout "
                        f"(trades={hm.get('total_trades')}, PF={hm.get('profit_factor')})"
                    )
                else:
                    self.logger.info(f"Strategy {sid} passed backtest but FAILED walk-forward")
        return status

    # ──────────────────────────────────────────────────
    # Data loading
    # ──────────────────────────────────────────────────

    def _load_data(self) -> Optional[pd.DataFrame]:
        """Load XAUUSD M1 data, using the largest CSV in data/raw.

        Cached, but invalidated when the file changes on disk (the data
        agent appends fresh bars daily) so validation always runs against
        current data.
        """
        raw_dir = DATA_DIR / "raw"
        candidates = sorted(raw_dir.glob("XAUUSD_M1*.csv"), key=lambda p: p.stat().st_size, reverse=True)
        if not candidates:
            self.logger.warning("No XAUUSD_M1*.csv found in data/raw/")
            return None

        csv_path = candidates[0]
        mtime = csv_path.stat().st_mtime
        if self._data_cache is not None:
            if getattr(self, "_data_mtime", None) == mtime:
                return self._data_cache
            # Data refreshed on disk — drop all caches and reload
            self.logger.info("Data file changed on disk — reloading caches")
            self._data_cache = None
            self._data_cache_m5 = None
            self._df_m5_pickle = None
        self._data_mtime = mtime
        self.logger.info(f"Loading data from {csv_path}")
        df = pd.read_csv(csv_path, parse_dates=["time"])

        rename_map = {
            "open": "Open", "high": "High", "low": "Low",
            "close": "Close", "tick_volume": "Volume", "volume": "Volume",
        }
        df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})
        df = df.sort_values("time").reset_index(drop=True)

        h = hashlib.md5(csv_path.read_bytes()).hexdigest()
        self._data_hash = h
        self._data_cache = df
        return df

    def _load_data_m5(self) -> Optional[pd.DataFrame]:
        """Resample M1 data to M5. Cached until the M1 file changes on disk."""
        # _load_data first: it clears _data_cache_m5 when the file changed
        df_m1 = self._load_data()
        if df_m1 is None:
            return None
        if self._data_cache_m5 is not None:
            return self._data_cache_m5

        self.logger.info("Resampling M1 → M5...")
        df = df_m1.copy()
        df.set_index("time", inplace=True)
        agg = {
            "Open": "first", "High": "max", "Low": "min",
            "Close": "last", "Volume": "sum",
        }
        # Keep the per-bar spread through the resample (worst M1 spread of the
        # 5 minutes — conservative). Losing it made every backtest fall back
        # to the flat DEFAULT_SPREAD.
        if "spread" in df.columns:
            agg["spread"] = "max"
        df_m5 = df.resample("5min").agg(agg).dropna().reset_index()
        self._data_cache_m5 = df_m5
        self.logger.info(f"M5 data: {len(df_m5)} bars")
        return df_m5

    def _is_m5_strategy(self, strategy_id: str) -> bool:
        return True

    # ──────────────────────────────────────────────────
    # Strategy loading (used by task queue / single backtest)
    # ──────────────────────────────────────────────────

    def _resolve_strategy_path(self, strategy_id: str) -> Optional[Path]:
        """Find the strategy source file on disk. Returns the path or None."""
        row = self.db.fetchone("SELECT file_path FROM strategies WHERE id = ?", (strategy_id,))
        candidate_paths = []

        if row and row["file_path"]:
            db_path = Path(row["file_path"])
            candidate_paths.append(db_path)
            candidate_paths.append(DATA_DIR.parent / db_path)

        candidate_paths.append(STRATEGIES_DIR / f"strategy_{strategy_id.lower()}.py")

        for p in candidate_paths:
            if p.exists():
                return p
        return None

    def _load_strategy_module(self, strategy_id: str):
        """Dynamically load a strategy module. Returns the module or None."""
        module_path = self._resolve_strategy_path(strategy_id)
        if module_path is None:
            self.logger.warning(f"Strategy file not found for {strategy_id}")
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
    # Signal generation (used by task queue / single backtest)
    # ──────────────────────────────────────────────────

    def _build_signal_series(self, df: pd.DataFrame, module) -> tuple:
        params = getattr(module, "PARAMS", {})
        sl_atr = params.get("sl_atr", 1.5)
        tp_atr = params.get("tp_atr", 2.5)

        result_df = module.generate_signals(df.copy(), params)

        if "signal" not in result_df.columns or "ATR" not in result_df.columns:
            return None

        signals = result_df["signal"]
        atr = result_df["ATR"]
        close = result_df["Close"]

        sl_prices = pd.Series(np.nan, index=df.index)
        tp_prices = pd.Series(np.nan, index=df.index)
        directions = pd.Series(0, index=df.index)

        long_mask = signals == 1
        short_mask = signals == -1

        sl_prices[long_mask] = close[long_mask] - sl_atr * atr[long_mask]
        tp_prices[long_mask] = close[long_mask] + tp_atr * atr[long_mask]
        sl_prices[short_mask] = close[short_mask] + sl_atr * atr[short_mask]
        tp_prices[short_mask] = close[short_mask] - tp_atr * atr[short_mask]
        directions[long_mask] = 1
        directions[short_mask] = -1

        return signals, sl_prices, tp_prices, directions

    # ──────────────────────────────────────────────────
    # Single backtest (used by task queue)
    # ──────────────────────────────────────────────────

    def run_single_backtest(self, strategy_id: str) -> Optional[dict]:
        """Run a full backtest for strategy_id (sequential, for task queue).

        Delegates to the same _backtest_worker used by the parallel path so
        this path applies identical validation — including the walk-forward
        test (it previously granted walk_forward_passed=1 without running it).
        """
        # Skip if already validated/rejected
        row_check = self.db.fetchone(
            "SELECT status FROM strategies WHERE id = ?", (strategy_id,),
        )
        if row_check and row_check["status"] in ("validated", "rejected", "retired"):
            return None

        self.logger.info(f"Running backtest for strategy {strategy_id}")

        df = self._load_data_m5()
        if df is None:
            return None

        if self._df_m5_pickle is None:
            import pickle
            self._df_m5_pickle = pickle.dumps(df)

        file_path = self._resolve_strategy_path(strategy_id)
        if file_path is None:
            self.logger.warning(f"Strategy file not found for {strategy_id}")
            self._mark_rejected(strategy_id, "file_missing")
            return None

        result = _backtest_worker(
            strategy_id, str(file_path), self._df_m5_pickle, self._data_hash
        )
        self._apply_worker_result(result)
        # Never return the raw metrics: the equity_curve (one float per bar)
        # ends up json-serialized into task_queue.result and bloats the DB.
        metrics = result.get("metrics") or {}
        return {k: v for k, v in metrics.items() if k != "equity_curve"}

    # ──────────────────────────────────────────────────
    # Result persistence
    # ──────────────────────────────────────────────────

    def _revalidate_deployed(self):
        """Edge decay defense: re-run one stale deployed strategy per tick.

        The dataset refreshes daily, so every REVALIDATION_DAYS each deployed
        strategy faces the full gauntlet again on data that now includes the
        most recent market. Pass → metrics refreshed. Fail → undeployed
        (walk_forward_passed = 0) with a warning event; live history is kept.
        """
        from core.config import REVALIDATION_DAYS

        row = self.db.fetchone(
            "SELECT s.id FROM strategies s "
            "WHERE s.status = 'validated' AND s.walk_forward_passed = 1 "
            "AND NOT EXISTS (SELECT 1 FROM backtest_results b "
            "                WHERE b.strategy_id = s.id "
            f"                AND b.run_at >= datetime('now', '-{int(REVALIDATION_DAYS)} days')) "
            "LIMIT 1"
        )
        if not row:
            return
        sid = row["id"]

        df = self._load_data_m5()
        if df is None:
            return
        if self._df_m5_pickle is None:
            import pickle
            self._df_m5_pickle = pickle.dumps(df)

        file_path = self._resolve_strategy_path(sid)
        if file_path is None:
            self._demote_deployed(sid, "revalidation: file_missing")
            return

        self.logger.info(f"Re-validating deployed strategy {sid} (edge decay check)")
        result = _backtest_worker(sid, str(file_path), self._df_m5_pickle, self._data_hash)

        status = result.get("status")
        metrics = result.get("metrics") or {}
        still_good = status == "validated" and result.get("wf_passed", False)

        # Always store a result row: it refreshes best_* when better and,
        # in every case, restarts the REVALIDATION_DAYS clock.
        self._store_results(sid, metrics, {})
        if metrics:
            self._update_strategy_metrics(sid, metrics)

        if still_good:
            self.logger.info(f"Strategy {sid} re-validation PASSED (still deployable)")
        else:
            reason = result.get("reason") or ", ".join(result.get("fails", [])) or status
            self._demote_deployed(sid, f"revalidation_failed: {reason}")

    def _demote_deployed(self, strategy_id: str, reason: str):
        """Undeploy a strategy that no longer passes on fresh data."""
        self.db.execute(
            "UPDATE strategies SET walk_forward_passed = 0 WHERE id = ?",
            (strategy_id,),
        )
        self.emit_event(
            "warning",
            f"Strategy {strategy_id} UNDEPLOYED: failed periodic re-validation ({reason})",
            metadata={"strategy_id": strategy_id, "reason": reason},
        )
        self.logger.warning(f"Strategy {strategy_id} undeployed: {reason}")

    def _mark_probation(self, strategy_id: str):
        """Flag a probation strategy: best_config marker (merged, so Monte
        Carlo/sensitivity data survive) + low starting confidence so the
        gatekeeper sizes it at a quarter lot until live trades prove it."""
        row = self.db.fetchone(
            "SELECT best_config FROM strategies WHERE id = ?", (strategy_id,)
        )
        config = {}
        if row and row["best_config"]:
            try:
                config = (json.loads(row["best_config"])
                          if isinstance(row["best_config"], str) else row["best_config"])
            except (json.JSONDecodeError, TypeError):
                pass
        config["probation"] = True
        self.db.execute(
            "UPDATE strategies SET best_config = ? WHERE id = ?",
            (json.dumps(config), strategy_id),
        )
        self.db.execute(
            "INSERT INTO strategy_live_stats (strategy_id, confidence_score) "
            "VALUES (?, 40.0) "
            "ON CONFLICT(strategy_id) DO UPDATE SET confidence_score = 40.0",
            (strategy_id,),
        )

    def _mark_rejected(self, strategy_id: str, reason: str):
        self.db.execute(
            "UPDATE strategies SET status = 'rejected' WHERE id = ?",
            (strategy_id,),
        )

    def _store_results(self, strategy_id: str, metrics: dict, regime_results: dict):
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
        row = self.db.fetchone(
            "SELECT best_win_rate, best_profit_factor, best_max_drawdown, "
            "best_x10_count, best_final_balance FROM strategies WHERE id = ?",
            (strategy_id,),
        )
        if row is None:
            return

        current_pf = row["best_profit_factor"] or 0.0
        new_pf = metrics.get("profit_factor", 0.0)

        if new_pf > current_pf:
            # best_config is deliberately NOT touched here: monte_carlo and
            # sensitivity_agent store their results (p_ruin, is_fragile) in it,
            # and paper_trade relies on those to filter dangerous strategies.
            self.db.execute(
                "UPDATE strategies SET "
                "best_win_rate = ?, best_profit_factor = ?, best_max_drawdown = ?, "
                "best_x10_count = ?, best_final_balance = ? "
                "WHERE id = ?",
                (
                    metrics.get("win_rate"),
                    metrics.get("profit_factor"),
                    metrics.get("max_drawdown"),
                    metrics.get("x10_count"),
                    metrics.get("final_balance"),
                    strategy_id,
                ),
            )
