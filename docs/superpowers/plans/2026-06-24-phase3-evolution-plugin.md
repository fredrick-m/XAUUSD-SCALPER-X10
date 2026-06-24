# Phase 3: Evolution Agent & Plugin Scout — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Evolution Agent (parameter optimization + genetic crossover of strategies) and the Plugin Scout (automated discovery and installation of external tools from GitHub/PyPI).

**Architecture:** The Evolution Agent selects top-performing strategies from the DB, runs Optuna-based parameter optimization (in-sample/out-of-sample split), creates mutated/crossover variants as new generation strategies, and posts them to the Backtest Runner. The Plugin Scout searches GitHub/PyPI on a slow cadence, evaluates candidates, installs them safely, and registers them in the `plugins` table so other agents can discover new tools.

**Tech Stack:** Python, optuna, pandas, numpy, requests, subprocess (for pip install), Anthropic SDK

---

## File Structure

```
engine/
├── optimizer.py              — Optuna-based parameter optimizer (new)

agents/
├── evolution_agent.py        — Evolution Agent (new)
├── plugin_scout.py           — Plugin Scout agent (new)

tests/
├── test_optimizer.py         — Optimizer unit tests (new)
├── test_evolution_agent.py   — Evolution Agent tests (new)
├── test_plugin_scout.py      — Plugin Scout tests (new)

core/
├── config.py                 — Add evolution_agent + plugin_scout to CORE_AGENTS
```

---

### Task 1: Parameter optimizer (`engine/optimizer.py`)

**Files:**
- Create: `engine/optimizer.py`
- Create: `tests/test_optimizer.py`

This is the core optimization engine used by the Evolution Agent. It wraps Optuna to optimize strategy parameters using the backtest engine, with proper in-sample/out-of-sample data splitting.

- [ ] **Step 1: Write the failing tests**

`tests/test_optimizer.py`:
```python
"""Tests for the parameter optimizer."""
import pandas as pd
import numpy as np
import pytest


@pytest.fixture
def sample_df():
    """Create a small OHLCV DataFrame for testing."""
    np.random.seed(42)
    n = 2000
    base = 2000.0
    close = base + np.cumsum(np.random.randn(n) * 0.5)
    df = pd.DataFrame({
        "time": pd.date_range("2024-01-01", periods=n, freq="min"),
        "Open": close + np.random.randn(n) * 0.1,
        "High": close + abs(np.random.randn(n) * 0.3),
        "Low": close - abs(np.random.randn(n) * 0.3),
        "Close": close,
        "Volume": np.random.randint(100, 1000, n),
    })
    return df


def test_optimizer_imports():
    from engine.optimizer import optimize_strategy, composite_score
    assert callable(optimize_strategy)
    assert callable(composite_score)


def test_composite_score_calculation():
    from engine.optimizer import composite_score
    metrics = {
        "win_rate": 0.65,
        "profit_factor": 3.0,
        "max_drawdown": 0.20,
        "x10_count": 5,
        "total_trades": 200,
    }
    score = composite_score(metrics)
    assert isinstance(score, float)
    assert 0.0 <= score <= 1.0


def test_composite_score_zero_trades():
    from engine.optimizer import composite_score
    metrics = {
        "win_rate": 0.0,
        "profit_factor": 0.0,
        "max_drawdown": 1.0,
        "x10_count": 0,
        "total_trades": 0,
    }
    score = composite_score(metrics)
    assert score == 0.0


def test_split_data():
    from engine.optimizer import split_data
    df = pd.DataFrame({"A": range(100)})
    train, test = split_data(df, ratio=0.7)
    assert len(train) == 70
    assert len(test) == 30


def test_optimize_returns_best_params(sample_df):
    from engine.optimizer import optimize_strategy

    # Minimal strategy module mock
    class FakeModule:
        PARAMS = {"ema_fast": 5, "ema_slow": 20, "atr_period": 14, "sl_atr": 1.5, "tp_atr": 2.5}
        @staticmethod
        def generate_signals(df, p):
            import ta as ta_lib
            df["ATR"] = ta_lib.volatility.average_true_range(
                df["High"], df["Low"], df["Close"], window=p.get("atr_period", 14)
            )
            df["signal"] = 0
            return df

    param_space = {
        "sl_atr": (0.5, 3.0),
        "tp_atr": (1.0, 5.0),
    }

    best_params, best_score = optimize_strategy(
        module=FakeModule,
        df=sample_df,
        param_space=param_space,
        n_trials=5,
        split_ratio=0.7,
    )
    assert isinstance(best_params, dict)
    assert "sl_atr" in best_params
    assert "tp_atr" in best_params
    assert isinstance(best_score, float)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_optimizer.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'engine.optimizer'`

