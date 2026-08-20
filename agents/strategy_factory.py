"""Strategy Factory V2: edge-aware generation of novel XAUUSD strategies."""
import random
import re
import textwrap
from pathlib import Path
from typing import Tuple

from agents.base_agent import BaseAgent
from agents.model_router import ModelRouter
from core.config import STRATEGIES_DIR

STRATEGY_TYPES = [
    "momentum_burst", "range_breakout", "order_block", "pullback_in_trend",
    "session_breakout", "volume_anomaly", "multi_tf_confluence", "candle_pattern",
    "mean_reversion", "momentum_divergence", "stochastic_rsi_scalp",
    "ichimoku_cloud_scalp", "supertrend_flip", "parabolic_sar_reversal",
    "fibonacci_retracement", "support_resistance_bounce", "fake_breakout_reversal",
    "liquidity_sweep", "vwap_deviation_scalp", "bollinger_squeeze_breakout",
    "keltner_channel_scalp", "donchian_channel_breakout", "gap_momentum_scalp",
    "price_action_engulfing", "elder_ray_impulse", "williams_r_extreme",
    "multi_rsi_confluence", "atr_expansion_momentum", "triple_ema_ribbon",
    "trend_exhaustion_reversal",
]

# Family research policy. Families are never permanently deleted: a small
# exploration probability allows revisiting an old idea after the market/data
# changes, while most generation budget goes to families showing evidence.
FAMILY_MIN_EVALUATED = 20
FAMILY_MIN_EDGE_PF = 1.05
FAMILY_GOOD_PF = 1.20
FAMILY_MIN_GOOD_RATIO = 0.10
FAMILY_REEXPLORE_PROB = 0.08


def validate_strategy_code(code: str) -> Tuple[bool, str]:
    try:
        compile(code, "<generated>", "exec")
    except SyntaxError as exc:
        return False, f"SyntaxError: {exc}"
    if "import pandas" not in code:
        return False, "Missing 'import pandas'"
    if "PARAMS" not in code:
        return False, "Missing PARAMS dict"
    if "generate_signals" not in code:
        return False, "Missing generate_signals function"
    if '"signal"' not in code and "'signal'" not in code:
        return False, "Missing 'signal' column assignment"
    return True, ""


def _strip_code_fences(text: str) -> str:
    pattern = r"```(?:python)?\s*\n?(.*?)```"
    match = re.search(pattern, text, re.DOTALL)
    return match.group(1).strip() if match else text.strip()


