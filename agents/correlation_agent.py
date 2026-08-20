"""Portfolio selection agent.

Ranks validated strategies by robust edge, removes highly correlated clones,
and promotes only statistically credible diversified strategies to
``validated``. Good but non-selected strategies remain ``portfolio_reserve``.

The selector is the final deployment gate before paper trading. It therefore
adds a multiple-testing-aware confidence filter so a lucky winner among
thousands of trials is not treated like a genuinely established edge.
"""

import importlib.util
import json
import math
from pathlib import Path
from statistics import NormalDist
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from agents.base_agent import BaseAgent
from core.config import DATA_DIR, STRATEGIES_DIR


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

    def __init__(self, db):
        super().__init__(agent_id="correlation_agent", db=db)
        self._data_cache: Optional[pd.DataFrame] = None
        self._data_mtime: Optional[float] = None

    def setup(self):
        self.logger.info("Portfolio selector V3 ready — multiple-testing confidence gate active")

    def tick(self):
        total_trials = self._tested_strategy_count()
        strategies = self._get_candidates(total_trials)
        if len(strategies) < 2:
            self.logger.info(
                f"Portfolio selector: {len(strategies)} statistically eligible strategies "
                f"after {total_trials} tested candidates"
            )
            return

        df = self._load_data_m5()
        if df is None:
            self.logger.warning("No XAUUSD data available for portfolio selection")
            return

        signals = self._load_all_signals(strategies, df)
        if not signals:
            return

        ids = list(signals)
        corr = self._compute_correlation_matrix(signals)
        strat_map = {s["id"]: s for s in strategies}

        scores = {sid: self._score_strategy(strat_map[sid]) for sid in ids}
        clusters = self._find_clusters(ids, corr, self.HIGH_CORR_THRESHOLD)
        duplicate_of = self._best_per_cluster(clusters, scores)

        portfolio = self._build_portfolio(ids, corr, strat_map, scores, duplicate_of)
        self._apply_portfolio_state(strategies, portfolio, scores, duplicate_of)
        self._store_portfolio_event(portfolio, scores, duplicate_of, total_trials)

    def tick_interval(self) -> float:
        return self.get_config("tick_interval", 600)

    def _tested_strategy_count(self) -> int:
        row = self.db.fetchone(
            "SELECT COUNT(DISTINCT strategy_id) AS n FROM backtest_results"
        )
        return max(1, int(row["n"] or 0) if row else 1)

    def _latest_trade_count(self, strategy_id: str) -> int:
        row = self.db.fetchone(
            "SELECT total_trades FROM backtest_results WHERE strategy_id = ? "
            "ORDER BY run_at DESC, id DESC LIMIT 1",
            (strategy_id,),
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
        """Bonferroni-style family-wise error guard + effect-size floors.

        ``alpha / total_trials`` is intentionally conservative. We cap the
        resulting z-score to avoid numerical extremes once the research base
        becomes very large; holdout/WF/Monte-Carlo remain independent layers.
        """
        sid = s["id"]
        n = self._latest_trade_count(sid)
        wr = float(s.get("best_win_rate") or 0.0)
        pf = float(s.get("best_profit_factor") or 0.0)
        dd = float(s.get("best_max_drawdown") or 1.0)

        effective_alpha = max(1e-8, self.BASE_ALPHA / max(1, total_trials))
        z = NormalDist().inv_cdf(1.0 - effective_alpha / 2.0)
        z = min(max(z, 1.96), 4.5)
        wins = round(wr * n)
        wr_lb = self._wilson_lower_bound(wins, n, z)

        # Evidence requirement grows slowly with the number of experiments.
        # 60 baseline trades + 10 per decade of search breadth.
        adaptive_min_trades = self.MIN_CONFIDENCE_TRADES + int(
            10 * max(0.0, math.log10(max(1, total_trials)))
        )
        adaptive_pf = self.MIN_ADJUSTED_PF + min(
            0.15, 0.03 * max(0.0, math.log10(max(1, total_trials)))
        )

        passed = (
            n >= adaptive_min_trades
            and wr_lb >= self.MIN_ADJUSTED_WR_LB
            and pf >= adaptive_pf
            and dd <= self.MAX_ADJUSTED_DD
        )
        evidence = {
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
        return passed, evidence

    def _get_candidates(self, total_trials: int) -> List[dict]:
        rows = self.db.fetchall(
            "SELECT DISTINCT s.id, s.file_path, s.family, s.best_profit_factor, "
            "s.best_win_rate, s.best_max_drawdown, s.regimes_passed, "
            "s.best_x10_count, s.best_config, s.status "
            "FROM strategies s "
            "JOIN backtest_results b ON b.strategy_id = s.id "
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
            if not passed:
                continue
            result.append(s)
        return result

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
        rename = {"open": "Open", "high": "High", "low": "Low", "close": "Close",
                  "tick_volume": "Volume", "volume": "Volume"}
        df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})
        df = df.sort_values("time").set_index("time")
        agg = {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}
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

    def _load_all_signals(self, strategies: List[dict], df: pd.DataFrame) -> Dict[str, np.ndarray]:
        signals = {}
        for s in strategies:
            module = self._load_strategy_module(s["id"], s.get("file_path") or "")
            if module is None or not hasattr(module, "generate_signals"):
                continue
            try:
                params = getattr(module, "PARAMS", {})
                out = module.generate_signals(df.copy(), params)
                if "signal" not in out.columns:
                    continue
                sig = out["signal"].fillna(0).astype(float).to_numpy()
                if np.count_nonzero(sig) < 5:
                    continue
                signals[s["id"]] = sig
            except Exception as exc:
                self.logger.warning(f"Signal generation failed for {s['id']}: {exc}")
        return signals

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

    def _score_strategy(self, s: dict) -> float:
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

        score = 0.0
        score += min(max((pf - 1.0) / 1.5, 0.0), 1.0) * 25.0
        score += min(max((wr - 0.50) / 0.30, 0.0), 1.0) * 12.0
        score += min(max((wr_lb - 0.50) / 0.15, 0.0), 1.0) * 15.0
        score += max(0.0, 1.0 - dd / 0.35) * 13.0
        score += min(regimes / 3.0, 1.0) * 10.0
        score += min(p_x10 / 0.25, 1.0) * 15.0
        score += max(0.0, 1.0 - p95_dd / 0.50) * 10.0
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
            s = strat_map[sid]
            family = s.get("family") or "unknown"
            if family_counts.get(family, 0) >= int(self.get_config("max_per_family", self.MAX_PER_FAMILY)):
                continue

            idx = id_to_idx[sid]
            max_corr = 0.0
            for existing in portfolio:
                max_corr = max(max_corr, abs(float(corr[idx, id_to_idx[existing]])))
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
                sid,
                portfolio_selected=is_selected,
                portfolio_score=scores.get(sid, 0.0),
                redundant=(sid in duplicate_of),
                redundant_of=duplicate_of.get(sid),
            )

    def _store_portfolio_event(self, portfolio, scores, duplicate_of, total_trials):
        ranked = sorted(portfolio, key=lambda sid: scores.get(sid, 0.0), reverse=True)
        self.emit_event(
            "milestone",
            f"Portfolio selected: {len(portfolio)} statistically robust/diversified strategies "
            f"from {total_trials} tested candidates",
            metadata={
                "type": "portfolio_composition_v3",
                "tested_universe": total_trials,
                "strategies": ranked,
                "scores": {sid: scores[sid] for sid in ranked},
                "reserve_duplicates": duplicate_of,
                "count": len(ranked),
            },
        )
        self.logger.info(
            f"Portfolio V3: {len(ranked)} selected from {total_trials} tested; top={ranked[:10]}"
        )