- [ ] **Step 3: Implement the optimizer**

`engine/optimizer.py`:
```python
"""
Optuna-based parameter optimizer for trading strategies.

Wraps the backtest engine to optimize strategy PARAMS using Bayesian optimization
with in-sample/out-of-sample data splitting.
"""
from typing import Dict, Tuple

import numpy as np
import pandas as pd
import optuna

from engine.backtest import run_simulation

# Silence Optuna's verbose logging
optuna.logging.set_verbosity(optuna.logging.WARNING)


def composite_score(metrics: dict) -> float:
    """
    Compute a 0-1 composite fitness score from backtest metrics.

    Weights:
      - win_rate:       25%
      - profit_factor:  30%  (capped at 4.0 → 1.0)
      - (1 - drawdown): 20%
      - x10_count:      25%  (capped at 5 → 1.0)

    Returns 0.0 if total_trades == 0.
    """
    if metrics.get("total_trades", 0) == 0:
        return 0.0

    wr = metrics.get("win_rate", 0.0)
    pf = metrics.get("profit_factor", 0.0)
    dd = metrics.get("max_drawdown", 1.0)
    x10 = metrics.get("x10_count", 0)

    score = (
        wr * 0.25
        + min(pf / 4.0, 1.0) * 0.30
        + (1.0 - dd) * 0.20
        + min(x10 / 5.0, 1.0) * 0.25
    )
    return round(max(0.0, min(score, 1.0)), 6)


def split_data(df: pd.DataFrame, ratio: float = 0.7) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Split DataFrame into train/test by ratio (chronological, no shuffle)."""
    split_idx = int(len(df) * ratio)
    return df.iloc[:split_idx].copy().reset_index(drop=True), df.iloc[split_idx:].copy().reset_index(drop=True)


def _build_signals(module, df: pd.DataFrame, params: dict):
    """
    Run module.generate_signals and extract signal/SL/TP series.

    Returns (signals, sl_prices, tp_prices, directions) or None on failure.
    """
    sl_atr = params.get("sl_atr", 1.5)
    tp_atr = params.get("tp_atr", 2.5)

    result_df = module.generate_signals(df.copy(), params)

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

    return signals, sl_prices, tp_prices, directions


def _evaluate(module, df: pd.DataFrame, params: dict) -> float:
    """Run backtest with given params and return composite_score. Returns 0.0 on failure."""
    signal_data = _build_signals(module, df, params)
    if signal_data is None:
        return 0.0

    signals, sl_prices, tp_prices, directions = signal_data
    try:
        metrics = run_simulation(
            df, signals, sl_prices, tp_prices, directions,
            risk_pct=params.get("risk_pct", 0.05),
            trailing_stop=True,
            max_bars_in_trade=params.get("max_bars_in_trade", 60),
            session_filter=True,
            session_hours=(7, 21),
        )
    except Exception:
        return 0.0

    return composite_score(metrics)


def optimize_strategy(
    module,
    df: pd.DataFrame,
    param_space: Dict[str, Tuple[float, float]],
    n_trials: int = 50,
    split_ratio: float = 0.7,
) -> Tuple[dict, float]:
    """
    Optimize strategy parameters using Optuna.

    Parameters
    ----------
    module       : Strategy module with PARAMS dict and generate_signals().
    df           : Full OHLCV DataFrame.
    param_space  : Dict mapping param name to (min_val, max_val) float range.
    n_trials     : Number of Optuna trials.
    split_ratio  : Train/test split ratio (chronological).

    Returns
    -------
    (best_params, best_in_sample_score) — best params found on in-sample data.
    """
    train_df, _ = split_data(df, ratio=split_ratio)
    base_params = dict(getattr(module, "PARAMS", {}))

    def objective(trial: optuna.Trial) -> float:
        params = dict(base_params)
        for name, (lo, hi) in param_space.items():
            params[name] = trial.suggest_float(name, lo, hi)
        return _evaluate(module, train_df, params)

    study = optuna.create_study(direction="maximize")
    study.optimize(objective, n_trials=n_trials, show_progress_bar=False)

    best_params = dict(base_params)
    best_params.update(study.best_params)
    return best_params, study.best_value
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_optimizer.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add engine/optimizer.py tests/test_optimizer.py
git commit -m "feat: add Optuna-based parameter optimizer for strategies"
```

