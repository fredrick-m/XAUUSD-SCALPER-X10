"""Sensitivity Analyzer: parameter robustness on the M5 selection window only.

The locked final holdout is never used for parameter sensitivity. Analysis
matches the backtest runner's timeframe, trailing/session and max-bars rules.
Transient failures remain retryable instead of being stamped as successful
sensitivity tests.
"""
import copy
import importlib.util
import json
import traceback
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from agents.base_agent import BaseAgent
from core.config import (
    DATA_DIR,
    STRATEGIES_DIR,
    DEFAULT_RISK_PCT,
    HOLDOUT_MONTHS,
)
from engine.backtest import run_simulation

PERTURBATION_FACTORS = [0.7, 0.8, 0.9, 1.1, 1.2, 1.3]
TUNABLE_KEYS = [
    "sl_atr", "tp_atr", "atr_period", "ema_fast", "ema_slow",
    "rsi_period", "rsi_upper", "rsi_lower", "adx_period", "adx_threshold",
    "bb_period", "bb_std", "macd_fast", "macd_slow", "macd_signal",
    "lookback", "threshold", "period", "window",
]
MAX_PF_DROP_10PCT = 0.50
ANALYSIS_PER_FAMILY = 8
SENSITIVITY_MAX_PER_TICK = 1


