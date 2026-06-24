"""Evolution Agent: optimizes parameters, creates mutated/crossover variants of top strategies."""
import importlib.util
import json
import random
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from agents.base_agent import BaseAgent
from core.config import STRATEGIES_DIR
from engine.optimizer import composite_score


class EvolutionAgent(BaseAgent):
    """Selects top strategies, optimizes params, creates evolved variants."""

    name = "evolution_agent"

    def __init__(self, db):
        super().__init__(agent_id="evolution_agent", db=db)

    # ── lifecycle ──────────────────────────────────────────────────────────────

    def setup(self):
        self.logger.info("Evolution Agent ready")

    def tick(self):
        top = self._select_top_strategies(limit=10)
        if not top:
            self.logger.info("No strategies to evolve yet")
            return

        self.logger.info(f"Selected {len(top)} strategies for evolution")

        # 1. Mutation: create mutated copies of top strategies
        mutations_created = 0
        for strat in top[:5]:
            strategy_id = strat["id"]
            config = self._load_strategy_config(strategy_id)
            if config is None:
                continue
            mutated = self._mutate_params(config, mutation_rate=0.5, mutation_range=0.2)
            evo_id = self._next_evolution_id()
            self._create_evolved_strategy(
                evo_id=evo_id,
                parent_id=strategy_id,
                parent_generation=strat.get("generation", 1),
                params=mutated,
                family=strat.get("family", "evolved"),
                description=f"Mutation of {strategy_id}",
            )
            mutations_created += 1

        # 2. Crossover: pair top strategies and combine params
        crossovers_created = 0
        if len(top) >= 2:
            pairs = [(top[i], top[i + 1]) for i in range(0, min(len(top) - 1, 4), 2)]
            for parent_a, parent_b in pairs:
                config_a = self._load_strategy_config(parent_a["id"])
                config_b = self._load_strategy_config(parent_b["id"])
                if config_a is None or config_b is None:
                    continue
                child_params = self._crossover_params(config_a, config_b)
                evo_id = self._next_evolution_id()
                max_gen = max(parent_a.get("generation", 1), parent_b.get("generation", 1))
                self._create_evolved_strategy(
                    evo_id=evo_id,
                    parent_id=parent_a["id"],
                    parent_generation=max_gen,
                    params=child_params,
                    family=parent_a.get("family", "crossover"),
                    description=f"Crossover of {parent_a['id']} x {parent_b['id']}",
                )
                crossovers_created += 1

        # 3. Retire consistently poor strategies
        retired = self._retire_poor_strategies(min_runs=3, max_score=0.3)

        self.emit_event("info",
            f"Evolution tick: {mutations_created} mutations, {crossovers_created} crossovers, "
            f"{len(retired)} retired",
            metadata={"mutations": mutations_created, "crossovers": crossovers_created, "retired": retired},
        )

    def tick_interval(self) -> float:
        return self.get_config("tick_interval", 120)

    # ── selection ──────────────────────────────────────────────────────────────

    def _select_top_strategies(self, limit: int = 10) -> List[dict]:
        """
        Select top strategies by composite score, using the latest backtest
        results. Returns list of dicts with strategy info + 'score' key.
        """
        rows = self.db.fetchall(
            "SELECT s.id, s.family, s.generation, s.file_path, "
            "s.best_win_rate, s.best_profit_factor, s.best_max_drawdown, "
            "s.best_x10_count, s.best_final_balance, s.best_config "
            "FROM strategies s "
            "WHERE s.status NOT IN ('retired', 'deleted') "
            "AND s.best_profit_factor IS NOT NULL"
        )

        scored = []
        for r in rows:
            metrics = {
                "win_rate": r["best_win_rate"] or 0.0,
                "profit_factor": r["best_profit_factor"] or 0.0,
                "max_drawdown": r["best_max_drawdown"] or 1.0,
                "x10_count": r["best_x10_count"] or 0,
                "total_trades": 1,  # non-zero so score isn't auto-zeroed
            }
            score = composite_score(metrics)
            entry = dict(r)
            entry["score"] = score
            scored.append(entry)

        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:limit]

    # ── param manipulation ─────────────────────────────────────────────────────

    @staticmethod
    def _mutate_params(params: dict, mutation_rate: float = 0.5, mutation_range: float = 0.2) -> dict:
        """
        Create a mutated copy of params.

        Each numeric param has `mutation_rate` probability of being mutated
        by a random factor in [1 - mutation_range, 1 + mutation_range].
        Non-numeric params are copied unchanged. Values are clamped to > 0.
        """
        mutated = {}
        for key, value in params.items():
            if isinstance(value, (int, float)) and random.random() < mutation_rate:
                factor = 1.0 + random.uniform(-mutation_range, mutation_range)
                new_val = value * factor
                # Clamp to positive
                new_val = max(new_val, abs(value) * 0.01) if value != 0 else new_val
                # Preserve int type if original was int
                mutated[key] = int(round(new_val)) if isinstance(value, int) else round(new_val, 6)
            else:
                mutated[key] = value
        return mutated

    @staticmethod
    def _crossover_params(parent_a: dict, parent_b: dict) -> dict:
        """
        Uniform crossover: for each key, randomly pick from parent_a or parent_b.
        Keys only in one parent are copied from that parent.
        """
        all_keys = set(parent_a.keys()) | set(parent_b.keys())
        child = {}
        for key in all_keys:
            if key in parent_a and key in parent_b:
                child[key] = random.choice([parent_a[key], parent_b[key]])
            elif key in parent_a:
                child[key] = parent_a[key]
            else:
                child[key] = parent_b[key]
        return child

    # ── strategy loading ───────────────────────────────────────────────────────

    def _load_strategy_config(self, strategy_id: str) -> Optional[dict]:
        """Load PARAMS dict from a strategy's best_config or its source file."""
        row = self.db.fetchone(
            "SELECT best_config, file_path FROM strategies WHERE id = ?", (strategy_id,)
        )
        if row is None:
            return None

        # Try best_config from DB first
        if row["best_config"]:
            try:
                config = json.loads(row["best_config"]) if isinstance(row["best_config"], str) else row["best_config"]
                if isinstance(config, dict) and config:
                    return config
            except (json.JSONDecodeError, TypeError):
                pass

        # Fall back to loading PARAMS from the strategy file
        file_path = Path(row["file_path"])
        if not file_path.exists():
            return None
        try:
            spec = importlib.util.spec_from_file_location(f"strat_{strategy_id}", str(file_path))
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return dict(getattr(module, "PARAMS", {}))
        except Exception:
            return None

    # ── evolved strategy creation ──────────────────────────────────────────────

    def _create_evolved_strategy(
        self,
        evo_id: str,
        parent_id: str,
        parent_generation: int,
        params: dict,
        family: str,
        description: str,
    ):
        """
        Create an evolved strategy: write a wrapper .py file that imports
        the parent's generate_signals but overrides PARAMS, then register
        and queue for backtest.
        """
        # Load parent file path
        parent_row = self.db.fetchone("SELECT file_path FROM strategies WHERE id = ?", (parent_id,))
        if parent_row is None:
            self.logger.warning(f"Parent strategy {parent_id} not found")
            return

        parent_path = Path(parent_row["file_path"])
        if not parent_path.exists():
            self.logger.warning(f"Parent file {parent_path} does not exist")
            return

        # Read parent source and replace PARAMS line
        parent_code = parent_path.read_text(encoding="utf-8")

        # Build new PARAMS dict string
        params_str = "PARAMS = " + json.dumps(params, indent=4)

        # Replace the PARAMS definition in the parent code
        import re
        # Match PARAMS = { ... } (potentially multi-line)
        pattern = r"PARAMS\s*=\s*\{[^}]*\}"
        if re.search(pattern, parent_code, re.DOTALL):
            new_code = re.sub(pattern, params_str, parent_code, count=1, flags=re.DOTALL)
        else:
            # If no match, prepend PARAMS override
            new_code = params_str + "\n\n" + parent_code

        file_name = f"strategy_{evo_id.lower()}.py"
        file_path = STRATEGIES_DIR / file_name
        file_path.write_text(new_code, encoding="utf-8")

        new_gen = parent_generation + 1
        self.db.execute(
            "INSERT OR IGNORE INTO strategies "
            "(id, file_path, family, description, generation, parent_strategy, created_by, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (evo_id, str(file_path), family, description, new_gen, parent_id, self.agent_id, "candidate"),
        )

        self.post_task(
            target_agent="backtest_runner",
            task_type="backtest",
            payload={"strategy_id": evo_id, "file_path": str(file_path)},
            priority=5,
        )
        self.logger.info(f"Created evolved strategy {evo_id} (gen {new_gen}) from {parent_id}")

    # ── retirement ─────────────────────────────────────────────────────────────

    def _retire_poor_strategies(self, min_runs: int = 3, max_score: float = 0.3) -> list:
        """
        Retire strategies that have at least `min_runs` backtest results and
        whose best composite score is below `max_score`.

        Returns list of retired strategy IDs.
        """
        rows = self.db.fetchall(
            "SELECT s.id, s.best_win_rate, s.best_profit_factor, s.best_max_drawdown, "
            "s.best_x10_count, COUNT(b.id) as run_count "
            "FROM strategies s "
            "JOIN backtest_results b ON s.id = b.strategy_id "
            "WHERE s.status NOT IN ('retired', 'deleted', 'hall_of_fame') "
            "GROUP BY s.id "
            "HAVING run_count >= ?",
            (min_runs,),
        )

        retired = []
        for r in rows:
            metrics = {
                "win_rate": r["best_win_rate"] or 0.0,
                "profit_factor": r["best_profit_factor"] or 0.0,
                "max_drawdown": r["best_max_drawdown"] or 1.0,
                "x10_count": r["best_x10_count"] or 0,
                "total_trades": 1,
            }
            score = composite_score(metrics)
            if score < max_score:
                self.db.execute(
                    "UPDATE strategies SET status = 'retired' WHERE id = ?", (r["id"],)
                )
                retired.append(r["id"])
                self.logger.info(f"Retired strategy {r['id']} (score={score:.3f})")

        return retired

    # ── ID generation ──────────────────────────────────────────────────────────

    def _next_evolution_id(self) -> str:
        """Generate the next sequential evolved-strategy ID (E0001, E0002, …)."""
        row = self.db.fetchone(
            "SELECT id FROM strategies WHERE id LIKE 'E%' ORDER BY id DESC LIMIT 1"
        )
        if row:
            last_num = int(row["id"][1:])
            return f"E{last_num + 1:04d}"
        return "E0001"