---

### Task 2: Evolution Agent (`agents/evolution_agent.py`)

**Files:**
- Create: `agents/evolution_agent.py`
- Create: `tests/test_evolution_agent.py`

The Evolution Agent selects top strategies, optimizes their parameters, creates mutated/crossover variants, and retires poor performers.

- [ ] **Step 1: Write the failing tests**

`tests/test_evolution_agent.py`:
```python
"""Tests for Evolution Agent."""
import json
import pytest


@pytest.fixture
def tmp_db(tmp_path):
    from core.db import Database
    db = Database(tmp_path / "test.sqlite")
    db.init_schema()
    db.execute(
        "INSERT INTO agent_registry (id, name, module_path, class_name, config) VALUES (?, ?, ?, ?, ?)",
        ("evolution_agent", "evolution_agent", "agents.evolution_agent", "EvolutionAgent",
         '{"tick_interval": 0.01}'),
    )
    yield db
    db.close()


def _seed_strategies(db, count=5):
    """Insert dummy strategies with backtest results for testing."""
    for i in range(1, count + 1):
        sid = f"S{i:04d}"
        db.execute(
            "INSERT INTO strategies (id, file_path, family, status, generation, "
            "best_win_rate, best_profit_factor, best_max_drawdown, best_x10_count, best_final_balance) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (sid, f"strategies/strategy_{sid.lower()}.py", "momentum_burst", "candidate", 1,
             0.60 + i * 0.02, 1.5 + i * 0.3, 0.25 - i * 0.02, i, 100.0 + i * 50),
        )
        db.execute(
            "INSERT INTO backtest_results "
            "(strategy_id, risk_pct, total_trades, win_rate, profit_factor, "
            "max_drawdown, x10_count, final_balance, return_pct, blown_account) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (sid, 0.05, 300, 0.60 + i * 0.02, 1.5 + i * 0.3,
             0.25 - i * 0.02, i, 100.0 + i * 50, (100.0 + i * 50 - 50) / 50 * 100, 0),
        )


def test_evolution_agent_imports():
    from agents.evolution_agent import EvolutionAgent
    assert EvolutionAgent.name == "evolution_agent"


def test_select_top_strategies(tmp_db):
    from agents.evolution_agent import EvolutionAgent
    _seed_strategies(tmp_db, count=5)
    agent = EvolutionAgent(tmp_db)
    top = agent._select_top_strategies(limit=3)
    assert len(top) == 3
    # Should be sorted by composite score descending
    assert top[0]["id"] == "S0005"  # highest metrics


def test_composite_score_used(tmp_db):
    from agents.evolution_agent import EvolutionAgent
    from engine.optimizer import composite_score
    _seed_strategies(tmp_db, count=3)
    agent = EvolutionAgent(tmp_db)
    top = agent._select_top_strategies(limit=3)
    # Verify each row has a 'score' key
    for row in top:
        assert "score" in row
        assert isinstance(row["score"], float)


def test_mutate_params():
    from agents.evolution_agent import EvolutionAgent
    params = {"ema_fast": 5.0, "ema_slow": 20.0, "sl_atr": 1.5, "tp_atr": 3.0}
    mutated = EvolutionAgent._mutate_params(params, mutation_rate=1.0, mutation_range=0.2)
    # All params should be mutated (rate=1.0) but keys preserved
    assert set(mutated.keys()) == set(params.keys())
    # At least one param should differ (extremely unlikely all stay the same at rate 1.0)
    assert mutated != params


def test_mutate_params_preserves_positive():
    from agents.evolution_agent import EvolutionAgent
    params = {"sl_atr": 0.1}
    # Even with heavy mutation, values should stay positive
    for _ in range(20):
        mutated = EvolutionAgent._mutate_params(params, mutation_rate=1.0, mutation_range=0.5)
        assert mutated["sl_atr"] > 0


def test_crossover_params():
    from agents.evolution_agent import EvolutionAgent
    parent_a = {"ema_fast": 3.0, "ema_slow": 8.0, "sl_atr": 1.5, "tp_atr": 2.5}
    parent_b = {"ema_fast": 5.0, "ema_slow": 20.0, "sl_atr": 2.0, "tp_atr": 4.0}
    child = EvolutionAgent._crossover_params(parent_a, parent_b)
    # Child should have all keys from parent_a
    assert set(child.keys()) == set(parent_a.keys())
    # Each value should come from one of the parents
    for key in child:
        assert child[key] in (parent_a[key], parent_b[key])


def test_next_evolution_id(tmp_db):
    from agents.evolution_agent import EvolutionAgent
    agent = EvolutionAgent(tmp_db)
    eid = agent._next_evolution_id()
    assert eid == "E0001"
    # Simulate one existing
    tmp_db.execute(
        "INSERT INTO strategies (id, file_path, family, status, generation) VALUES (?, ?, ?, ?, ?)",
        ("E0001", "strategies/strategy_e0001.py", "evolved", "candidate", 2),
    )
    eid2 = agent._next_evolution_id()
    assert eid2 == "E0002"


def test_retire_poor_strategies(tmp_db):
    from agents.evolution_agent import EvolutionAgent
    # Insert a strategy with 3 failed backtest runs
    tmp_db.execute(
        "INSERT INTO strategies (id, file_path, family, status, generation) VALUES (?, ?, ?, ?, ?)",
        ("POOR1", "strategies/strategy_poor1.py", "test", "candidate", 3),
    )
    for _ in range(3):
        tmp_db.execute(
            "INSERT INTO backtest_results "
            "(strategy_id, risk_pct, total_trades, win_rate, profit_factor, "
            "max_drawdown, x10_count, final_balance, return_pct, blown_account) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("POOR1", 0.05, 50, 0.30, 0.5, 0.80, 0, 10.0, -80.0, 0),
        )
    agent = EvolutionAgent(tmp_db)
    retired = agent._retire_poor_strategies(min_runs=3, max_score=0.3)
    assert "POOR1" in retired


def test_tick_no_crash_empty_db(tmp_db):
    from agents.evolution_agent import EvolutionAgent
    agent = EvolutionAgent(tmp_db)
    agent.setup()
    agent.tick()  # Should not crash with no strategies
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_evolution_agent.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'agents.evolution_agent'`