class SensitivityAgent(BaseAgent):
    """Perturb tunable parameters of Validation-V2 survivors."""

    name = "sensitivity_agent"

    def __init__(self, db):
        super().__init__(agent_id="sensitivity_agent", db=db)
        self._data_cache: Optional[pd.DataFrame] = None
        self._data_mtime: Optional[float] = None

    def setup(self):
        self.logger.info(
            f"Sensitivity V2 ready — M5 selection-only, up to {ANALYSIS_PER_FAMILY} variants/family"
        )

    def tick(self):
        strategies = self._get_untested_strategies()
        if not strategies:
            return
        df = self._load_selection_data_m5()
        if df is None:
            return

        max_per_tick = max(1, int(self.get_config("max_per_tick", SENSITIVITY_MAX_PER_TICK)))
        for strat in strategies[:max_per_tick]:
            try:
                self._analyze_sensitivity(strat["id"], df)
            except Exception as exc:
                self._record_failed_attempt(strat["id"], f"exception: {exc}")
                self.logger.error(
                    f"Sensitivity analysis failed for {strat['id']}: {exc}\n"
                    f"{traceback.format_exc()}"
                )

    def tick_interval(self) -> float:
        return self.get_config("tick_interval", 300)

    def _load_selection_data_m5(self) -> Optional[pd.DataFrame]:
        """Load/resample M1 -> M5 and remove the locked final holdout."""
        raw_dir = DATA_DIR / "raw"
        candidates = sorted(
            raw_dir.glob("XAUUSD_M1*.csv"),
            key=lambda p: p.stat().st_size,
            reverse=True,
        )
        if not candidates:
            self.logger.warning("No XAUUSD_M1*.csv found in data/raw/")
            return None

        csv_path = candidates[0]
        mtime = csv_path.stat().st_mtime
        if self._data_cache is not None and self._data_mtime == mtime:
            return self._data_cache

        self.logger.info(f"Loading M1 data for M5 sensitivity from {csv_path}")
        df = pd.read_csv(csv_path, parse_dates=["time"])
        rename_map = {
            "open": "Open", "high": "High", "low": "Low",
            "close": "Close", "tick_volume": "Volume", "volume": "Volume",
        }
        df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})
        df = df.sort_values("time").set_index("time")
        agg = {
            "Open": "first",
            "High": "max",
            "Low": "min",
            "Close": "last",
            "Volume": "sum",
        }
        if "spread" in df.columns:
            agg["spread"] = "max"
        m5 = df.resample("5min").agg(agg).dropna().reset_index()
        if len(m5) == 0:
            return None

        times = pd.to_datetime(m5["time"])
        holdout_start = times.iloc[-1] - pd.DateOffset(months=HOLDOUT_MONTHS)
        h_idx = int((times < holdout_start).sum())
        if h_idx < 5000 or (len(m5) - h_idx) < 1000:
            self.logger.warning("Sensitivity blocked: locked holdout boundary unavailable")
            return None

        selection = m5.iloc[:h_idx].reset_index(drop=True)
        self._data_cache = selection
        self._data_mtime = mtime
        self.logger.info(
            f"Sensitivity data: {len(selection)} M5 selection bars; "
            f"{len(m5) - h_idx} locked holdout bars excluded"
        )
        return selection

    def _load_strategy_module(self, strategy_id: str):
        row = self.db.fetchone("SELECT file_path FROM strategies WHERE id = ?", (strategy_id,))
        candidate_paths = []
        if row and row["file_path"]:
            db_path = Path(row["file_path"])
            candidate_paths.append(db_path)
            candidate_paths.append(DATA_DIR.parent / db_path)
        candidate_paths.append(STRATEGIES_DIR / f"strategy_{strategy_id.lower()}.py")

        for p in candidate_paths:
            if p.exists():
                try:
                    spec = importlib.util.spec_from_file_location(
                        f"strategy_{strategy_id.lower()}", str(p),
                    )
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    return module
                except Exception as exc:
                    self.logger.error(f"Failed to load {p}: {exc}")
                    return None
        return None

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
            if not config.get("sensitivity_tested", False):
                untested.append(dict(row))
        return untested

    def _run_backtest_with_params(
        self, df: pd.DataFrame, module, params: dict
    ) -> Optional[dict]:
        sl_atr = float(params.get("sl_atr", 1.5))
        tp_atr = float(params.get("tp_atr", 2.5))
        try:
            result_df = module.generate_signals(df.copy(), params)
        except Exception:
            return None
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

        try:
            use_trailing = bool(params.get("trailing", 1))
            if tp_atr >= 3.0:
                use_trailing = False
        except Exception:
            use_trailing = False
        sess_start = int(params.get("session_start", 7))
        sess_end = int(params.get("session_end", 21))
        if not (0 <= sess_start < sess_end <= 24):
            sess_start, sess_end = 7, 21

        try:
            return run_simulation(
                df,
                signals,
                sl_prices,
                tp_prices,
                directions,
                risk_pct=DEFAULT_RISK_PCT,
                trailing_stop=use_trailing,
                max_bars_in_trade=200,
                session_filter=True,
                session_hours=(sess_start, sess_end),
            )
        except Exception:
            return None

    def _analyze_sensitivity(self, strategy_id: str, df: pd.DataFrame):
        self.logger.info(f"Running M5 selection-only sensitivity for {strategy_id}")
        module = self._load_strategy_module(strategy_id)
        if module is None:
            self._record_failed_attempt(strategy_id, "strategy_module_unavailable")
            return

        base_params = copy.deepcopy(getattr(module, "PARAMS", {}))
        baseline_metrics = self._run_backtest_with_params(df, module, base_params)
        if baseline_metrics is None:
            self._record_failed_attempt(strategy_id, "baseline_simulation_failed")
            return

        baseline_pf = float(baseline_metrics.get("profit_factor", 0.0) or 0.0)
        if baseline_pf <= 0:
            self._record_failed_attempt(strategy_id, "baseline_pf_nonpositive")
            return

        tunable = [
            k for k in base_params
            if k in TUNABLE_KEYS and isinstance(base_params[k], (int, float))
        ]
        if not tunable:
            self._mark_tested(
                strategy_id,
                {
                    "model": "m5_selection_sensitivity_v2",
                    "locked_holdout_excluded": True,
                    "robust": True,
                    "is_fragile": False,
                    "reason": "no_tunable_params",
                },
            )
            return

        results = {}
        is_fragile = False
        for key in tunable:
            key_results = []
            for factor in PERTURBATION_FACTORS:
                perturbed_params = copy.deepcopy(base_params)
                original_val = base_params[key]
                new_val = original_val * factor
                if isinstance(original_val, int):
                    new_val = max(1, round(new_val))
                perturbed_params[key] = new_val

                metrics = self._run_backtest_with_params(df, module, perturbed_params)
                if metrics is None:
                    key_results.append({
                        "factor": factor,
                        "value": new_val,
                        "pf": 0.0,
                        "pf_ratio": 0.0,
                        "error": True,
                    })
                    if factor in (0.9, 1.1):
                        is_fragile = True
                    continue

                perturbed_pf = float(metrics.get("profit_factor", 0.0) or 0.0)
                pf_ratio = perturbed_pf / baseline_pf if baseline_pf > 0 else 0.0
                key_results.append({
                    "factor": round(factor, 2),
                    "value": round(new_val, 4) if isinstance(new_val, float) else new_val,
                    "pf": round(perturbed_pf, 4),
                    "wr": round(float(metrics.get("win_rate", 0.0) or 0.0), 4),
                    "pf_ratio": round(pf_ratio, 4),
                })
                if factor in (0.9, 1.1) and pf_ratio < (1.0 - MAX_PF_DROP_10PCT):
                    is_fragile = True
            results[key] = key_results

        all_ratios = [
            r["pf_ratio"]
            for key_results in results.values()
            for r in key_results
            if not r.get("error")
        ]
        robustness_score = round(float(np.mean(all_ratios)), 4) if all_ratios else 0.0
        sensitivity_result = {
            "model": "m5_selection_sensitivity_v2",
            "locked_holdout_excluded": True,
            "baseline_pf": round(baseline_pf, 4),
            "robustness_score": robustness_score,
            "is_fragile": is_fragile,
            "param_results": results,
        }
        self._mark_tested(strategy_id, sensitivity_result)

        if is_fragile:
            self.db.execute(
                "UPDATE strategies SET status = 'fragile', walk_forward_passed = 0 WHERE id = ?",
                (strategy_id,),
            )
            self.emit_event(
                "warning",
                f"Strategy {strategy_id} marked FRAGILE by M5 sensitivity "
                f"(robustness={robustness_score:.2f})",
                metadata={"strategy_id": strategy_id, "sensitivity": sensitivity_result},
            )
        else:
            self.emit_event(
                "milestone",
                f"Strategy {strategy_id} PASSED M5 selection-only sensitivity "
                f"(robustness={robustness_score:.2f})",
                metadata={"strategy_id": strategy_id, "sensitivity": sensitivity_result},
            )

    def _record_failed_attempt(self, strategy_id: str, reason: str):
        """Record diagnostics but keep the strategy retryable."""
        row = self.db.fetchone("SELECT best_config FROM strategies WHERE id = ?", (strategy_id,))
        config = {}
        if row and row["best_config"]:
            try:
                config = (
                    json.loads(row["best_config"])
                    if isinstance(row["best_config"], str)
                    else dict(row["best_config"])
                )
            except (json.JSONDecodeError, TypeError, ValueError):
                config = {}
        config["sensitivity_tested"] = False
        config["sensitivity_last_error"] = reason
        self.db.execute(
            "UPDATE strategies SET best_config = ? WHERE id = ?",
            (json.dumps(config), strategy_id),
        )

    def _mark_tested(self, strategy_id: str, result: dict):
        row = self.db.fetchone("SELECT best_config FROM strategies WHERE id = ?", (strategy_id,))
        config = {}
        if row and row["best_config"]:
            try:
                config = (
                    json.loads(row["best_config"])
                    if isinstance(row["best_config"], str)
                    else dict(row["best_config"])
                )
            except (json.JSONDecodeError, TypeError, ValueError):
                config = {}
        config["sensitivity_tested"] = True
        config["sensitivity"] = result
        config.pop("sensitivity_last_error", None)
        self.db.execute(
            "UPDATE strategies SET best_config = ? WHERE id = ?",
            (json.dumps(config), strategy_id),
        )
