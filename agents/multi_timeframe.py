"""Multi-Timeframe Agent: enriches M1 strategies with higher-timeframe trend filters."""
import importlib.util
import json
import traceback
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import ta

from agents.base_agent import BaseAgent
from core.config import DATA_DIR, STRATEGIES_DIR, DEFAULT_RISK_PCT
from engine.backtest import run_simulation, validate, add_regime_indicators


# Higher timeframes to resample M1 data into
HTF_CONFIGS = [
    {"name": "M5", "rule": "5min"},
    {"name": "M15", "rule": "15min"},
    {"name": "H1", "rule": "1h"},
]


def resample_ohlcv(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    """Resample M1 OHLCV data to a higher timeframe."""
    df_ts = df.set_index("time")
    resampled = df_ts.resample(rule).agg({
        "Open": "first",
        "High": "max",
        "Low": "min",
        "Close": "last",
        "Volume": "sum",
    }).dropna()
    return resampled.reset_index()


def compute_htf_trend(df_htf: pd.DataFrame, ema_period: int = 50) -> pd.Series:
    """Compute trend direction on a higher timeframe: +1 bullish, -1 bearish, 0 neutral."""
    ema = ta.trend.ema_indicator(df_htf["Close"], window=ema_period)
    trend = pd.Series(0, index=df_htf.index)
    trend[df_htf["Close"] > ema] = 1
    trend[df_htf["Close"] < ema] = -1
    return trend


def map_htf_trend_to_m1(df_m1: pd.DataFrame, df_htf: pd.DataFrame, trend: pd.Series) -> pd.Series:
    """
    Map a higher-timeframe trend series back to M1 bars using forward-fill.
    Each M1 bar gets the trend value from the most recent completed HTF bar.
    """
    htf_trend_ts = pd.Series(trend.values, index=df_htf["time"])
    # Reindex to M1 timestamps and forward-fill
    m1_trend = htf_trend_ts.reindex(df_m1["time"], method="ffill").fillna(0).astype(int)
    m1_trend.index = df_m1.index  # restore integer index
    return m1_trend


class MultiTimeframeAgent(BaseAgent):
    """Enriches validated strategies with higher-timeframe trend filters and re-backtests."""

    name = "multi_timeframe"

    def __init__(self, db):
        super().__init__(agent_id="multi_timeframe", db=db)
        self._data_cache: Optional[pd.DataFrame] = None
        self._htf_trends: dict = {}  # cached HTF trend series

    # ──────────────────────────────────────────────────
    # BaseAgent interface
    # ──────────────────────────────────────────────────

    def setup(self):
        self.logger.info("Multi-Timeframe Agent ready")

    def tick(self):
        strategies = self._get_untested_strategies()
        if not strategies:
            return

        df = self._load_data()
        if df is None:
            return

        # Precompute HTF trends once
        if not self._htf_trends:
            self._precompute_htf_trends(df)

        for strat in strategies:
            try:
                self._apply_htf_filter(strat["id"], df)
            except Exception as exc:
                self.logger.error(
                    f"Multi-TF analysis failed for {strat['id']}: {exc}\n"
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
    # HTF trend computation
    # ──────────────────────────────────────────────────

    def _precompute_htf_trends(self, df: pd.DataFrame):
        """Precompute trend series for all higher timeframes."""
        for htf_cfg in HTF_CONFIGS:
            name = htf_cfg["name"]
            rule = htf_cfg["rule"]
            try:
                df_htf = resample_ohlcv(df, rule)
                if len(df_htf) < 100:
                    self.logger.warning(f"Not enough bars for {name} ({len(df_htf)})")
                    continue
                trend = compute_htf_trend(df_htf, ema_period=50)
                m1_trend = map_htf_trend_to_m1(df, df_htf, trend)
                self._htf_trends[name] = m1_trend
                self.logger.info(f"Precomputed {name} trend: {len(df_htf)} bars")
            except Exception as exc:
                self.logger.error(f"Failed to compute {name} trend: {exc}")

    # ──────────────────────────────────────────────────
    # Strategy selection
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
            if not config.get("mtf_tested"):
                untested.append(dict(row))
        return untested

    # ──────────────────────────────────────────────────
    # Core: apply HTF filter and re-backtest
    # ──────────────────────────────────────────────────

    def _apply_htf_filter(self, strategy_id: str, df: pd.DataFrame):
        self.logger.info(f"Applying multi-timeframe filter to {strategy_id}")

        module = self._load_strategy_module(strategy_id)
        if module is None:
            self._mark_tested(strategy_id, None)
            return

        params = getattr(module, "PARAMS", {})
        sl_atr = params.get("sl_atr", 1.5)
        tp_atr = params.get("tp_atr", 2.5)

        # Generate base signals
        try:
            result_df = module.generate_signals(df.copy(), params)
        except Exception as exc:
            self.logger.error(f"Signal generation failed for {strategy_id}: {exc}")
            self._mark_tested(strategy_id, None)
            return

        if "signal" not in result_df.columns or "ATR" not in result_df.columns:
            self._mark_tested(strategy_id, None)
            return

        base_signals = result_df["signal"]
        atr = result_df["ATR"]
        close = result_df["Close"]

        # Baseline backtest (without HTF filter) for comparison
        baseline_metrics = self._run_with_signals(
            df, base_signals, close, atr, sl_atr, tp_atr
        )
        baseline_pf = baseline_metrics.get("profit_factor", 0.0) if baseline_metrics else 0.0

        # Test each HTF filter
        best_htf = None
        best_pf = baseline_pf
        best_metrics = baseline_metrics
        htf_results = {}

        for htf_name, htf_trend in self._htf_trends.items():
            # Filter: only allow signals in the direction of HTF trend
            filtered_signals = base_signals.copy()
            # Zero out long signals when HTF trend is bearish
            filtered_signals[(base_signals == 1) & (htf_trend == -1)] = 0
            # Zero out short signals when HTF trend is bullish
            filtered_signals[(base_signals == -1) & (htf_trend == 1)] = 0

            metrics = self._run_with_signals(
                df, filtered_signals, close, atr, sl_atr, tp_atr
            )
            if metrics is None:
                htf_results[htf_name] = {"error": True}
                continue

            pf = metrics.get("profit_factor", 0.0)
            wr = metrics.get("win_rate", 0.0)
            trades = metrics.get("total_trades", 0)

            htf_results[htf_name] = {
                "pf": round(pf, 4),
                "wr": round(wr, 4),
                "trades": trades,
                "improvement": round(pf / baseline_pf, 4) if baseline_pf > 0 else 0.0,
            }

            if pf > best_pf and trades >= 100:
                best_pf = pf
                best_htf = htf_name
                best_metrics = metrics

        mtf_result = {
            "baseline_pf": round(baseline_pf, 4),
            "best_htf": best_htf,
            "best_pf": round(best_pf, 4),
            "improvement": round(best_pf / baseline_pf, 4) if baseline_pf > 0 else 0.0,
            "htf_results": htf_results,
        }

        self._mark_tested(strategy_id, mtf_result)

        if best_htf and best_pf > baseline_pf * 1.1:
            self.emit_event(
                "milestone",
                f"Strategy {strategy_id} improved with {best_htf} filter: "
                f"PF {baseline_pf:.2f} → {best_pf:.2f} (+{(best_pf/baseline_pf - 1)*100:.0f}%)",
                metadata={"strategy_id": strategy_id, "mtf": mtf_result},
            )
            self.logger.info(
                f"Strategy {strategy_id}: {best_htf} filter improved PF by "
                f"{(best_pf/baseline_pf - 1)*100:.0f}%"
            )
        else:
            self.logger.info(f"Strategy {strategy_id}: no HTF filter improved performance")

    def _run_with_signals(self, df, signals, close, atr, sl_atr, tp_atr):
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
        config["mtf_tested"] = True
        if result is not None:
            config["multi_timeframe"] = result
        self.db.execute(
            "UPDATE strategies SET best_config = ? WHERE id = ?",
            (json.dumps(config), strategy_id),
        )