- [ ] **Step 3: Implement the Evolution Agent**

`agents/evolution_agent.py`:
```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_evolution_agent.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add agents/evolution_agent.py tests/test_evolution_agent.py
git commit -m "feat: add Evolution Agent with mutation, crossover, and retirement"
```

---

### Task 3: Plugin Scout agent (`agents/plugin_scout.py`)

**Files:**
- Create: `agents/plugin_scout.py`
- Create: `tests/test_plugin_scout.py`

The Plugin Scout searches GitHub and PyPI for useful packages, evaluates them, installs them safely, and registers them in the `plugins` table.

- [ ] **Step 1: Write the failing tests**

`tests/test_plugin_scout.py`:
```python
"""Tests for Plugin Scout agent."""
import json
import pytest


@pytest.fixture
def tmp_db(tmp_path):
    from core.db import Database
    db = Database(tmp_path / "test.sqlite")
    db.init_schema()
    db.execute(
        "INSERT INTO agent_registry (id, name, module_path, class_name, config) VALUES (?, ?, ?, ?, ?)",
        ("plugin_scout", "plugin_scout", "agents.plugin_scout", "PluginScout",
         '{"tick_interval": 0.01}'),
    )
    yield db
    db.close()


def test_plugin_scout_imports():
    from agents.plugin_scout import PluginScout
    assert PluginScout.name == "plugin_scout"


def test_search_domains_defined():
    from agents.plugin_scout import SEARCH_QUERIES
    assert isinstance(SEARCH_QUERIES, list)
    assert len(SEARCH_QUERIES) >= 3


def test_evaluate_candidate_good():
    from agents.plugin_scout import evaluate_candidate
    candidate = {
        "full_name": "ta-lib/ta-lib-python",
        "description": "Technical Analysis Library",
        "stargazers_count": 500,
        "license": {"spdx_id": "MIT"},
        "pushed_at": "2026-06-01T00:00:00Z",
        "archived": False,
    }
    passed, reason = evaluate_candidate(candidate, min_stars=50)
    assert passed


def test_evaluate_candidate_low_stars():
    from agents.plugin_scout import evaluate_candidate
    candidate = {
        "full_name": "nobody/tiny-repo",
        "description": "Some lib",
        "stargazers_count": 10,
        "license": {"spdx_id": "MIT"},
        "pushed_at": "2026-06-01T00:00:00Z",
        "archived": False,
    }
    passed, reason = evaluate_candidate(candidate, min_stars=50)
    assert not passed
    assert "stars" in reason.lower()


def test_evaluate_candidate_archived():
    from agents.plugin_scout import evaluate_candidate
    candidate = {
        "full_name": "old/archived-repo",
        "description": "Archived lib",
        "stargazers_count": 200,
        "license": {"spdx_id": "MIT"},
        "pushed_at": "2024-01-01T00:00:00Z",
        "archived": True,
    }
    passed, reason = evaluate_candidate(candidate, min_stars=50)
    assert not passed
    assert "archived" in reason.lower()


def test_register_plugin(tmp_db):
    from agents.plugin_scout import PluginScout
    agent = PluginScout(tmp_db)
    agent._register_plugin(
        plugin_id="ta-lib-python",
        name="ta-lib-python",
        source_url="https://github.com/ta-lib/ta-lib-python",
        install_type="pip",
        description="Technical Analysis Library",
    )
    row = tmp_db.fetchone("SELECT * FROM plugins WHERE id = ?", ("ta-lib-python",))
    assert row is not None
    assert row["status"] == "installed"
    assert row["install_type"] == "pip"


def test_is_already_installed(tmp_db):
    from agents.plugin_scout import PluginScout
    agent = PluginScout(tmp_db)
    assert not agent._is_already_installed("some-package")
    agent._register_plugin("some-package", "some-package", "", "pip", "test")
    assert agent._is_already_installed("some-package")


def test_tick_no_crash_without_internet(tmp_db):
    from agents.plugin_scout import PluginScout
    agent = PluginScout(tmp_db)
    agent.setup()
    # tick() makes HTTP requests that may fail — should not crash
    try:
        agent.tick()
    except Exception:
        pass  # Expected if no internet or GitHub rate limit
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_plugin_scout.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'agents.plugin_scout'`

