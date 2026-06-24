"""Strategy Factory Agent: uses Claude to generate novel XAUUSD M1 trading strategies."""
import re
import textwrap
from pathlib import Path
from typing import Tuple

from agents.base_agent import BaseAgent
from agents.model_router import ModelRouter
from core.config import STRATEGIES_DIR

# ── Strategy type catalogue ────────────────────────────────────────────────────
STRATEGY_TYPES = [
    "momentum_burst",
    "range_breakout",
    "order_block",
    "pullback_in_trend",
    "session_breakout",
    "volume_anomaly",
    "multi_tf_confluence",
    "candle_pattern",
    "mean_reversion",
    "momentum_divergence",
]


# ── Validation ─────────────────────────────────────────────────────────────────

def validate_strategy_code(code: str) -> Tuple[bool, str]:
    """
    Check that generated strategy code is syntactically correct and meets
    the minimum structural requirements.

    Returns (is_valid, error_message).  error_message is "" on success.
    """
    # 1. Syntax check
    try:
        compile(code, "<generated>", "exec")
    except SyntaxError as exc:
        return False, f"SyntaxError: {exc}"

    # 2. Must import pandas
    if "import pandas" not in code:
        return False, "Missing 'import pandas'"

    # 3. Must define PARAMS dict
    if "PARAMS" not in code:
        return False, "Missing PARAMS dict"

    # 4. Must define generate_signals function
    if "generate_signals" not in code:
        return False, "Missing generate_signals function"

    # 5. Must set a 'signal' column somewhere
    if '"signal"' not in code and "'signal'" not in code:
        return False, "Missing 'signal' column assignment"

    return True, ""


# ── Helper: strip markdown fences ─────────────────────────────────────────────

def _strip_code_fences(text: str) -> str:
    """Remove ```python … ``` or ``` … ``` wrappers from LLM output."""
    # Match optional language tag after opening fence
    pattern = r"```(?:python)?\s*\n(.*?)```"
    match = re.search(pattern, text, re.DOTALL)
    if match:
        return match.group(1).strip()
    # If no fences found, return as-is (may already be raw code)
    return text.strip()


# ── Agent ──────────────────────────────────────────────────────────────────────

