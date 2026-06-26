"""Regime Filter agent: analyzes market regimes and tags strategies with per-regime performance."""
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


# Regimes we care about (exclude UNKNOWN and MIXED)
_TARGET_REGIMES = {"TREND", "RANGE", "HIGH_VOLATILITY"}


class RegimeFilter(BaseAgent):
    """Analyzes market regimes and evaluates strategy performance in each regime."""

    name = "regime_filter"

    def __init__(self, db):
        super().__init__(agent_id="regime_filter", db=db)
        self._data_cache: Optional[pd.DataFrame] = None
        self._data_hash: Optional[str] = None

    # ──────────────────────────────────────────────────
    # BaseAgent interface
    # ──────────────────────────────────────────────────

    def setup(self):
        self.logger.info("Regime Filter ready")

    def tick(self):
        """Find validated strategies missing per-regime results and backtest them."""
        df = self._load_data()
        if df is None:
            return

        df_regime = add_regime_indicators(df)
        strategies = self._get_strategies_needing_regime_analysis()

        for strategy in strategies:
            strategy_id = strategy["id"]
            try:
                self._analyse_strategy_regimes(strategy_id, df, df_regime)
            except Exception as exc:
                self.logger.error(
                    f"Regime analysis failed for {strategy_id}: {exc}\n{traceback.format_exc()}"
                )

    def tick_interval(self) -> float:
        return self.get_config("tick_interval", 120)

    # ──────────────────────────────────────────────────
    # Data loading (mirrors backtest_runner pattern)
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

        h = hashlib.md5(csv_path.read_bytes()).hexdigest()
        self._data_hash = h
        self._data_cache = df
        return df

    # ──────────────────────────────────────────────────
    # Strategy loading (mirrors backtest_runner pattern)
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
    # Signal generation (mirrors backtest_runner pattern)
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
    # Strategy selection
    # ──────────────────────────────────────────────────

    def _get_strategies_needing_regime_analysis(self) -> list:
        """Return validated strategies whose backtest_results lack per-regime data."""
        rows = self.db.fetchall(
            "SELECT s.id FROM strategies s "
            "JOIN backtest_results b ON s.id = b.strategy_id "
            "WHERE s.status = 'validated' AND b.walk_forward = 0",
        )
        strategies_needing_work = []
        seen = set()
        for row in rows:
            sid = row["id"]
            if sid in seen:
                continue
            seen.add(sid)

            # Check if the strategy already has per-regime results
            bt = self.db.fetchone(
                "SELECT regime_results FROM backtest_results "
                "WHERE strategy_id = ? AND walk_forward = 0 ORDER BY run_at DESC LIMIT 1",
                (sid,),
            )
            if bt and bt["regime_results"]:
                try:
                    rr = json.loads(bt["regime_results"]) if isinstance(bt["regime_results"], str) else bt["regime_results"]
                    # Already has per-regime keys -> skip
                    if any(k in rr for k in _TARGET_REGIMES):
                        continue
                except (json.JSONDecodeError, TypeError):
                    pass
            strategies_needing_work.append({"id": sid})

        return strategies_needing_work

    # ──────────────────────────────────────────────────
    # Core regime analysis
    # ──────────────────────────────────────────────────

    def _analyse_strategy_regimes(self, strategy_id: str, df: pd.DataFrame, df_regime: pd.DataFrame):
        """Run the strategy's backtest on each regime subset and store results."""
        self.logger.info(f"Running regime analysis for strategy {strategy_id}")

        module = self._load_strategy_module(strategy_id)
        if module is None:
            self.logger.warning(f"Could not load strategy module for {strategy_id}")
            return

        regimes_present = set(df_regime["regime"].dropna().unique()) & _TARGET_REGIMES
        if not regimes_present:
            self.logger.warning("No target regimes found in data — skipping")
            return

        regime_results = {}
        regimes_passed = 0

        for regime_name in sorted(regimes_present):
            mask = df_regime["regime"] == regime_name
            df_subset = df.loc[mask].reset_index(drop=True)

            if len(df_subset) < 500:
                self.logger.info(
                    f"Regime {regime_name}: only {len(df_subset)} bars — skipping (need 500+)"
                )
                regime_results[regime_name] = {"skipped": True, "bars": len(df_subset)}
                continue

            signal_data = self._build_signal_series(df_subset, module)
            if signal_data is None:
                regime_results[regime_name] = {"error": "signal generation failed"}
                continue

            signals, sl_prices, tp_prices, directions = signal_data

            try:
                metrics = run_simulation(
                    df_subset,
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
                self.logger.error(f"run_simulation failed for {strategy_id} regime {regime_name}: {exc}")
                regime_results[regime_name] = {"error": str(exc)}
                continue

            # Strip equity_curve from stored results (too large for JSON)
            metrics_to_store = {k: v for k, v in metrics.items() if k != "equity_curve"}
            regime_results[regime_name] = metrics_to_store

            # Check if this regime passes validation (use regimes_tested=1 for per-regime)
            passed, fails = validate(metrics, regimes_tested=1)
            regime_results[regime_name]["passed"] = passed
            if passed:
                regimes_passed += 1
                self.logger.info(f"Strategy {strategy_id} PASSED in regime {regime_name}")
            else:
                self.logger.info(
                    f"Strategy {strategy_id} FAILED in regime {regime_name}: {fails}"
                )

        # Store per-regime results in backtest_results
        self._store_regime_results(strategy_id, regime_results)

        # Update strategies.regimes_passed
        self.db.execute(
            "UPDATE strategies SET regimes_passed = ? WHERE id = ?",
            (regimes_passed, strategy_id),
        )

        # Emit event for strategies passing 3+ regimes
        if regimes_passed >= 3:
            self.emit_event(
                "milestone",
                f"Strategy {strategy_id} passed {regimes_passed} regime(s)",
                metadata={
                    "strategy_id": strategy_id,
                    "regimes_passed": regimes_passed,
                    "regime_results": {
                        k: {mk: mv for mk, mv in v.items() if mk != "equity_curve"}
                        for k, v in regime_results.items()
                        if isinstance(v, dict)
                    },
                },
            )

    def _store_regime_results(self, strategy_id: str, regime_results: dict):
        """Update the most recent non-walk-forward backtest_results row with regime data."""
        bt = self.db.fetchone(
            "SELECT id FROM backtest_results "
            "WHERE strategy_id = ? AND walk_forward = 0 ORDER BY run_at DESC LIMIT 1",
            (strategy_id,),
        )
        if bt:
            self.db.execute(
                "UPDATE backtest_results SET regime_results = ? WHERE id = ?",
                (json.dumps(regime_results), bt["id"]),
            )
        else:
            self.logger.warning(
                f"No backtest_results row found for {strategy_id} — cannot store regime results"
            )