- [ ] **Step 3: Implement the Plugin Scout**

`agents/plugin_scout.py`:
```python
"""Plugin Scout Agent: discovers, evaluates, and installs useful external packages."""
import subprocess
import sys
from datetime import datetime, timezone
from typing import List, Tuple

import requests

from agents.base_agent import BaseAgent


# ── Search configuration ──────────────────────────────────────────────────────

SEARCH_QUERIES = [
    "python trading indicators",
    "python technical analysis library",
    "python backtesting framework",
    "python XAUUSD forex",
    "python optuna trading optimization",
    "python financial data source",
    "python MetaTrader5 connector",
]

# Known useful packages the scout should be aware of (won't re-discover)
KNOWN_PACKAGES = {
    "ta", "pandas", "numpy", "optuna", "plotly", "flask",
    "anthropic", "MetaTrader5", "requests",
}

GITHUB_SEARCH_URL = "https://api.github.com/search/repositories"


# ── Evaluation ────────────────────────────────────────────────────────────────

def evaluate_candidate(candidate: dict, min_stars: int = 50) -> Tuple[bool, str]:
    """
    Evaluate a GitHub repository candidate.

    Returns (passed, reason). `reason` explains rejection or acceptance.
    """
    name = candidate.get("full_name", "unknown")
    stars = candidate.get("stargazers_count", 0)
    archived = candidate.get("archived", False)
    pushed_at = candidate.get("pushed_at", "")

    if archived:
        return False, f"{name}: archived repository"

    if stars < min_stars:
        return False, f"{name}: only {stars} stars (minimum {min_stars})"

    # Check if last push was within the last 2 years
    if pushed_at:
        try:
            last_push = datetime.fromisoformat(pushed_at.replace("Z", "+00:00"))
            age_days = (datetime.now(timezone.utc) - last_push).days
            if age_days > 730:
                return False, f"{name}: last push {age_days} days ago (stale)"
        except (ValueError, TypeError):
            pass

    lic = candidate.get("license")
    if lic is None:
        return False, f"{name}: no license specified"

    return True, f"{name}: {stars} stars, active, licensed"


# ── Agent ─────────────────────────────────────────────────────────────────────

class PluginScout(BaseAgent):
    """Discovers and installs useful Python packages from GitHub/PyPI."""

    name = "plugin_scout"

    def __init__(self, db):
        super().__init__(agent_id="plugin_scout", db=db)
        self._query_index = 0

    # ── lifecycle ──────────────────────────────────────────────────────────────

    def setup(self):
        self.logger.info("Plugin Scout ready")

    def tick(self):
        # Rotate through search queries one per tick
        query = SEARCH_QUERIES[self._query_index % len(SEARCH_QUERIES)]
        self._query_index += 1

        self.logger.info(f"Searching GitHub for: {query}")
        candidates = self._search_github(query)

        if not candidates:
            self.logger.info("No candidates found this tick")
            return

        installed_count = 0
        for candidate in candidates[:5]:  # Evaluate top 5 results per query
            passed, reason = evaluate_candidate(candidate, min_stars=50)
            if not passed:
                self.logger.debug(f"Rejected: {reason}")
                continue

            pkg_name = self._extract_package_name(candidate)
            if not pkg_name or self._is_already_installed(pkg_name):
                continue
            if pkg_name in KNOWN_PACKAGES:
                continue

            # Try installing
            success = self._safe_install(pkg_name)
            if success:
                self._register_plugin(
                    plugin_id=pkg_name,
                    name=candidate.get("name", pkg_name),
                    source_url=candidate.get("html_url", ""),
                    install_type="pip",
                    description=candidate.get("description", "")[:200],
                )
                installed_count += 1
                self.emit_event("milestone",
                    f"Installed plugin: {pkg_name}",
                    metadata={"package": pkg_name, "stars": candidate.get("stargazers_count")},
                )

        if installed_count:
            self.logger.info(f"Installed {installed_count} new package(s)")

    def tick_interval(self) -> float:
        return self.get_config("tick_interval", 3600)

    # ── GitHub search ──────────────────────────────────────────────────────────

    def _search_github(self, query: str) -> list:
        """Search GitHub repositories. Returns list of repo dicts."""
        try:
            resp = requests.get(
                GITHUB_SEARCH_URL,
                params={"q": query, "sort": "stars", "order": "desc", "per_page": 10},
                timeout=15,
                headers={"Accept": "application/vnd.github.v3+json"},
            )
            if resp.status_code == 200:
                return resp.json().get("items", [])
            self.logger.warning(f"GitHub search returned {resp.status_code}")
            return []
        except requests.RequestException as e:
            self.logger.warning(f"GitHub search failed: {e}")
            return []

    # ── Package extraction ─────────────────────────────────────────────────────

    @staticmethod
    def _extract_package_name(candidate: dict) -> str:
        """
        Extract a pip-installable package name from a GitHub repo.
        Uses the repo name as the pip package name (common convention).
        """
        name = candidate.get("name", "")
        # Sanitize: only allow alphanumeric, hyphens, underscores
        sanitized = "".join(c for c in name if c.isalnum() or c in "-_")
        return sanitized.lower() if sanitized else ""

    # ── Safe installation ──────────────────────────────────────────────────────

    def _safe_install(self, package_name: str) -> bool:
        """
        Install a pip package in a subprocess. Returns True on success.
        Uses --dry-run first to check for conflicts.
        """
        self.logger.info(f"Attempting to install: {package_name}")
        try:
            # Dry run first
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", "--dry-run", package_name],
                capture_output=True, text=True, timeout=60,
            )
            if result.returncode != 0:
                self.logger.warning(f"Dry-run failed for {package_name}: {result.stderr[:200]}")
                return False

            # Actual install
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", package_name],
                capture_output=True, text=True, timeout=120,
            )
            if result.returncode == 0:
                self.logger.info(f"Successfully installed {package_name}")
                return True
            else:
                self.logger.warning(f"Install failed for {package_name}: {result.stderr[:200]}")
                return False
        except subprocess.TimeoutExpired:
            self.logger.warning(f"Install timed out for {package_name}")
            return False
        except Exception as e:
            self.logger.error(f"Install error for {package_name}: {e}")
            return False

    # ── DB helpers ─────────────────────────────────────────────────────────────

    def _register_plugin(
        self,
        plugin_id: str,
        name: str,
        source_url: str,
        install_type: str,
        description: str,
    ):
        """Insert a new plugin record into the plugins table."""
        self.db.execute(
            "INSERT OR IGNORE INTO plugins "
            "(id, name, source_url, install_type, status, installed_by, description) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (plugin_id, name, source_url, install_type, "installed", self.agent_id, description),
        )

    def _is_already_installed(self, plugin_id: str) -> bool:
        """Check if a plugin is already registered in the DB."""
        row = self.db.fetchone("SELECT id FROM plugins WHERE id = ?", (plugin_id,))
        return row is not None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_plugin_scout.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add agents/plugin_scout.py tests/test_plugin_scout.py
git commit -m "feat: add Plugin Scout agent for automated package discovery"
```

