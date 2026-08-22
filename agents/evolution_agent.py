"""Evolution Agent V2: mutate proven edges without contaminating strategy PARAMS."""
import importlib.util
import json
import random
import re
from pathlib import Path
from typing import List, Optional

from agents.base_agent import BaseAgent
from core.config import STRATEGIES_DIR


class EvolutionAgent(BaseAgent):
    """Create directed descendants of statistically promising strategies."""

    name = "evolution_agent"

    def __init__(self, db):
        super().__init__(agent_id="evolution_agent", db=db)

    def setup(self):
        self.logger.info("Evolution Agent V2 ready")

    def tick(self):
        top = self._select_top_strategies(limit=12)
        if not top:
            self.logger.info("No strategies worth evolving yet")
            return

        pending = self.db.fetchone(
            "SELECT COUNT(*) AS cnt FROM strategies s "
            "LEFT JOIN backtest_results b ON s.id=b.strategy_id "
            "WHERE s.status='candidate' AND b.id IS NULL AND s.created_by='evolution_agent'"
        )
        max_pending = int(self.get_config("max_pending", 300))
        if pending and int(pending["cnt"] or 0) >= max_pending:
            self.logger.info(f"Evolution queue full ({pending['cnt']}/{max_pending})")
            return

        mutations = 0
        # Spread mutations across different families when possible.
        chosen = []
        used_families = set()
        for s in top:
            fam = s.get("family") or "unknown"
            if fam not in used_families:
                chosen.append(s)
                used_families.add(fam)
            if len(chosen) >= 6:
                break
        if len(chosen) < 6:
            for s in top:
                if s not in chosen:
                    chosen.append(s)
                if len(chosen) >= 6:
                    break

        for strat in chosen:
            sid = strat["id"]
            params = self._load_strategy_params(sid)
            if not params:
                continue

            trades = int(strat.get("total_trades") or 0)
            pf = float(strat.get("best_profit_factor") or 0.0)
            p_x10 = float(strat.get("p_x10_10d") or 0.0)

            # High-quality low-frequency parents are close to useful. Preserve
            # the edge and make only a SMALL move toward more frequency. The
            # previous broad relaxation frequently jumped from ~40 trades to
            # 200+ and destroyed PF/WR.
            if pf >= 1.5 and 0 < trades < 100:
                child = self._mutate_params(params, 0.18, 0.06)
                child = self._relax_entry_thresholds(child)
                desc = f"Gentle frequency-directed V2 mutation of {sid}"
            else:
                # Strong x10 candidates get gentler local search; ordinary
                # promising parents get broader exploration.
                if p_x10 >= 0.05:
                    child = self._mutate_params(params, 0.30, 0.12)
                else:
                    child = self._mutate_params(params, 0.45, 0.18)
                desc = f"Edge-directed V2 mutation of {sid}"

            evo_id = self._next_evolution_id()
            if self._create_evolved_strategy(
                evo_id, sid, int(strat.get("generation") or 1), child,
                strat.get("family") or "evolved", desc,
            ):
                mutations += 1

        # Crossover is allowed only inside the SAME family. Mixing unrelated
        # parameter vocabularies was generating nonsensical children.
        crossovers = 0
        pair = self._best_same_family_pair(top)
        if pair:
            a, b = pair
            pa = self._load_strategy_params(a["id"])
            pb = self._load_strategy_params(b["id"])
            if pa and pb:
                shared = set(pa) & set(pb)
                # Require meaningful parameter overlap before crossover.
                overlap = len(shared) / max(1, min(len(pa), len(pb)))
                if overlap >= 0.60:
                    child = self._crossover_params(pa, pb)
                    evo_id = self._next_evolution_id()
                    if self._create_evolved_strategy(
                        evo_id, a["id"], max(int(a.get("generation") or 1), int(b.get("generation") or 1)),
                        child, a.get("family") or "crossover",
                        f"Same-family V2 crossover {a['id']} x {b['id']}",
                    ):
                        crossovers = 1

        self.emit_event(
            "info",
            f"Evolution V2: {mutations} mutations, {crossovers} crossover",
            metadata={"mutations": mutations, "crossovers": crossovers},
        )

    def tick_interval(self) -> float:
        return self.get_config("tick_interval", 120)

    def _select_top_strategies(self, limit: int = 12) -> List[dict]:
        """Rank parents by edge + robustness + X10 potential - ruin."""
        rows = self.db.fetchall(
            "SELECT s.id, s.family, s.generation, s.file_path, s.best_win_rate, "
            "s.best_profit_factor, s.best_max_drawdown, s.best_config, "
            "MAX(b.total_trades) AS total_trades "
            "FROM strategies s LEFT JOIN backtest_results b ON b.strategy_id=s.id "
            "WHERE s.status IN ('validated','portfolio_reserve','candidate') "
            "AND s.best_profit_factor IS NOT NULL "
            "GROUP BY s.id"
        )
        scored = []
        for row in rows:
            s = dict(row)
            if not self._resolve_path(s.get("file_path"), s["id"]):
                continue
            pf = float(s.get("best_profit_factor") or 0.0)
            wr = float(s.get("best_win_rate") or 0.0)
            dd = float(s.get("best_max_drawdown") or 1.0)
            if pf < 1.05 or wr <= 0:
                continue

            cfg = self._parse_json(s.get("best_config"))
            mc = cfg.get("monte_carlo", {}) if isinstance(cfg, dict) else {}
            p_x10 = float(mc.get("p_x10_10d", mc.get("p_x10", 0.0)) or 0.0)
            p_ruin = float(mc.get("p_ruin_10d", mc.get("p_ruin", 0.0)) or 0.0)
            p95dd = float(mc.get("p95_dd_10d", mc.get("p95_dd", dd)) or dd)

            score = 0.0
            score += min(max((pf - 1.0) / 1.5, 0.0), 1.0) * 35.0
            score += min(max((wr - 0.50) / 0.30, 0.0), 1.0) * 20.0
            score += max(0.0, 1.0 - dd / 0.35) * 15.0
            score += min(p_x10 / 0.25, 1.0) * 20.0
            score += max(0.0, 1.0 - p95dd / 0.50) * 10.0
            score -= min(p_ruin / 0.10, 1.0) * 35.0
            if cfg.get("probation"):
                score -= 5.0

            s["score"] = round(score, 4)
            s["p_x10_10d"] = p_x10
            s["p_ruin_10d"] = p_ruin
            scored.append(s)

        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:limit]

    @staticmethod
    def _parse_json(value) -> dict:
        if isinstance(value, dict):
            return value
        if not value:
            return {}
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except (json.JSONDecodeError, TypeError):
            return {}

    @staticmethod
    def _resolve_path(file_path: Optional[str], strategy_id: str) -> Optional[Path]:
        candidates = []
        if file_path:
            p = Path(file_path)
            candidates.extend([p, STRATEGIES_DIR.parent / p])
        candidates.append(STRATEGIES_DIR / f"strategy_{strategy_id.lower()}.py")
        return next((p for p in candidates if p.exists()), None)

    def _load_strategy_params(self, strategy_id: str) -> Optional[dict]:
        """Load ONLY executable PARAMS from source; never best_config metadata."""
        row = self.db.fetchone("SELECT file_path FROM strategies WHERE id=?", (strategy_id,))
        if not row:
            return None
        path = self._resolve_path(row["file_path"], strategy_id)
        if path is None:
            return None
        try:
            spec = importlib.util.spec_from_file_location(f"strat_{strategy_id}", str(path))
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            params = getattr(module, "PARAMS", None)
            return dict(params) if isinstance(params, dict) else None
        except Exception as exc:
            self.logger.warning(f"Could not load PARAMS for {strategy_id}: {exc}")
            return None

    @staticmethod
    def _relax_entry_thresholds(params: dict) -> dict:
        """Gently increase frequency while preserving a proven parent edge.

        This deliberately makes only small threshold moves. Session bounds are
        left unchanged and cooldown is reduced by at most one bar.
        """
        p = dict(params)
        for k in ("rsi_low", "mfi_low", "uo_low", "stoch_low", "cci_low"):
            if isinstance(p.get(k), (int, float)):
                p[k] = round(p[k] + random.uniform(0.5, 2.0), 4)
        for k in ("rsi_high", "mfi_high", "uo_high", "stoch_high", "cci_high"):
            if isinstance(p.get(k), (int, float)):
                p[k] = round(p[k] - random.uniform(0.5, 2.0), 4)
        if isinstance(p.get("bb_std"), (int, float)):
            p["bb_std"] = round(max(1.2, p["bb_std"] - random.uniform(0.03, 0.12)), 4)
        for k in ("adx_threshold", "adx_floor"):
            if isinstance(p.get(k), (int, float)):
                p[k] = max(12, int(round(p[k] - random.uniform(0.5, 2.0))))
        if isinstance(p.get("cooldown"), (int, float)):
            current = max(1, int(round(p["cooldown"])))
            p["cooldown"] = max(1, current - random.choice((0, 0, 1)))
        return p

    @staticmethod
    def _mutate_params(params: dict, mutation_rate: float, mutation_range: float) -> dict:
        child = {}
        # Preserve execution geometry/frequency controls during generic
        # mutation. Frequency-directed mutations adjust cooldown separately
        # and never mutate the trading session window.
        protected = {"sl_atr", "tp_atr", "cooldown", "session_start", "session_end"}
        for key, value in params.items():
            if isinstance(value, bool):
                child[key] = value
                continue
            if isinstance(value, (int, float)) and random.random() < mutation_rate:
                local_range = min(mutation_range, 0.05) if key in protected else mutation_range
                factor = 1.0 + random.uniform(-local_range, local_range)
                nv = value * factor
                if value > 0:
                    nv = max(nv, max(0.0001, value * 0.10))
                child[key] = int(round(nv)) if isinstance(value, int) else round(float(nv), 6)
            else:
                child[key] = value
        # Preserve sane risk/reward geometry.
        if isinstance(child.get("sl_atr"), (int, float)):
            child["sl_atr"] = max(0.3, min(float(child["sl_atr"]), 5.0))
        if isinstance(child.get("tp_atr"), (int, float)):
            child["tp_atr"] = max(0.4, min(float(child["tp_atr"]), 10.0))
        return child

    @staticmethod
    def _crossover_params(a: dict, b: dict) -> dict:
        child = {}
        for key in set(a) | set(b):
            if key in a and key in b:
                child[key] = random.choice((a[key], b[key]))
            elif key in a:
                child[key] = a[key]
            else:
                child[key] = b[key]
        return child

    @staticmethod
    def _best_same_family_pair(top: List[dict]):
        for i, a in enumerate(top):
            for b in top[i + 1:]:
                if a.get("family") == b.get("family"):
                    return a, b
        return None

    def _create_evolved_strategy(self, evo_id, parent_id, parent_generation, params, family, description) -> bool:
        row = self.db.fetchone("SELECT file_path FROM strategies WHERE id=?", (parent_id,))
        if not row:
            return False
        parent_path = self._resolve_path(row["file_path"], parent_id)
        if parent_path is None:
            return False

        parent_code = parent_path.read_text(encoding="utf-8")
        params_str = "PARAMS = " + repr(params)
        pattern = r"PARAMS\s*=\s*\{[^}]*\}"
        if not re.search(pattern, parent_code, re.DOTALL):
            self.logger.warning(f"No replaceable PARAMS dict in {parent_id}; child skipped")
            return False
        new_code = re.sub(pattern, params_str, parent_code, count=1, flags=re.DOTALL)
        try:
            compile(new_code, f"<evolved:{evo_id}>", "exec")
        except SyntaxError as exc:
            self.logger.warning(f"Evolved child {evo_id} invalid: {exc}")
            return False

        file_name = f"strategy_{evo_id.lower()}.py"
        file_path = STRATEGIES_DIR / file_name
        file_path.write_text(new_code, encoding="utf-8")
        self.db.execute(
            "INSERT OR IGNORE INTO strategies "
            "(id,file_path,family,description,generation,parent_strategy,created_by,status) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (evo_id, str(file_path), family, description, parent_generation + 1,
             parent_id, self.agent_id, "candidate"),
        )
        # The parallel backtest runner already discovers every untested
        # candidate directly. Posting a second task here caused duplicate
        # simulations/results for the same strategy, so no task is queued.
        self.logger.info(f"Created {evo_id} from {parent_id}")
        return True

    def _next_evolution_id(self) -> str:
        rows = self.db.fetchall("SELECT id FROM strategies WHERE id LIKE 'E%' AND id NOT LIKE 'ENS%'")
        nums = []
        for row in rows:
            try:
                nums.append(int(row["id"][1:]))
            except (ValueError, TypeError):
                continue
        return f"E{max(nums, default=0) + 1:04d}"
