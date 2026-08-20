"""Portfolio selection agent.

Final deployment gate before paper trading. A strategy must survive:
- walk-forward + holdout upstream,
- multiple-testing-adjusted statistical evidence,
- chronological stability across several market blocks,
- Monte Carlo / sensitivity safety,
- correlation and family-diversification constraints.

The objective is to build toward 100+ genuinely different robust strategies,
not to fill 100 slots with lucky or redundant variants.
"""

import importlib.util
import json
import math
from pathlib import Path
from statistics import NormalDist, median
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from agents.base_agent import BaseAgent
from core.config import DATA_DIR, STRATEGIES_DIR, DEFAULT_RISK_PCT
from engine.backtest import run_simulation


class CorrelationAgent(BaseAgent):
    name = "correlation_agent"

    HIGH_CORR_THRESHOLD = 0.70
    PORTFOLIO_CORR_THRESHOLD = 0.45
    TARGET_PORTFOLIO_SIZE = 100
    MAX_PER_FAMILY = 8

    # Statistical deployment gate
    BASE_ALPHA = 0.05
    MIN_CONFIDENCE_TRADES = 60
    MIN_ADJUSTED_WR_LB = 0.50
    MIN_ADJUSTED_PF = 1.20
    MAX_ADJUSTED_DD = 0.30

    # Chronological stability gate
    STABILITY_FOLDS = 4
    STABILITY_MIN_ACTIVE_FOLDS = 3
    STABILITY_MIN_TRADES_PER_FOLD = 5
    STABILITY_MIN_PROFITABLE_RATIO = 0.75
    STABILITY_MIN_MEDIAN_PF = 1.05
    STABILITY_MAX_WORST_DD = 0.35

    def __init__(self, db):
        super().__init__(agent_id="correlation_agent", db=db)
        self._data_cache: Optional[pd.DataFrame] = None
        self._data_mtime: Optional[float] = None

    def setup(self):
        self.logger.info(
            "Portfolio selector V4 ready — multiple-testing + chronological stability gates active"
        )

    def tick(self):
        total_trials = self._tested_strategy_count()
        candidates = self._get_candidates(total_trials)
        if not candidates:
            self.logger.info(
                f"Portfolio selector: 0 statistically eligible strategies after {total_trials} tested"
            )
            return

        df = self._load_data_m5()
        if df is None:
            self.logger.warning("No XAUUSD data available for portfolio selection")
            return

        # Chronological stability is deliberately checked after the cheap
        # statistical gate, so expensive fold simulations are only run on
        # strategies with enough evidence to matter.
        stable = []
        stability_evidence = {}
        for s in candidates:
            passed, evidence = self._chronological_stability(s, df)
            stability_evidence[s["id"]] = evidence
            self._merge_config(s["id"], chronological_stability=evidence)
            if passed:
                stable.append(s)

        if len(stable) < 2:
            self.logger.info(
                f"Portfolio selector: {len(stable)} survived chronological stability "
                f"from {len(candidates)} statistically eligible"
            )
            return

        signals = self._load_all_signals(stable, df)
        if not signals:
            return

        ids = list(signals)
        corr = self._compute_correlation_matrix(signals)
        strat_map = {s["id"]: s for s in stable}

        scores = {
            sid: self._score_strategy(strat_map[sid], stability_evidence.get(sid, {}))
            for sid in ids
        }
        clusters = self._find_clusters(ids, corr, self.HIGH_CORR_THRESHOLD)
        duplicate_of = self._best_per_cluster(clusters, scores)

        portfolio = self._build_portfolio(ids, corr, strat_map, scores, duplicate_of)
        self._apply_portfolio_state(stable, portfolio, scores, duplicate_of)
        self._store_portfolio_event(
            portfolio, scores, duplicate_of, total_trials,
            statistically_eligible=len(candidates), stable_count=len(stable),
        )

    def tick_interval(self) -> float:
        return self.get_config("tick_interval", 600)

    # ------------------------------------------------------------------
    # Multiple-testing-aware statistical evidence
    # ------------------------------------------------------------------
    def _tested_strategy_count(self) -> int:
        row = self.db.fetchone("SELECT COUNT(DISTINCT strategy_id) AS n FROM backtest_results")
        return max(1, int(row["n"] or 0) if row else 1)

    def _latest_trade_count(self, strategy_id: str) -> int:
        row = self.db.fetchone(
            "SELECT total_trades FROM backtest_results WHERE strategy_id = ? "
            "ORDER BY run_at DESC, id DESC LIMIT 1", (strategy_id,),
        )
        return int(row["total_trades"] or 0) if row else 0

    @staticmethod
    def _wilson_lower_bound(wins: float, n: int, z: float) -> float:
        if n <= 0:
            return 0.0
        p = min(max(float(wins) / n, 0.0), 1.0)
        z2 = z * z
        denom = 1.0 + z2 / n
        center = p + z2 / (2.0 * n)
        margin = z * math.sqrt((p * (1.0 - p) + z2 / (4.0 * n)) / n)
        return max(0.0, (center - margin) / denom)

    def _statistical_gate(self, s: dict, total_trials: int) -> tuple[bool, dict]:
        sid = s["id"]
        n = self._latest_trade_count(sid)
        wr = float(s.get("best_win_rate") or 0.0)
        pf = float(s.get("best_profit_factor") or 0.0)
        dd = float(s.get("best_max_drawdown") or 1.0)

        # Conservative family-wise-error correction. The z cap prevents the
        # evidence requirement from becoming numerically absurd after tens of
        # thousands of related experiments; independent holdout/stability/MC
        # gates remain on top of this correction.
        effective_alpha = max(1e-8, self.BASE_ALPHA / max(1, total_trials))
        z = NormalDist().inv_cdf(1.0 - effective_alpha / 2.0)
        z = min(max(z, 1.96), 4.5)
        wins = round(wr * n)
        wr_lb = self._wilson_lower_bound(wins, n, z)

        breadth = max(0.0, math.log10(max(1, total_trials)))
        adaptive_min_trades = self.MIN_CONFIDENCE_TRADES + int(10 * breadth)
        adaptive_pf = self.MIN_ADJUSTED_PF + min(0.15, 0.03 * breadth)

        passed = (
            n >= adaptive_min_trades
            and wr_lb >= self.MIN_ADJUSTED_WR_LB
            and pf >= adaptive_pf
            and dd <= self.MAX_ADJUSTED_DD
        )
        return passed, {
            "tested_universe": total_trials,
            "trades": n,
            "effective_alpha": effective_alpha,
            "z": round(z, 4),
            "wr": round(wr, 4),
            "wr_lower_bound_adjusted": round(wr_lb, 4),
            "pf": round(pf, 4),
            "required_pf": round(adaptive_pf, 4),
            "dd": round(dd, 4),
            "required_min_trades": adaptive_min_trades,
            "passed": passed,
        }

    def _get_candidates(self, total_trials: int) -> List[dict]:
        rows = self.db.fetchall(
            "SELECT DISTINCT s.id, s.file_path, s.family, s.best_profit_factor, "
            "s.best_win_rate, s.best_max_drawdown, s.regimes_passed, "
            "s.best_x10_count, s.best_config, s.status "
            "FROM strategies s JOIN backtest_results b ON b.strategy_id = s.id "
            "WHERE s.walk_forward_passed = 1 "
            "AND s.status IN ('validated', 'portfolio_reserve')"
        )
        result = []
        for row in rows:
            s = dict(row)
            cfg = self._config(s)
            mc = cfg.get("monte_carlo", {})
            ruin = mc.get("p_ruin_10d", mc.get("p_ruin", 0.0))
            if ruin is not None and float(ruin) > 0.10:
                continue
            if cfg.get("sensitivity", {}).get("is_fragile", False):
                continue

            passed, evidence = self._statistical_gate(s, total_trials)
            self._merge_config(s["id"], statistical_evidence=evidence)
            if passed:
                result.append(s)
        return result

    # ------------------------------------------------------------------
    # Market data and strategy loading
    # ------------------------------------------------------------------
    def _load_data_m5(self) -> Optional[pd.DataFrame]:
        raw_dir = DATA_DIR / "raw"
        files = sorted(raw_dir.glob("XAUUSD_M1*.csv"), key=lambda p: p.stat().st_size, reverse=True)
        if not files:
            return None
        path = files[0]
        mtime = path.stat().st_mtime
        if self._data_cache is not None and self._data_mtime == mtime:
            return self._data_cache

        df = pd.read_csv(path, parse_dates=["time"])
        rename = {
            "open": "Open", "high": "High", "low": "Low", "close": "Close",
            "tick_volume": "Volume", "volume": "Volume",
        }
        df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})
        df = df.sort_values("time").set_index("time")
        agg = {
            "Open": "first", "High": "max", "Low": "min",
            "Close": "last", "Volume": "sum",
        }
        if "spread" in df.columns:
            agg["spread"] = "max"
        df = df.resample("5min").agg(agg).dropna().reset_index()
        self._data_cache = df
        self._data_mtime = mtime
        return df

    def _load_strategy_module(self, strategy_id: str, file_path: str):
        candidates = []
        if file_path:
            p = Path(file_path)
            candidates.extend([p, DATA_DIR.parent / p])
        candidates.append(STRATEGIES_DIR / f"strategy_{strategy_id.lower()}.py")
        path = next((p for p in candidates if p.exists()), None)
        if path is None:
            return None
        try:
            spec = importlib.util.spec_from_file_location(f"strategy_{strategy_id.lower()}", str(path))
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
        except Exception as exc:
            self.logger.warning(f"Could not load {strategy_id}: {exc}")
            return None

    def _strategy_series(self, s: dict, df: pd.DataFrame):
        module = self._load_strategy_module(s["id"], s.get("file_path") or "")
        if module is None or not hasattr(module, "generate_signals"):
            return None
        params = getattr(module, "PARAMS", {})
        try:
            out = module.generate_signals(df.copy(), params)
        except Exception as exc:
            self.logger.warning(f"Signal generation failed for {s['id']}: {exc}")
            return None
        if "signal" not in out.columns or "ATR" not in out.columns:
            return None

        signals = out["signal"].fillna(0).astype(float)
        atr = out["ATR"]
        close = out["Close"]
        sl_atr = float(params.get("sl_atr", 1.5))
        tp_atr = float(params.get("tp_atr", 2.5))

        sl = pd.Series(np.nan, index=df.index)
        tp = pd.Series(np.nan, index=df.index)
        directions = pd.Series(0, index=df.index)
        long_mask = signals == 1
        short_mask = signals == -1
        sl[long_mask] = close[long_mask] - sl_atr * atr[long_mask]
        tp[long_mask] = close[long_mask] + tp_atr * atr[long_mask]
        sl[short_mask] = close[short_mask] + sl_atr * atr[short_mask]
        tp[short_mask] = close[short_mask] - tp_atr * atr[short_mask]
        directions[long_mask] = 1
        directions[short_mask] = -1

        try:
            use_trailing = bool(params.get("trailing", 1)) and tp_atr < 3.0
        except Exception:
            use_trailing = False
        sess_start = int(params.get("session_start", 7))
        sess_end = int(params.get("session_end", 21))
        if not (0 <= sess_start < sess_end <= 24):
            sess_start, sess_end = 7, 21

        return signals, sl, tp, directions, use_trailing, (sess_start, sess_end)

    def _load_all_signals(self, strategies: List[dict], df: pd.DataFrame) -> Dict[str, np.ndarray]:
        signals = {}
        for s in strategies:
            series = self._strategy_series(s, df)
            if series is None:
                continue
            sig = series[0].to_numpy()
            if np.count_nonzero(sig) >= 5:
                signals[s["id"]] = sig
        return signals

    # ------------------------------------------------------------------
    # Chronological stability
    # ------------------------------------------------------------------
    def _chronological_stability(self, s: dict, df: pd.DataFrame) -> tuple[bool, dict]:
        series = self._strategy_series(s, df)
        if series is None:
            return False, {"passed": False, "reason": "signal_series_unavailable"}
        signals, sl, tp, directions, trailing, session = series

        folds = int(self.get_config("stability_folds", self.STABILITY_FOLDS))
        n = len(df)
        if folds < 2 or n < folds * 500:
            return False, {"passed": False, "reason": "insufficient_data_for_stability", "bars": n}

        fold_metrics = []
        active = 0
        profitable = 0
        for fold in range(folds):
            a = int(n * fold / folds)
            b = int(n * (fold + 1) / folds)
            try:
                m = run_simulation(
                    df.iloc[a:b], signals.iloc[a:b], sl.iloc[a:b], tp.iloc[a:b],
                    directions.iloc[a:b], risk_pct=DEFAULT_RISK_PCT,
                    trailing_stop=trailing, max_bars_in_trade=200,
                    session_filter=True, session_hours=session,
                )
            except Exception:
                continue

            trades = int(m.get("total_trades", 0))
            pf = float(m.get("profit_factor", 0.0) or 0.0)
            ret = float(m.get("return_pct", 0.0) or 0.0)
            dd = float(m.get("max_drawdown", 1.0) or 1.0)
            is_active = trades >= self.STABILITY_MIN_TRADES_PER_FOLD
            is_profitable = is_active and pf >= 1.0 and ret > 0
            if is_active:
                active += 1
            if is_profitable:
                profitable += 1
            fold_metrics.append({
                "fold": fold + 1, "trades": trades, "pf": round(pf, 4),
                "return_pct": round(ret, 2), "dd": round(dd, 4),
                "profitable": is_profitable,
            })

        active_pfs = [x["pf"] for x in fold_metrics if x["trades"] >= self.STABILITY_MIN_TRADES_PER_FOLD]
        active_dds = [x["dd"] for x in fold_metrics if x["trades"] >= self.STABILITY_MIN_TRADES_PER_FOLD]
        profitable_ratio = profitable / active if active else 0.0
        med_pf = float(median(active_pfs)) if active_pfs else 0.0
        worst_dd = max(active_dds) if active_dds else 1.0

        passed = (
            active >= min(self.STABILITY_MIN_ACTIVE_FOLDS, folds)
            and profitable_ratio >= self.STABILITY_MIN_PROFITABLE_RATIO
            and med_pf >= self.STABILITY_MIN_MEDIAN_PF
            and worst_dd <= self.STABILITY_MAX_WORST_DD
        )
        return passed, {
            "passed": passed,
            "folds": folds,
            "active_folds": active,
            "profitable_folds": profitable,
            "profitable_ratio": round(profitable_ratio, 4),
            "median_pf": round(med_pf, 4),
            "worst_dd": round(worst_dd, 4),
            "fold_metrics": fold_metrics,
        }

    # ------------------------------------------------------------------
    # Correlation / ranking / portfolio persistence
    # ------------------------------------------------------------------
    @staticmethod
    def _compute_correlation_matrix(signals: Dict[str, np.ndarray]) -> np.ndarray:
        ids = list(signals)
        matrix = np.column_stack([signals[sid] for sid in ids])
        corr = pd.DataFrame(matrix, columns=ids).corr().to_numpy()
        return np.nan_to_num(corr, nan=0.0, posinf=0.0, neginf=0.0)

    @staticmethod
    def _find_clusters(ids: List[str], corr: np.ndarray, threshold: float) -> List[List[str]]:
        n = len(ids)
        parent = list(range(n))
        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x
        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[rb] = ra
        for i in range(n):
            for j in range(i + 1, n):
                if abs(float(corr[i, j])) >= threshold:
                    union(i, j)
        groups = {}
        for i, sid in enumerate(ids):
            groups.setdefault(find(i), []).append(sid)
        return [g for g in groups.values() if len(g) > 1]

    @staticmethod
    def _best_per_cluster(clusters: List[List[str]], scores: dict) -> dict:
        duplicate_of = {}
        for cluster in clusters:
            best = max(cluster, key=lambda sid: scores.get(sid, -999.0))
            for sid in cluster:
                if sid != best:
                    duplicate_of[sid] = best
        return duplicate_of

    @staticmethod
    def _config(strategy: dict) -> dict:
        cfg = strategy.get("best_config")
        if not cfg:
            return {}
        if isinstance(cfg, dict):
            return cfg
        try:
            return json.loads(cfg)
        except (json.JSONDecodeError, TypeError):
            return {}

    def _score_strategy(self, s: dict, stability: dict) -> float:
        pf = float(s.get("best_profit_factor") or 0.0)
        wr = float(s.get("best_win_rate") or 0.0)
        dd = float(s.get("best_max_drawdown") or 1.0)
        regimes = float(s.get("regimes_passed") or 0.0)
        cfg = self._config(s)
        mc = cfg.get("monte_carlo", {})
        evidence = cfg.get("statistical_evidence", {})

        p_x10 = float(mc.get("p_x10_10d", mc.get("p_x10", 0.0)) or 0.0)
        p_ruin = float(mc.get("p_ruin_10d", mc.get("p_ruin", 0.0)) or 0.0)
        p95_dd = float(mc.get("p95_dd_10d", mc.get("p95_dd", dd)) or dd)
        wr_lb = float(evidence.get("wr_lower_bound_adjusted", 0.0) or 0.0)
        stable_ratio = float(stability.get("profitable_ratio", 0.0) or 0.0)

        score = 0.0
        score += min(max((pf - 1.0) / 1.5, 0.0), 1.0) * 22.0
        score += min(max((wr - 0.50) / 0.30, 0.0), 1.0) * 10.0
        score += min(max((wr_lb - 0.50) / 0.15, 0.0), 1.0) * 15.0
        score += max(0.0, 1.0 - dd / 0.35) * 11.0
        score += min(regimes / 3.0, 1.0) * 8.0
        score += min(stable_ratio, 1.0) * 12.0
        score += min(p_x10 / 0.25, 1.0) * 14.0
        score += max(0.0, 1.0 - p95_dd / 0.50) * 8.0
        score -= min(p_ruin / 0.10, 1.0) * 30.0
        if cfg.get("probation"):
            score -= 8.0
        if not mc:
            score -= 5.0
        return round(score, 4)

    def _build_portfolio(self, ids, corr, strat_map, scores, duplicate_of) -> List[str]:
        id_to_idx = {sid: i for i, sid in enumerate(ids)}
        ordered = sorted(ids, key=lambda sid: scores.get(sid, -999.0), reverse=True)
        portfolio = []
        family_counts = {}
        for sid in ordered:
            if len(portfolio) >= int(self.get_config("target_portfolio_size", self.TARGET_PORTFOLIO_SIZE)):
                break
            if sid in duplicate_of:
                continue
            family = strat_map[sid].get("family") or "unknown"
            if family_counts.get(family, 0) >= int(self.get_config("max_per_family", self.MAX_PER_FAMILY)):
                continue
            idx = id_to_idx[sid]
            max_corr = max(
                [abs(float(corr[idx, id_to_idx[e]])) for e in portfolio], default=0.0
            )
            threshold = float(self.get_config("portfolio_corr_threshold", self.PORTFOLIO_CORR_THRESHOLD))
            if portfolio and max_corr >= threshold:
                continue
            portfolio.append(sid)
            family_counts[family] = family_counts.get(family, 0) + 1
        return portfolio

    def _merge_config(self, sid: str, **values):
        row = self.db.fetchone("SELECT best_config FROM strategies WHERE id = ?", (sid,))
        cfg = {}
        if row and row["best_config"]:
            try:
                cfg = json.loads(row["best_config"]) if isinstance(row["best_config"], str) else dict(row["best_config"])
            except (json.JSONDecodeError, TypeError, ValueError):
                cfg = {}
        cfg.update(values)
        self.db.execute("UPDATE strategies SET best_config = ? WHERE id = ?", (json.dumps(cfg), sid))

    def _apply_portfolio_state(self, strategies, portfolio, scores, duplicate_of):
        selected = set(portfolio)
        for s in strategies:
            sid = s["id"]
            is_selected = sid in selected
            self.db.execute(
                "UPDATE strategies SET status = ? WHERE id = ?",
                ("validated" if is_selected else "portfolio_reserve", sid),
            )
            self._merge_config(
                sid, portfolio_selected=is_selected,
                portfolio_score=scores.get(sid, 0.0),
                redundant=(sid in duplicate_of), redundant_of=duplicate_of.get(sid),
            )

    def _store_portfolio_event(
        self, portfolio, scores, duplicate_of, total_trials,
        statistically_eligible: int, stable_count: int,
    ):
        ranked = sorted(portfolio, key=lambda sid: scores.get(sid, 0.0), reverse=True)
        self.emit_event(
            "milestone",
            f"Portfolio V4: {len(ranked)} selected | tested={total_trials} "
            f"statistical={statistically_eligible} stable={stable_count}",
            metadata={
                "type": "portfolio_composition_v4",
                "tested_universe": total_trials,
                "statistically_eligible": statistically_eligible,
                "chronologically_stable": stable_count,
                "strategies": ranked,
                "scores": {sid: scores[sid] for sid in ranked},
                "reserve_duplicates": duplicate_of,
                "count": len(ranked),
            },
        )
        self.logger.info(
            f"Portfolio V4: {len(ranked)} selected / {stable_count} stable / "
            f"{statistically_eligible} statistical / {total_trials} tested"
        )