class StrategyFactory(BaseAgent):
    """Generate candidates while allocating research budget by family edge."""

    name = "strategy_factory"

    def __init__(self, db):
        super().__init__(agent_id="strategy_factory", db=db)

    def setup(self):
        self.logger.info("Strategy Factory V2 ready")
        STRATEGIES_DIR.mkdir(parents=True, exist_ok=True)

    def tick(self):
        # Prevent the LLM factory from outrunning backtesting by thousands of
        # candidates. Template/evolution agents still have their own queues.
        pending = self.db.fetchone(
            "SELECT COUNT(*) AS n FROM strategies s "
            "LEFT JOIN backtest_results b ON b.strategy_id=s.id "
            "WHERE s.created_by='strategy_factory' AND s.status='candidate' AND b.id IS NULL"
        )
        max_pending = int(self.get_config("max_pending", 200))
        if pending and int(pending["n"] or 0) >= max_pending:
            self.logger.info(f"Factory queue full ({pending['n']}/{max_pending})")
            return

        strategy_type = self._choose_strategy_type()
        self.logger.info(f"Generating family: {strategy_type}")
        self.emit_event("info", f"Generating strategy family: {strategy_type}")

        code = self._generate_strategy(strategy_type)
        is_valid, error = validate_strategy_code(code)
        if not is_valid:
            code = self._fix_strategy_code(code, error)
            is_valid, error = validate_strategy_code(code)
            if not is_valid:
                self.emit_event("error", f"Strategy generation failed: {error}")
                return

        strategy_id = self._next_strategy_id()
        file_name = f"strategy_{strategy_id.lower()}.py"
        file_path = STRATEGIES_DIR / file_name
        file_path.write_text(code, encoding="utf-8")

        stats = self._family_stats().get(strategy_type, {})
        description = (
            f"Factory V2 {strategy_type} | tested={stats.get('evaluated', 0)} "
            f"good_ratio={stats.get('good_ratio', 0.0):.2f} max_pf={stats.get('max_pf', 0.0):.2f}"
        )
        self._register_strategy(strategy_id, str(file_path), strategy_type, description)
        self.post_task(
            target_agent="backtest_runner", task_type="backtest",
            payload={"strategy_id": strategy_id, "file_path": str(file_path)}, priority=5,
        )
        self.emit_event("milestone", f"Strategy {strategy_id} ({strategy_type}) queued")

    def tick_interval(self) -> float:
        return self.get_config("tick_interval", 300)

    def _family_stats(self) -> dict:
        """Summarize actual tested evidence for every research family."""
        rows = self.db.fetchall(
            "SELECT s.family, COUNT(DISTINCT s.id) AS attempted, "
            "COUNT(DISTINCT CASE WHEN b.id IS NOT NULL THEN s.id END) AS evaluated, "
            "MAX(COALESCE(s.best_profit_factor,0)) AS max_pf, "
            "SUM(CASE WHEN x.best_pf >= ? THEN 1 ELSE 0 END) AS good "
            "FROM strategies s "
            "LEFT JOIN backtest_results b ON b.strategy_id=s.id "
            "LEFT JOIN (SELECT strategy_id, MAX(profit_factor) AS best_pf "
            "           FROM backtest_results GROUP BY strategy_id) x ON x.strategy_id=s.id "
            "WHERE s.family IS NOT NULL GROUP BY s.family",
            (FAMILY_GOOD_PF,),
        )
        stats = {}
        for r in rows:
            evaluated = int(r["evaluated"] or 0)
            good = int(r["good"] or 0)
            stats[r["family"]] = {
                "attempted": int(r["attempted"] or 0),
                "evaluated": evaluated,
                "max_pf": float(r["max_pf"] or 0.0),
                "good_ratio": good / evaluated if evaluated else 0.0,
            }
        return stats

    @staticmethod
    def _family_is_cold(s: dict) -> bool:
        """Cold = enough evidence and still almost no sign of edge."""
        return (
            int(s.get("evaluated", 0)) >= FAMILY_MIN_EVALUATED
            and float(s.get("max_pf", 0.0)) < FAMILY_MIN_EDGE_PF
            and float(s.get("good_ratio", 0.0)) < FAMILY_MIN_GOOD_RATIO
        )

    def _choose_strategy_type(self) -> str:
        """Balance exploration, exploitation and automatic family cooling."""
        stats = self._family_stats()

        untried = [f for f in STRATEGY_TYPES if stats.get(f, {}).get("attempted", 0) == 0]
        if untried:
            return random.choice(untried)

        cold = [f for f in STRATEGY_TYPES if self._family_is_cold(stats.get(f, {}))]
        active = [f for f in STRATEGY_TYPES if f not in cold]

        # Occasionally retest a cooled family so regime/data changes can revive it.
        if cold and random.random() < FAMILY_REEXPLORE_PROB:
            return min(cold, key=lambda f: stats.get(f, {}).get("attempted", 0))

        if not active:
            active = STRATEGY_TYPES[:]

        # UCB-like research score: reward actual good ratio/max PF, but also
        # under-sampled families. This avoids both clone factories and starving
        # promising families after only a few attempts.
        def research_score(f: str) -> float:
            s = stats.get(f, {})
            attempted = float(s.get("attempted", 0))
            evaluated = float(s.get("evaluated", 0))
            max_pf = min(float(s.get("max_pf", 0.0)), 3.0)
            good_ratio = float(s.get("good_ratio", 0.0))
            evidence = 2.0 * good_ratio + 0.6 * max(0.0, max_pf - 1.0)
            exploration = 2.0 / ((evaluated + 1.0) ** 0.5)
            saturation_penalty = min(attempted / 200.0, 1.0) * 0.5
            return evidence + exploration - saturation_penalty + random.uniform(0, 0.05)

        return max(active, key=research_score)

    def _build_generation_prompt(self, strategy_type: str = "momentum_burst") -> str:
        top_rows = self.db.fetchall(
            "SELECT id, family, best_win_rate, best_profit_factor, best_max_drawdown "
            "FROM strategies WHERE status IN ('validated','portfolio_reserve') "
            "ORDER BY best_profit_factor DESC LIMIT 5"
        )
        context = ""
        if top_rows:
            context = "Existing strong ideas (DO NOT clone them):\n" + "\n".join(
                f"- {r['id']} family={r['family']} WR={r['best_win_rate']} PF={r['best_profit_factor']} DD={r['best_max_drawdown']}"
                for r in top_rows
            ) + "\n\n"

        return textwrap.dedent(f"""\
            You are a quantitative trading researcher building diverse XAUUSD M5 scalping systems.

            {context}Generate ONE complete Python strategy in family: {strategy_type}.

            RESEARCH GOAL:
            - Produce a genuinely different edge, not a cosmetic parameter variation.
            - Prefer causal price/volatility/session/volume structure over indicator stacking.
            - The strategy will face next-bar execution, spread, slippage, holdout,
              walk-forward, Monte Carlo, sensitivity and correlation filters.
            - Never optimize for a claimed win rate. Generate falsifiable logic.
            - Avoid look-ahead/repainting and any future-bar information.

            HARD REQUIREMENTS:
            1. Define numeric PARAMS, including sl_atr and tp_atr.
            2. Define exactly: def generate_signals(df: pd.DataFrame, p: dict = PARAMS) -> pd.DataFrame
            3. Add ATR column named "ATR" and signal values in {{-1,0,1}}.
            4. Allowed imports: pandas as pd, numpy as np, ta.
            5. Do not import MetaTrader5, yfinance or data/network clients.
            6. Avoid simple MA crossover as the main entry logic.
            7. Use only information available at or before each bar.
            8. Keep parameters few enough to reduce overfitting (prefer <=12 numeric knobs).
            9. Start with a docstring documenting Family, Hypothesis, Timeframe,
               Entry, Exit, Failure mode and Parameters.

            Return ONLY raw Python source code.
        """)

    def _generate_strategy(self, strategy_type: str) -> str:
        model = ModelRouter.route_task("generate_strategy")
        raw = self.call_llm(
            prompt=self._build_generation_prompt(strategy_type), model=model,
            task_type="generate_strategy", max_tokens=4096, temperature=0.9,
        )
        return _strip_code_fences(raw)

    def _fix_strategy_code(self, code: str, error: str) -> str:
        fix_prompt = textwrap.dedent(f"""\
            Repair this XAUUSD strategy. Error: {error}
            Preserve its trading hypothesis. Ensure valid Python, import pandas as pd,
            define PARAMS, ATR, and generate_signals(df, p=PARAMS) producing signal -1/0/1.
            Do not introduce future-data/look-ahead logic.
            Return ONLY corrected source code.

            {code}
        """)
        raw = self.call_llm(
            prompt=fix_prompt, model="sonnet", task_type="debug_strategy",
            max_tokens=4096, temperature=0.2,
        )
        return _strip_code_fences(raw)

    def _next_strategy_id(self) -> str:
        row = self.db.fetchone("SELECT id FROM strategies WHERE id LIKE 'G%' ORDER BY id DESC LIMIT 1")
        if row:
            try:
                return f"G{int(row['id'][1:]) + 1:04d}"
            except ValueError:
                pass
        return "G0001"

    def _register_strategy(self, strategy_id: str, file_path: str, family: str, description: str) -> None:
        self.db.execute(
            "INSERT OR IGNORE INTO strategies "
            "(id, file_path, family, description, created_by, status) VALUES (?, ?, ?, ?, ?, ?)",
            (strategy_id, file_path, family, description, self.agent_id, "candidate"),
        )
