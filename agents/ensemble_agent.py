"""Ensemble Agent: combines signals from multiple validated strategies into ensemble strategies."""
import hashlib
import importlib.util
import json
import traceback
from itertools import combinations
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from agents.base_agent import BaseAgent
from core.config import DATA_DIR, STRATEGIES_DIR, DEFAULT_RISK_PCT
from engine.backtest import run_simulation, validate, add_regime_indicators


class EnsembleAgent(BaseAgent):
    """Combines signals from multiple validated strategies into ensemble strategies."""

    name = "ensemble_agent"

    def __init__(self, db):
        super().__init__(agent_id="ensemble_agent", db=db)
        self._data_cache: Optional[pd.DataFrame] = None
        self._data_hash: Optional[str] = None

    # ──────────────────────────────────────────────────
    # BaseAgent interface
    # ──────────────────────────────────────────────────

    def setup(self):
        self.logger.info("Ensemble Agent ready")

    def tick(self):
        """Build ensemble strategies from validated components."""
        # 1. Get all validated strategies
        rows = self.db.fetchall(
            "SELECT id, file_path, best_profit_factor FROM strategies "
            "WHERE status = 'validated' ORDER BY best_profit_factor DESC",
        )
        validated = [dict(r) for r in rows]

        if len(validated) < 3:
            self.logger.info(
                f"Only {len(validated)} validated strategies — need at least 3 for ensemble"
            )
            return

        # 2. Load M1 data
        df = self._load_data()
        if df is None:
            self.logger.warning("No data available — skipping ensemble tick")
            return

        # 3. Load modules and generate signals for each validated strategy
        strategy_signals = {}
        strategy_params = {}
        strategy_atrs = {}
        for strat in validated:
            sid = strat["id"]
            module = self._load_strategy_module(sid)
            if module is None:
                continue
            sig_data = self._generate_signals(df, module)
            if sig_data is None:
                continue
            signals, atr = sig_data
            strategy_signals[sid] = signals
            strategy_params[sid] = getattr(module, "PARAMS", {})
            strategy_atrs[sid] = atr

        available_ids = list(strategy_signals.keys())
        if len(available_ids) < 3:
            self.logger.info(
                f"Only {len(available_ids)} strategies produced signals — need at least 3"
            )
            return

        # Build profit_factor lookup for weighting
        pf_lookup = {}
        for strat in validated:
            if strat["id"] in strategy_signals:
                pf_lookup[strat["id"]] = max(strat["best_profit_factor"] or 1.0, 0.01)

        # 4. Full ensemble: all available strategies
        self._try_ensemble(
            df, available_ids, strategy_signals, strategy_params,
            strategy_atrs, pf_lookup, method="vote",
        )
        self._try_ensemble(
            df, available_ids, strategy_signals, strategy_params,
            strategy_atrs, pf_lookup, method="weighted",
        )

        # 5. Subset ensembles: combinations of 3-5 from top strategies
        top_ids = available_ids[:10]  # limit base set to top 10
        combo_count = 0
        max_combos = 20
        for size in range(3, min(len(top_ids) + 1, 6)):
            for combo in combinations(top_ids, size):
                if combo_count >= max_combos:
                    break
                combo_list = list(combo)
                self._try_ensemble(
                    df, combo_list, strategy_signals, strategy_params,
                    strategy_atrs, pf_lookup, method="vote",
                )
                self._try_ensemble(
                    df, combo_list, strategy_signals, strategy_params,
                    strategy_atrs, pf_lookup, method="weighted",
                )
                combo_count += 1
            if combo_count >= max_combos:
                break

    def tick_interval(self) -> float:
        return self.get_config("tick_interval", 900)

    # ──────────────────────────────────────────────────
    # Data loading (mirrors backtest_runner pattern)
    # ──────────────────────────────────────────────────

    def _load_data(self) -> Optional[pd.DataFrame]:
        """Load XAUUSD M1 data, using the largest CSV in data/raw. Results are cached."""
        if self._data_cache is not None:
            return self._data_cache

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
        self.logger.info(f"Loading data from {csv_path}")
        df = pd.read_csv(csv_path, parse_dates=["time"])

        rename_map = {
            "open": "Open", "high": "High", "low": "Low",
            "close": "Close", "tick_volume": "Volume", "volume": "Volume",
        }
        df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})
        df = df.sort_values("time").reset_index(drop=True)

        # Resample to M5 — all validated strategies are M5-optimized
        df = df.set_index("time")
        df = df.resample("5min").agg({
            "Open": "first", "High": "max", "Low": "min",
            "Close": "last", "Volume": "sum",
        }).dropna().reset_index()

        h = hashlib.md5(csv_path.read_bytes()).hexdigest()
        self._data_hash = h
        self._data_cache = df
        return df

    # ──────────────────────────────────────────────────
    # Strategy loading
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
                f"strategy_{strategy_id.lower()}", str(module_path),
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
        except Exception as exc:
            self.logger.error(f"Failed to load strategy module {module_path}: {exc}")
            return None

    # ──────────────────────────────────────────────────
    # Signal generation
    # ──────────────────────────────────────────────────

    def _generate_signals(self, df: pd.DataFrame, module) -> Optional[tuple]:
        """
        Call module.generate_signals(df, module.PARAMS) and return (signals_series, atr_series).
        Returns None on failure.
        """
        params = getattr(module, "PARAMS", {})
        try:
            result_df = module.generate_signals(df.copy(), params)
        except Exception as exc:
            self.logger.error(f"generate_signals failed: {exc}")
            return None

        if "signal" not in result_df.columns or "ATR" not in result_df.columns:
            return None

        return result_df["signal"], result_df["ATR"]

    # ──────────────────────────────────────────────────
    # Ensemble construction
    # ──────────────────────────────────────────────────

    @staticmethod
    def majority_vote(signal_dict: dict) -> pd.Series:
        """Majority vote: signal = sign(sum of all component signals)."""
        all_signals = pd.DataFrame(signal_dict)
        vote_sum = all_signals.sum(axis=1)
        return np.sign(vote_sum).astype(int)

    @staticmethod
    def weighted_vote(signal_dict: dict, weights: dict) -> pd.Series:
        """Weighted vote: signal = sign(weighted sum of component signals)."""
        weighted_sum = pd.Series(0.0, index=next(iter(signal_dict.values())).index)
        for sid, signals in signal_dict.items():
            w = weights.get(sid, 1.0)
            weighted_sum += signals * w
        return np.sign(weighted_sum).astype(int)

    def _try_ensemble(
        self,
        df: pd.DataFrame,
        component_ids: list,
        strategy_signals: dict,
        strategy_params: dict,
        strategy_atrs: dict,
        pf_lookup: dict,
        method: str,
    ):
        """Build an ensemble from component_ids, backtest it, and save if it passes."""
        # Check if this exact ensemble already exists
        ensemble_key = f"{method}_{'_'.join(sorted(component_ids))}"
        existing = self.db.fetchone(
            "SELECT id FROM strategies WHERE family = 'ensemble' AND description LIKE ?",
            (f"%{ensemble_key}%",),
        )
        if existing:
            return

        # Gather signals for the selected components
        sig_dict = {sid: strategy_signals[sid] for sid in component_ids}

        # Compute ensemble signal
        if method == "vote":
            ensemble_signal = self.majority_vote(sig_dict)
        else:
            ensemble_signal = self.weighted_vote(sig_dict, pf_lookup)

        # Compute average ATR and average sl_atr/tp_atr across components
        atr_stack = pd.DataFrame({sid: strategy_atrs[sid] for sid in component_ids})
        avg_atr = atr_stack.mean(axis=1)

        sl_atrs = []
        tp_atrs = []
        for sid in component_ids:
            p = strategy_params.get(sid, {})
            sl_atrs.append(p.get("sl_atr", 1.5))
            tp_atrs.append(p.get("tp_atr", 2.5))
        avg_sl_atr = np.mean(sl_atrs)
        avg_tp_atr = np.mean(tp_atrs)

        # Build SL/TP price series
        close = df["Close"]
        sl_prices = pd.Series(np.nan, index=df.index)
        tp_prices = pd.Series(np.nan, index=df.index)
        directions = pd.Series(0, index=df.index)

        long_mask = ensemble_signal == 1
        short_mask = ensemble_signal == -1

        sl_prices[long_mask] = close[long_mask] - avg_sl_atr * avg_atr[long_mask]
        tp_prices[long_mask] = close[long_mask] + avg_tp_atr * avg_atr[long_mask]
        sl_prices[short_mask] = close[short_mask] + avg_sl_atr * avg_atr[short_mask]
        tp_prices[short_mask] = close[short_mask] - avg_tp_atr * avg_atr[short_mask]
        directions[long_mask] = 1
        directions[short_mask] = -1

        # Trailing stop rule: disable for wide-TP ensembles (avg_tp_atr >= 3.0)
        use_trailing = avg_tp_atr < 3.0

        # Run backtest (M5 data → 200 max bars)
        try:
            metrics = run_simulation(
                df,
                ensemble_signal,
                sl_prices,
                tp_prices,
                directions,
                risk_pct=DEFAULT_RISK_PCT,
                trailing_stop=use_trailing,
                max_bars_in_trade=200,
                session_filter=True,
                session_hours=(7, 20),
            )
        except Exception as exc:
            self.logger.error(f"Ensemble backtest failed ({method}, {component_ids}): {exc}")
            return

        # Regime analysis
        regimes_tested = 1
        try:
            df_regime = add_regime_indicators(df)
            regimes_present = set(df_regime["regime"].dropna().unique()) - {"UNKNOWN", "MIXED"}
            regimes_tested = max(1, len(regimes_present))
        except Exception:
            pass

        # Validate
        passed, fails = validate(metrics, regimes_tested=regimes_tested)
        if not passed:
            self.logger.info(
                f"Ensemble {method} ({len(component_ids)} components) did not pass: {fails}"
            )
            return

        # Passed — save the ensemble strategy
        self._save_ensemble(
            df, method, component_ids, metrics, avg_sl_atr, avg_tp_atr,
            pf_lookup, ensemble_key,
        )

    # ──────────────────────────────────────────────────
    # Save ensemble strategy
    # ──────────────────────────────────────────────────

    def _next_ensemble_id(self, method: str) -> str:
        """Generate the next ensemble strategy ID like ENS_VOTE_001 or ENS_WEIGHTED_001."""
        prefix = f"ENS_{method.upper()}_"
        rows = self.db.fetchall(
            "SELECT id FROM strategies WHERE id LIKE ?",
            (f"{prefix}%",),
        )
        existing_nums = []
        for r in rows:
            try:
                num = int(r["id"].replace(prefix, ""))
                existing_nums.append(num)
            except ValueError:
                continue
        next_num = max(existing_nums, default=0) + 1
        return f"{prefix}{next_num:03d}"

    def _save_ensemble(
        self,
        df: pd.DataFrame,
        method: str,
        component_ids: list,
        metrics: dict,
        avg_sl_atr: float,
        avg_tp_atr: float,
        pf_lookup: dict,
        ensemble_key: str,
    ):
        """Create a strategy file and register the ensemble in the DB."""
        strategy_id = self._next_ensemble_id(method)
        file_name = f"strategy_{strategy_id.lower()}.py"
        file_path = STRATEGIES_DIR / file_name

        # Build weights string for weighted method
        weights_dict = {sid: round(pf_lookup.get(sid, 1.0), 4) for sid in component_ids}

        # Generate strategy file
        code = self._generate_strategy_code(
            strategy_id, method, component_ids, avg_sl_atr, avg_tp_atr, weights_dict,
        )
        file_path.write_text(code, encoding="utf-8")
        self.logger.info(f"Saved ensemble strategy file: {file_path}")

        # Register in DB
        config_json = json.dumps({
            "method": method,
            "component_ids": component_ids,
            "weights": weights_dict,
            "avg_sl_atr": round(avg_sl_atr, 4),
            "avg_tp_atr": round(avg_tp_atr, 4),
        })

        self.db.execute(
            "INSERT INTO strategies "
            "(id, file_path, family, description, generation, created_by, status, "
            "best_win_rate, best_profit_factor, best_max_drawdown, best_x10_count, "
            "best_final_balance, best_config) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                strategy_id,
                f"strategies/{file_name}",
                "ensemble",
                f"Ensemble {method} | key={ensemble_key}",
                1,
                "ensemble_agent",
                "validated",
                metrics.get("win_rate"),
                metrics.get("profit_factor"),
                metrics.get("max_drawdown"),
                metrics.get("x10_count"),
                metrics.get("final_balance"),
                config_json,
            ),
        )

        # Store backtest result
        self.db.execute(
            "INSERT INTO backtest_results "
            "(strategy_id, risk_pct, total_trades, win_rate, profit_factor, "
            "max_drawdown, x10_count, final_balance, return_pct, blown_account, "
            "regime_results, walk_forward, data_hash) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                strategy_id, DEFAULT_RISK_PCT,
                metrics.get("total_trades", 0),
                metrics.get("win_rate", 0.0),
                metrics.get("profit_factor", 0.0),
                metrics.get("max_drawdown", 0.0),
                metrics.get("x10_count", 0),
                metrics.get("final_balance", 0.0),
                metrics.get("return_pct", 0.0),
                1 if metrics.get("blown_account") else 0,
                json.dumps({"type": "ensemble", "method": method}),
                0,
                self._data_hash,
            ),
        )

        # Emit milestone
        self.emit_event(
            "milestone",
            f"Ensemble strategy {strategy_id} ({method}, {len(component_ids)} components) passed validation",
            metadata={
                "strategy_id": strategy_id,
                "method": method,
                "components": component_ids,
                "metrics": {k: v for k, v in metrics.items() if k != "equity_curve"},
            },
        )
        self.logger.info(
            f"Ensemble {strategy_id} VALIDATED: "
            f"PF={metrics.get('profit_factor', 0):.2f}, "
            f"WR={metrics.get('win_rate', 0):.1%}, "
            f"x10={metrics.get('x10_count', 0)}"
        )

    # ──────────────────────────────────────────────────
    # Code generation for ensemble strategy files
    # ──────────────────────────────────────────────────

    @staticmethod
    def _generate_strategy_code(
        strategy_id: str,
        method: str,
        component_ids: list,
        avg_sl_atr: float,
        avg_tp_atr: float,
        weights: dict,
    ) -> str:
        """Generate a Python strategy file for the ensemble."""
        components_str = json.dumps(component_ids)
        weights_str = json.dumps(weights)
        method_label = "Majority Vote" if method == "vote" else "Weighted Vote"

        return f'''"""
Strategy {strategy_id}: Ensemble {method_label}
Family  : ensemble
Goal    : XAUUSD-SCALPER-X10 — x10 returns in < 20 days
Timeframe: M1 (XAUUSD)
Description: Ensemble {method_label} combining {len(component_ids)} validated strategies
Components: {components_str}

Parameters:
  sl_atr: {avg_sl_atr:.4f}
  tp_atr: {avg_tp_atr:.4f}
  method: {method}
"""

import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd
import ta

PARAMS = {{
    "sl_atr": {avg_sl_atr:.4f},
    "tp_atr": {avg_tp_atr:.4f},
    "atr_period": 14,
    "method": "{method}",
    "component_ids": {components_str},
    "weights": {weights_str},
}}

STRATEGIES_DIR = Path(__file__).resolve().parent


def _load_component_module(strategy_id: str):
    """Load a component strategy module by ID."""
    module_path = STRATEGIES_DIR / f"strategy_{{strategy_id.lower()}}.py"
    if not module_path.exists():
        return None
    spec = importlib.util.spec_from_file_location(
        f"strategy_{{strategy_id.lower()}}", str(module_path),
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def generate_signals(df: pd.DataFrame, p: dict = PARAMS) -> pd.DataFrame:
    """Generate ensemble signals by combining component strategy signals."""
    df = df.copy()

    # Compute ATR for SL/TP
    atr_period = p.get("atr_period", 14)
    df["ATR"] = ta.volatility.average_true_range(
        df["High"], df["Low"], df["Close"], window=atr_period,
    )

    component_ids = p["component_ids"]
    weights = p.get("weights", {{}})
    method = p.get("method", "{method}")

    # Collect signals from each component
    all_signals = {{}}
    for sid in component_ids:
        mod = _load_component_module(sid)
        if mod is None:
            continue
        mod_params = getattr(mod, "PARAMS", {{}})
        try:
            result = mod.generate_signals(df.copy(), mod_params)
            if "signal" in result.columns:
                all_signals[sid] = result["signal"]
        except Exception:
            continue

    if not all_signals:
        df["signal"] = 0
        return df

    sig_df = pd.DataFrame(all_signals)

    if method == "weighted":
        weighted_sum = pd.Series(0.0, index=df.index)
        for sid in sig_df.columns:
            w = weights.get(sid, 1.0)
            weighted_sum += sig_df[sid].fillna(0) * w
        df["signal"] = np.sign(weighted_sum).astype(int)
    else:
        vote_sum = sig_df.fillna(0).sum(axis=1)
        df["signal"] = np.sign(vote_sum).astype(int)

    return df
'''