class StrategyFactory(BaseAgent):
    """Generates new trading strategies via the Claude API and registers them."""

    name = "strategy_factory"

    def __init__(self, db):
        super().__init__(agent_id="strategy_factory", db=db)

    # ── lifecycle ──────────────────────────────────────────────────────────────

    def setup(self):
        self.logger.info("Strategy Factory ready")
        STRATEGIES_DIR.mkdir(parents=True, exist_ok=True)

    def tick(self):
        strategy_type = self._choose_strategy_type()
        self.logger.info(f"Generating strategy type: {strategy_type}")
        self.emit_event("info", f"Generating strategy: {strategy_type}")

        code = self._generate_strategy(strategy_type)

        is_valid, error = validate_strategy_code(code)
        if not is_valid:
            self.logger.warning(f"Generated code invalid ({error}), attempting fix")
            code = self._fix_strategy_code(code, error)
            is_valid, error = validate_strategy_code(code)
            if not is_valid:
                self.logger.error(f"Could not fix strategy code: {error}")
                self.emit_event("error", f"Strategy generation failed after fix attempt: {error}")
                return

        strategy_id = self._next_strategy_id()
        file_name = f"strategy_{strategy_id.lower()}.py"
        file_path = STRATEGIES_DIR / file_name

        file_path.write_text(code, encoding="utf-8")
        self.logger.info(f"Saved strategy to {file_path}")

        self._register_strategy(
            strategy_id=strategy_id,
            file_path=str(file_path),
            family=strategy_type,
            description=f"Auto-generated {strategy_type} strategy",
        )

        self.post_task(
            target_agent="backtest_runner",
            task_type="backtest",
            payload={"strategy_id": strategy_id, "file_path": str(file_path)},
            priority=5,
        )
        self.emit_event("milestone", f"Strategy {strategy_id} registered and queued for backtest")

    def tick_interval(self) -> float:
        return self.get_config("tick_interval", 3600)

    # ── strategy selection ─────────────────────────────────────────────────────

    def _choose_strategy_type(self) -> str:
        """
        Prefer strategy types that have never been attempted.
        Fall back to the least-tried type.
        """
        rows = self.db.fetchall(
            "SELECT family, COUNT(*) as cnt FROM strategies GROUP BY family"
        )
        tried = {row["family"]: row["cnt"] for row in rows}

        untried = [t for t in STRATEGY_TYPES if t not in tried]
        if untried:
            return untried[0]

        # All types tried — pick the one with fewest strategies
        return min(STRATEGY_TYPES, key=lambda t: tried.get(t, 0))

    # ── prompt building ────────────────────────────────────────────────────────

    def _build_generation_prompt(self, strategy_type: str = "momentum_burst") -> str:
        """Build the detailed LLM prompt for strategy generation."""

        # Pull top-performing strategies from DB for context
        top_rows = self.db.fetchall(
            "SELECT id, family, description, best_win_rate, best_profit_factor "
            "FROM strategies WHERE status != 'rejected' "
            "ORDER BY best_profit_factor DESC LIMIT 3"
        )
        context_block = ""
        if top_rows:
            lines = ["Current best strategies for context:"]
            for r in top_rows:
                lines.append(
                    f"  - {r['id']} ({r['family']}): WR={r['best_win_rate']}, PF={r['best_profit_factor']}"
                )
            context_block = "\n".join(lines) + "\n\n"

        prompt = textwrap.dedent(f"""\
            You are an expert algorithmic trading engineer specialising in XAUUSD (Gold/USD) M1 scalping.

            {context_block}Your task: generate a complete, self-contained Python strategy module for the
            strategy type: **{strategy_type}**

            === HARD REQUIREMENTS ===
            1. The file must define a dict named PARAMS containing all numeric hyper-parameters
               (e.g. periods, multipliers, thresholds).  Example:
               PARAMS = {{"ema_fast": 5, "ema_slow": 20, "atr_period": 14, "sl_atr": 1.5, "tp_atr": 3.0}}

            2. The file must define exactly this function signature:
               def generate_signals(df: pd.DataFrame, p: dict = PARAMS) -> pd.DataFrame:
               The function must add a column named "signal" with values 1 (long), -1 (short), 0 (flat)
               and return the modified DataFrame.

            3. Imports allowed: pandas as pd, numpy as np, ta (the `ta` library).
               Do NOT import MetaTrader5, yfinance, or any paid data feed.

            4. Do NOT use simple EMA/SMA crossovers — they are already well-covered.
               Use {strategy_type}-specific logic with meaningful edge.

            5. Include ATR-based stop-loss and take-profit logic inside generate_signals or in a helper
               (columns "sl" and "tp" in the returned DataFrame are encouraged but not required).

            6. The code must be valid Python 3.10+.  No syntax errors.

            7. Start with a docstring block that documents: Strategy name, Family, Goal, Timeframe,
               Description, Parameters, Entry, Exit.

            === OUTPUT FORMAT ===
            Return ONLY the raw Python source code, no markdown fences, no explanation.
            The output must start with triple-quoted docstring or an import statement.
        """)
        return prompt

    # ── code generation ────────────────────────────────────────────────────────

    def _generate_strategy(self, strategy_type: str) -> str:
        """Call the LLM to generate strategy code for the given type."""
        model = ModelRouter.route_task("generate_strategy")  # -> "opus"
        prompt = self._build_generation_prompt(strategy_type)
        raw = self.call_llm(
            prompt=prompt,
            model=model,
            task_type="generate_strategy",
            max_tokens=4096,
            temperature=0.8,
        )
        return _strip_code_fences(raw)

    def _fix_strategy_code(self, code: str, error: str) -> str:
        """Ask Claude (sonnet — cheaper) to repair invalid generated code."""
        fix_prompt = textwrap.dedent(f"""\
            The following Python strategy code is invalid.
            Error: {error}

            Fix the code so that:
            - It has no syntax errors
            - It imports pandas (import pandas as pd)
            - It defines a dict named PARAMS
            - It defines: def generate_signals(df, p=PARAMS): ... that sets df["signal"] and returns df

            Return ONLY the corrected Python source code, no markdown, no explanation.

            === CODE TO FIX ===
            {code}
        """)
        raw = self.call_llm(
            prompt=fix_prompt,
            model="sonnet",
            task_type="debug_strategy",
            max_tokens=4096,
            temperature=0.3,
        )
        return _strip_code_fences(raw)

    # ── DB helpers ─────────────────────────────────────────────────────────────

    def _next_strategy_id(self) -> str:
        """
        Generate the next sequential generated-strategy ID (G0001, G0002, …).
        """
        row = self.db.fetchone(
            "SELECT id FROM strategies WHERE id LIKE 'G%' ORDER BY id DESC LIMIT 1"
        )
        if row:
            last_num = int(row["id"][1:])
            return f"G{last_num + 1:04d}"
        return "G0001"

    def _register_strategy(
        self,
        strategy_id: str,
        file_path: str,
        family: str,
        description: str,
    ) -> None:
        """Insert a new strategy record into the strategies table."""
        self.db.execute(
            "INSERT OR IGNORE INTO strategies "
            "(id, file_path, family, description, created_by, status) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (strategy_id, file_path, family, description, self.agent_id, "candidate"),
        )