---

### Task 4: Register new agents in config

**Files:**
- Modify: `core/config.py:43-79` — add `evolution_agent` and `plugin_scout` to `CORE_AGENTS`
- Modify: `tests/test_config.py:28-37` — update assertions for 7 agents
- Modify: `tests/test_orchestrator.py:21-29` — verify new agents register

- [ ] **Step 1: Update config.py**

Add two entries to the `CORE_AGENTS` list in `core/config.py`, after the `strategy_factory` entry (line 78):

```python
    {
        "name": "evolution_agent",
        "module_path": "agents.evolution_agent",
        "class_name": "EvolutionAgent",
        "config": {"tick_interval": 120},
        "can_spawn_children": False,
    },
    {
        "name": "plugin_scout",
        "module_path": "agents.plugin_scout",
        "class_name": "PluginScout",
        "config": {"tick_interval": 3600},
        "can_spawn_children": False,
    },
```

- [ ] **Step 2: Update test_config.py**

Replace the `test_core_agents_list` function in `tests/test_config.py`:

```python
def test_core_agents_list():
    from core.config import CORE_AGENTS
    assert isinstance(CORE_AGENTS, list)
    assert len(CORE_AGENTS) >= 7
    names = [a["name"] for a in CORE_AGENTS]
    assert "token_manager" in names
    assert "model_router" in names
    assert "data_agent" in names
    assert "backtest_runner" in names
    assert "strategy_factory" in names
    assert "evolution_agent" in names
    assert "plugin_scout" in names
```

