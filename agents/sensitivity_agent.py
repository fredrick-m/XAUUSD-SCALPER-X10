"""Sensitivity Analyzer Agent: perturbs strategy parameters to detect fragile/overfit strategies."""
import copy
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


# Parameters to perturb and the perturbation factors
PERTURBATION_FACTORS = [0.7, 0.8, 0.9, 1.1, 1.2, 1.3]
# Keys inside PARAMS that are numeric and worth perturbing
TUNABLE_KEYS = [
    "sl_atr", "tp_atr", "atr_period", "ema_fast", "ema_slow",
    "rsi_period", "rsi_upper", "rsi_lower", "adx_period", "adx_threshold",
    "bb_period", "bb_std", "macd_fast", "macd_slow", "macd_signal",
    "lookback", "threshold", "period", "window",
]
# Max PF degradation allowed at ±10% perturbation
MAX_PF_DROP_10PCT = 0.50  # 50% drop → fragile


class SensitivityAgent(BaseAgent):
    """Perturbs each tunable parameter of validated strategies to detect overfitting."""

    name = "sensitivity_agent"

    def __init__(self, db):
        super().__init__(agent_id="sensitivity_agent", db=db)
        self._data_cache: Optional[pd.DataFrame] = None

    # ──────────────────────────────────────────────────
    # BaseAgent interface
    # ──────────────────────────────────────────────────

    def setup(self):
        self.logger.info("Sensitivity Analyzer Agent ready")

    def tick(self):
        """Find validated strategies that haven't been sensitivity-tested."""
        strategies = self._get_untested_strategies()
        if not strategies:
            return

        df = self._load_data()
        if df is None:
            return

        for strat in strategies:
            try:
                self._analyze_sensitivity(strat["id"], df)
            except Exception as exc:
                self.logger.error(
                    f"Sensitivity analysis failed for {strat['id']}: {exc}\n"
                    f"{traceback.format_exc()}"
                )

    def tick_interval(self) -> float:
        return self.get_config("tick_interval", 300)

    # ──────────────────────────────────────────────────
    # Data loading
    # ──────────────────────────────────────────────────

    def _load_data(self) -> Optional[pd.DataFrame]:
        if self._data_cache is not None:
            return self._data_cache

        raw_dir = DATA_DIR / "raw"
        candidates = sorted(
            raw_dir.glob("XAUUSD_M1*.csv"),
            key=lambda p: p.stat().st_size, reverse=True,
        )
        if not candidates:
            self.logger.warning("No XAUUSD_M1*.csv found in data/raw/")
            return None

        csv_path = candidates[0]
        self.logger.info(f"Loading data from {csv_path}")
        df = pd.read_csv(csv_path, parse_dates=["time"])
        rename_map = {
            "open": "Open", "high": "High", "low": "Low",
            "close": "Close", "tick_volume": "Volume", "volume": "Volume",
        }
        df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})
        df = df.sort_values("time").reset_index(drop=True)
        self._data_cache = df
        return df

    # ──────────────────────────────────────────────────
    # Strategy loading
    # ──────────────────────────────────────────────────

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

    # ──────────────────────────────────────────────────
    # Untested strategy retrieval
    # ──────────────────────────────────────────────────

    def _get_untested_strategies(self) -> list:
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
            if not config.get("sensitivity_tested"):
                untested.append(dict(row))
        return untested

    # ──────────────────────────────────────────────────
    # Core sensitivity analysis
    # ──────────────────────────────────────────────────

    def _run_backtest_with_params(self, df: pd.DataFrame, module, params: dict) -> Optional[dict]:
        """Run a backtest with custom params on the module."""
        sl_atr = params.get("sl_atr", 1.5)
        tp_atr = params.get("tp_atr", 2.5)

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
            return run_simulation(
                df, signals, sl_prices, tp_prices, directions,
                risk_pct=DEFAULT_RISK_PCT, trailing_stop=True,
                max_bars_in_trade=60, session_filter=True, session_hours=(7, 21),
            )
        except Exception:
            return None

    def _analyze_sensitivity(self, strategy_id: str, df: pd.DataFrame):
        self.logger.info(f"Running sensitivity analysis for {strategy_id}")

        module = self._load_strategy_module(strategy_id)
        if module is None:
            self._mark_tested(strategy_id, None)
            return

        base_params = copy.deepcopy(getattr(module, "PARAMS", {}))

        # Baseline run
        baseline_metrics = self._run_backtest_with_params(df, module, base_params)
        if baseline_metrics is None:
            self._mark_tested(strategy_id, None)
            return

        baseline_pf = baseline_metrics.get("profit_factor", 0.0)
        if baseline_pf <= 0:
            self._mark_tested(strategy_id, None)
            return

        # Find tunable keys in this strategy's PARAMS
        tunable = [k for k in base_params if k in TUNABLE_KEYS and isinstance(base_params[k], (int, float))]
        if not tunable:
            self.logger.info(f"No tunable parameters found for {strategy_id}")
            self._mark_tested(strategy_id, {"robust": True, "reason": "no_tunable_params"})
            return

        results = {}
        is_fragile = False

        for key in tunable:
            key_results = []
            for factor in PERTURBATION_FACTORS:
                perturbed_params = copy.deepcopy(base_params)
                original_val = base_params[key]

                # For integer params, round the perturbed value
                new_val = original_val * factor
                if isinstance(original_val, int):
                    new_val = max(1, round(new_val))

                perturbed_params[key] = new_val

                metrics = self._run_backtest_with_params(df, module, perturbed_params)
                if metrics is None:
                    key_results.append({
                        "factor": factor, "value": new_val, "pf": 0.0,
                        "pf_ratio": 0.0, "error": True,
                    })
                    continue

                perturbed_pf = metrics.get("profit_factor", 0.0)
                pf_ratio = perturbed_pf / baseline_pf if baseline_pf > 0 else 0.0

                key_results.append({
                    "factor": round(factor, 2),
                    "value": round(new_val, 4) if isinstance(new_val, float) else new_val,
                    "pf": round(perturbed_pf, 4),
                    "wr": round(metrics.get("win_rate", 0.0), 4),
                    "pf_ratio": round(pf_ratio, 4),
                })

                # Check if ±10% perturbation causes >50% PF drop
                if factor in (0.9, 1.1) and pf_ratio < (1.0 - MAX_PF_DROP_10PCT):
                    is_fragile = True

            results[key] = key_results

        # Compute overall robustness score: average PF ratio across all perturbations
        all_ratios = []
        for key_results in results.values():
            for r in key_results:
                if not r.get("error"):
                    all_ratios.append(r["pf_ratio"])

        robustness_score = round(np.mean(all_ratios), 4) if all_ratios else 0.0

        sensitivity_result = {
            "baseline_pf": round(baseline_pf, 4),
            "robustness_score": robustness_score,
            "is_fragile": is_fragile,
            "param_results": results,
        }

        self._mark_tested(strategy_id, sensitivity_result)

        if is_fragile:
            self.db.execute(
                "UPDATE strategies SET status = 'fragile' WHERE id = ?",
                (strategy_id,),
            )
            self.emit_event(
                "warning",
                f"Strategy {strategy_id} marked FRAGILE by sensitivity analysis "
                f"(robustness={robustness_score:.2f})",
                metadata={"strategy_id": strategy_id, "sensitivity": sensitivity_result},
            )
            self.logger.warning(f"Strategy {strategy_id} is FRAGILE (robustness={robustness_score:.2f})")
        else:
            self.emit_event(
                "milestone",
                f"Strategy {strategy_id} PASSED sensitivity analysis "
                f"(robustness={robustness_score:.2f})",
                metadata={"strategy_id": strategy_id, "sensitivity": sensitivity_result},
            )
            self.logger.info(f"Strategy {strategy_id} ROBUST (score={robustness_score:.2f})")

    def _mark_tested(self, strategy_id: str, result: Optional[dict]):
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
        config["sensitivity_tested"] = True
        if result is not None:
            config["sensitivity"] = result
        self.db.execute(
            "UPDATE strategies SET best_config = ? WHERE id = ?",
            (json.dumps(config), strategy_id),
        )
