"""Strategy Analyzer: pure-statistics agent that diagnoses WHY strategies fail
and builds a knowledge base to inform future strategy creation."""
import json
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from agents.base_agent import BaseAgent
from core.config import LOG_DIR


class StrategyAnalyzer(BaseAgent):
    """Analyzes backtest results to identify failure patterns, optimal parameter
    ranges, and actionable insights — no LLM, pure statistical analysis."""

    name = "strategy_analyzer"

    def __init__(self, db):
        super().__init__(agent_id="strategy_analyzer", db=db)
        self.insights_path: Path = LOG_DIR / "strategy_insights.json"

    # ── lifecycle ─────────────────────────────────────────────────────────────

    def setup(self):
        self.logger.info("Strategy Analyzer ready — pure statistics mode")

    def tick_interval(self) -> float:
        return 300.0  # every 5 minutes

    def tick(self):
        results = self._fetch_all_results()
        if not results:
            self.logger.info("No backtest results to analyze yet")
            return

        strategies = self._fetch_all_strategies()
        strat_map = {s["id"]: dict(s) for s in strategies}

        # 1. Family-level performance analysis
        family_perf = self._analyze_family_performance(results, strat_map)

        # 2. Individual strategy failure diagnosis
        failure_modes = self._diagnose_failures(results, strat_map)

        # 3. SL/TP parameter range analysis
        sl_tp_analysis = self._analyze_sl_tp_ranges(results)

        # 4. Build and persist the knowledge base
        insights = self._generate_insights(family_perf, failure_modes, sl_tp_analysis, len(results))
        knowledge = {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "total_strategies_analyzed": len(set(r["strategy_id"] for r in results)),
            "total_backtests": len(results),
            "family_performance": family_perf,
            "best_sl_tp_ranges": sl_tp_analysis,
            "failure_modes": failure_modes["counts"],
            "failure_details": failure_modes["details"],
            "insights": insights,
        }
        self._save_knowledge(knowledge)

        # 5. Emit periodic summary event
        self._emit_summary(knowledge)

    # ── data fetching ─────────────────────────────────────────────────────────

    def _fetch_all_results(self) -> List[dict]:
        rows = self.db.fetchall(
            "SELECT id, strategy_id, win_rate, profit_factor, max_drawdown, "
            "x10_count, final_balance, total_trades, config, walk_forward, created_at "
            "FROM backtest_results ORDER BY created_at DESC"
        )
        return [dict(r) for r in rows] if rows else []

    def _fetch_all_strategies(self) -> List[dict]:
        rows = self.db.fetchall(
            "SELECT id, file_path, family, status, best_win_rate, best_profit_factor, "
            "best_max_drawdown, best_x10_count, best_final_balance, best_config, "
            "generation, created_by "
            "FROM strategies"
        )
        return [dict(r) for r in rows] if rows else []

    # ── 1. Family performance analysis ────────────────────────────────────────

    def _analyze_family_performance(self, results: List[dict], strat_map: Dict) -> Dict:
        """Group results by strategy family and compute aggregate statistics."""
        family_data: Dict[str, List[dict]] = defaultdict(list)

        for r in results:
            sid = r["strategy_id"]
            family = strat_map.get(sid, {}).get("family", "unknown")
            family_data[family].append(r)

        family_perf = {}
        for family, recs in family_data.items():
            wrs = [r["win_rate"] for r in recs if r["win_rate"] is not None]
            pfs = [r["profit_factor"] for r in recs if r["profit_factor"] is not None]
            dds = [r["max_drawdown"] for r in recs if r["max_drawdown"] is not None]
            balances = [r["final_balance"] for r in recs if r["final_balance"] is not None]
            trades = [r["total_trades"] for r in recs if r["total_trades"] is not None]
            x10s = [r["x10_count"] for r in recs if r["x10_count"] is not None]

            family_perf[family] = {
                "count": len(recs),
                "avg_wr": round(self._safe_mean(wrs), 4),
                "avg_pf": round(self._safe_mean(pfs), 4),
                "avg_dd": round(self._safe_mean(dds), 4),
                "avg_balance": round(self._safe_mean(balances), 2),
                "avg_trades": round(self._safe_mean(trades), 1),
                "avg_x10": round(self._safe_mean(x10s), 2),
                "max_pf": round(max(pfs), 4) if pfs else 0.0,
                "pf_above_1_pct": round(
                    sum(1 for pf in pfs if pf >= 1.0) / len(pfs) * 100, 1
                ) if pfs else 0.0,
                "std_wr": round(self._safe_stdev(wrs), 4),
                "std_pf": round(self._safe_stdev(pfs), 4),
            }

        return family_perf

    # ── 2. Individual failure diagnosis ───────────────────────────────────────

    def _diagnose_failures(self, results: List[dict], strat_map: Dict) -> Dict:
        """Classify each failing strategy into a failure mode."""
        mode_counts: Dict[str, int] = defaultdict(int)
        mode_details: Dict[str, List[dict]] = defaultdict(list)

        # Group results by strategy — use best result per strategy
        best_per_strategy: Dict[str, dict] = {}
        for r in results:
            sid = r["strategy_id"]
            pf = r["profit_factor"] if r["profit_factor"] is not None else 0.0
            if sid not in best_per_strategy or pf > (best_per_strategy[sid]["profit_factor"] or 0):
                best_per_strategy[sid] = r

        for sid, r in best_per_strategy.items():
            pf = r["profit_factor"] if r["profit_factor"] is not None else 0.0
            if pf >= 1.0:
                continue  # not a failure

            wr = r["win_rate"] if r["win_rate"] is not None else 0.0
            dd = r["max_drawdown"] if r["max_drawdown"] is not None else 1.0
            total = r["total_trades"] if r["total_trades"] is not None else 0
            config = self._parse_config(r.get("config"))
            sl_atr = config.get("sl_atr", 0) if config else 0
            tp_atr = config.get("tp_atr", 0) if config else 0
            family = strat_map.get(sid, {}).get("family", "unknown")

            # Classify failure mode
            mode = self._classify_failure(wr, pf, dd, total, sl_atr, tp_atr)
            mode_counts[mode] += 1
            mode_details[mode].append({
                "strategy_id": sid,
                "family": family,
                "win_rate": round(wr, 4),
                "profit_factor": round(pf, 4),
                "max_drawdown": round(dd, 4),
                "total_trades": total,
                "sl_atr": sl_atr,
                "tp_atr": tp_atr,
            })

        return {"counts": dict(mode_counts), "details": {k: v[:10] for k, v in mode_details.items()}}

    def _classify_failure(
        self, wr: float, pf: float, dd: float, total: int,
        sl_atr: float, tp_atr: float,
    ) -> str:
        """Return the primary failure mode for a strategy."""
        if total < 50:
            return "too_few_trades"

        # Spread drag: the SL is so tight that spread eats profit
        # With a typical 0.35 spread and sl_atr < 1.5, spread is > 20% of SL
        if sl_atr > 0 and tp_atr > 0:
            rr_ratio = tp_atr / sl_atr
            if sl_atr < 1.5 and pf < 0.8:
                return "spread_drag"
            if rr_ratio < 1.0 and wr < 0.65:
                return "spread_drag"

        if dd > 0.50:
            return "high_dd"

        if wr < 0.45:
            return "random_signals"

        if wr < 0.55:
            return "low_wr"

        # If WR is decent but PF still < 1.0, likely spread drag
        if wr >= 0.55 and pf < 1.0:
            return "spread_drag"

        return "low_wr"

    # ── 3. SL/TP parameter analysis ───────────────────────────────────────────

    def _analyze_sl_tp_ranges(self, results: List[dict]) -> Dict:
        """Find the SL/TP ranges correlated with positive performance."""
        profitable: List[Tuple[float, float, float]] = []  # (sl, tp, pf)
        all_sl: List[Tuple[float, float]] = []  # (sl, pf)
        all_tp: List[Tuple[float, float]] = []  # (tp, pf)

        for r in results:
            config = self._parse_config(r.get("config"))
            if not config:
                continue
            sl = config.get("sl_atr", 0)
            tp = config.get("tp_atr", 0)
            pf = r["profit_factor"] if r["profit_factor"] is not None else 0.0
            if sl <= 0 or tp <= 0:
                continue

            all_sl.append((sl, pf))
            all_tp.append((tp, pf))
            if pf >= 1.0:
                profitable.append((sl, tp, pf))

        if not all_sl:
            return {
                "min_viable_sl": 0.0,
                "optimal_sl_range": [0.0, 0.0],
                "optimal_tp_range": [0.0, 0.0],
                "sl_tp_correlation": {},
                "sample_size": 0,
            }

        # Find min SL that ever produced PF >= 1.0
        profitable_sls = [s for s, _, _ in profitable] if profitable else [0.0]
        profitable_tps = [t for _, t, _ in profitable] if profitable else [0.0]

        # Bucket analysis: group SL values into ranges and compute avg PF
        sl_buckets = self._bucket_analysis(all_sl, bucket_size=0.5)
        tp_buckets = self._bucket_analysis(all_tp, bucket_size=0.5)

        # Find the SL bucket with highest average PF
        best_sl_bucket = max(sl_buckets.items(), key=lambda x: x[1]["avg_pf"]) if sl_buckets else (0, {"avg_pf": 0})
        best_tp_bucket = max(tp_buckets.items(), key=lambda x: x[1]["avg_pf"]) if tp_buckets else (0, {"avg_pf": 0})

        return {
            "min_viable_sl": round(min(profitable_sls), 2) if profitable_sls[0] > 0 else 0.0,
            "optimal_sl_range": [
                round(min(profitable_sls), 2) if profitable_sls[0] > 0 else 0.0,
                round(max(profitable_sls), 2) if profitable_sls[0] > 0 else 0.0,
            ],
            "optimal_tp_range": [
                round(min(profitable_tps), 2) if profitable_tps[0] > 0 else 0.0,
                round(max(profitable_tps), 2) if profitable_tps[0] > 0 else 0.0,
            ],
            "sl_buckets": {str(k): v for k, v in sl_buckets.items()},
            "tp_buckets": {str(k): v for k, v in tp_buckets.items()},
            "best_sl_bucket": best_sl_bucket[0],
            "best_tp_bucket": best_tp_bucket[0],
            "sample_size": len(all_sl),
        }

    def _bucket_analysis(self, pairs: List[Tuple[float, float]], bucket_size: float) -> Dict:
        """Group (value, pf) pairs into buckets and compute avg PF per bucket."""
        buckets: Dict[float, List[float]] = defaultdict(list)
        for val, pf in pairs:
            bucket_key = round(int(val / bucket_size) * bucket_size, 2)
            buckets[bucket_key].append(pf)

        return {
            k: {
                "avg_pf": round(self._safe_mean(v), 4),
                "count": len(v),
                "pct_profitable": round(sum(1 for x in v if x >= 1.0) / len(v) * 100, 1),
            }
            for k, v in sorted(buckets.items())
        }

    # ── 4. Insight generation ─────────────────────────────────────────────────

    def _generate_insights(
        self, family_perf: Dict, failure_modes: Dict,
        sl_tp: Dict, total_results: int,
    ) -> List[str]:
        """Produce human-readable insight strings from the analysis."""
        insights: List[str] = []

        # SL threshold insight
        min_sl = sl_tp.get("min_viable_sl", 0)
        if min_sl > 0:
            insights.append(
                f"Strategies with sl_atr < {min_sl:.1f} have never achieved PF >= 1.0"
            )
        if min_sl >= 1.5:
            insights.append(
                "Strategies with sl_atr < 1.5 always blow account — spread drag dominates"
            )

        # Best SL/TP bucket
        best_sl = sl_tp.get("best_sl_bucket", 0)
        best_tp = sl_tp.get("best_tp_bucket", 0)
        if best_sl > 0:
            insights.append(
                f"Optimal SL bucket: sl_atr ~{best_sl:.1f} yields highest average PF"
            )
        if best_tp > 0:
            insights.append(
                f"Optimal TP bucket: tp_atr ~{best_tp:.1f} yields highest average PF"
            )

        # TP range insight
        tp_range = sl_tp.get("optimal_tp_range", [0, 0])
        if tp_range[0] > 0 and tp_range[1] > tp_range[0]:
            insights.append(
                f"Profitable strategies use tp_atr in [{tp_range[0]:.1f}, {tp_range[1]:.1f}]"
            )

        # Family insights — find best and worst
        if family_perf:
            sorted_families = sorted(
                family_perf.items(), key=lambda x: x[1]["avg_pf"], reverse=True
            )
            best_fam = sorted_families[0]
            if best_fam[1]["avg_pf"] > 0:
                insights.append(
                    f"Best family: '{best_fam[0]}' — avg PF {best_fam[1]['avg_pf']:.2f}, "
                    f"avg WR {best_fam[1]['avg_wr']:.1%}"
                )
            worst_fam = sorted_families[-1]
            if len(sorted_families) > 1:
                insights.append(
                    f"Worst family: '{worst_fam[0]}' — avg PF {worst_fam[1]['avg_pf']:.2f}, "
                    f"avg WR {worst_fam[1]['avg_wr']:.1%}"
                )

            # Families with high WR but low PF => spread drag candidates
            for fam, stats in family_perf.items():
                if stats["avg_wr"] >= 0.60 and stats["avg_pf"] < 1.0 and stats["count"] >= 3:
                    insights.append(
                        f"Family '{fam}' has decent WR ({stats['avg_wr']:.1%}) but low PF "
                        f"({stats['avg_pf']:.2f}) — likely spread drag, widen SL/TP"
                    )

            # Families with high variance
            for fam, stats in family_perf.items():
                if stats["std_pf"] > 0.5 and stats["count"] >= 5:
                    insights.append(
                        f"Family '{fam}' has high PF variance (std={stats['std_pf']:.2f}) — "
                        f"results are unstable, needs parameter narrowing"
                    )

        # Failure mode insights
        fm_counts = failure_modes.get("counts", {})
        total_failures = sum(fm_counts.values())
        if total_failures > 0:
            dominant = max(fm_counts.items(), key=lambda x: x[1])
            pct = dominant[1] / total_failures * 100
            insights.append(
                f"Dominant failure mode: '{dominant[0]}' — {dominant[1]}/{total_failures} "
                f"({pct:.0f}%) of failing strategies"
            )
            if fm_counts.get("spread_drag", 0) > total_failures * 0.4:
                insights.append(
                    "Over 40% of failures are spread-drag — system should increase "
                    "minimum sl_atr to at least 2.0"
                )
            if fm_counts.get("random_signals", 0) > total_failures * 0.3:
                insights.append(
                    "Over 30% of failures have random signals (WR < 45%) — signal "
                    "quality filters needed before backtesting"
                )

        return insights

    # ── 5. Periodic summary emission ──────────────────────────────────────────

    def _emit_summary(self, knowledge: Dict):
        """Emit an event summarizing key findings."""
        n_strats = knowledge["total_strategies_analyzed"]
        n_tests = knowledge["total_backtests"]
        fm = knowledge.get("failure_modes", {})
        n_insights = len(knowledge.get("insights", []))
        sl_tp = knowledge.get("best_sl_tp_ranges", {})

        summary_parts = [
            f"Analyzed {n_strats} strategies ({n_tests} backtests)",
            f"Failure modes: {json.dumps(fm)}",
            f"Optimal SL range: {sl_tp.get('optimal_sl_range', 'N/A')}",
            f"Optimal TP range: {sl_tp.get('optimal_tp_range', 'N/A')}",
            f"Generated {n_insights} insights",
        ]
        summary = " | ".join(summary_parts)

        self.emit_event("analysis", summary, metadata={
            "total_strategies": n_strats,
            "total_backtests": n_tests,
            "failure_modes": fm,
            "insights_count": n_insights,
        })

        # Log top insights
        for insight in knowledge.get("insights", [])[:5]:
            self.logger.info(f"Insight: {insight}")

    # ── persistence ───────────────────────────────────────────────────────────

    def _save_knowledge(self, knowledge: Dict):
        """Write the knowledge base to disk as JSON."""
        try:
            self.insights_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.insights_path, "w", encoding="utf-8") as f:
                json.dump(knowledge, f, indent=2, default=str)
            self.logger.info(f"Knowledge base saved to {self.insights_path}")
        except Exception as e:
            self.logger.error(f"Failed to save knowledge base: {e}")

    # ── helpers ───────────────────────────────────────────────────────────────

    def _parse_config(self, raw: Any) -> Optional[Dict]:
        """Safely parse a config column (may be JSON string or dict)."""
        if raw is None:
            return None
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, str):
            try:
                return json.loads(raw)
            except (json.JSONDecodeError, ValueError):
                return None
        return None

    @staticmethod
    def _safe_mean(values: List[float]) -> float:
        return statistics.mean(values) if values else 0.0

    @staticmethod
    def _safe_stdev(values: List[float]) -> float:
        return statistics.stdev(values) if len(values) >= 2 else 0.0