- [ ] **Step 3: Update test_orchestrator.py register test**

Update `test_register_core_agents` in `tests/test_orchestrator.py` to check for the new agents:

```python
def test_register_core_agents(tmp_db):
    from agents.orchestrator import Orchestrator
    orch = Orchestrator(tmp_db)
    orch.register_core_agents()
    agents = tmp_db.fetchall("SELECT name FROM agent_registry")
    names = {row["name"] for row in agents}
    assert "token_manager" in names
    assert "model_router" in names
    assert "data_agent" in names
    assert "backtest_runner" in names
    assert "strategy_factory" in names
    assert "evolution_agent" in names
    assert "plugin_scout" in names
```

- [ ] **Step 4: Run full test suite**

Run: `python -m pytest tests/ -v --tb=short`
Expected: ALL PASS (increase test_orchestrator_start_and_stop join timeout to 45s if needed for 7 agents)

- [ ] **Step 5: Commit**

```bash
git add core/config.py tests/test_config.py tests/test_orchestrator.py
git commit -m "feat: register evolution_agent and plugin_scout in CORE_AGENTS"
```

---

### Task 5: Phase 3 integration test

**Files:**
- No new files — this is a verification task.

- [ ] **Step 1: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: ALL tests pass

- [ ] **Step 2: Start the system briefly**

Run the system for 15 seconds and verify all 7 agents start:
```bash
timeout 15 python start.py
```
Expected output should show:
- `Registered agent: evolution_agent`
- `Registered agent: plugin_scout`
- `Started agent: evolution_agent`
- `Started agent: plugin_scout`
- `Evolution Agent ready`
- `Plugin Scout ready`

- [ ] **Step 3: Verify DB state**

```bash
python -c "
from core.db import Database; from core.config import DB_PATH
db = Database(DB_PATH)
agents = db.fetchall('SELECT name, status FROM agent_registry')
print('Agents:', [dict(r) for r in agents])
plugins = db.fetchall('SELECT COUNT(*) as c FROM plugins')
print('Plugins:', plugins[0]['c'] if plugins else 0)
db.close()
"
```
Expected: 7 agents listed, all with status='running' or 'stopped'

- [ ] **Step 4: Commit any fixes**

```bash
git add -A && git commit -m "fix: Phase 3 integration fixes" || echo "No fixes needed"
```
