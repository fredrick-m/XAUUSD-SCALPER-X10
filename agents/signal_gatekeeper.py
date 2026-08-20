"""Signal Gatekeeper: strict pre-trade filter for portfolio-level risk control."""
import json
from datetime import datetime, timezone
from typing import Tuple

from agents.base_agent import BaseAgent


MAX_PORTFOLIO_HEAT = 0.25
MAX_DIRECTIONAL_BIAS = 0.60
MIN_CONFIDENCE_SCORE = 30.0
MIN_LIVE_WIN_RATE = 0.40
MIN_LIVE_TRADES_FOR_WR = 5
MAX_OPEN_PER_STRATEGY = 1
MIN_MARGIN_RATIO = 1.5
MAX_OPEN_TRADES_DEFAULT = 15
MAX_ENTRIES_PER_WINDOW = 2
ENTRY_WINDOW_MINUTES = 15


class SignalGatekeeper(BaseAgent):
    """Pre-trade GO/NO-GO filter. Risk-profile limits come from Risk Engine V2."""

    name = "signal_gatekeeper"

    def __init__(self, db):
        super().__init__(agent_id="signal_gatekeeper", db=db)

    def setup(self):
        self.logger.info("Signal Gatekeeper ready — Risk Engine V2 limits active")

    def tick(self):
        self._update_confidence_scores()

    def tick_interval(self) -> float:
        return self.get_config("tick_interval", 120)

    def check_signal(self, strategy_id: str, direction: str,
                     lot: float, sl_distance: float,
                     account_balance: float, account_equity: float,
                     free_margin: float) -> Tuple[bool, str]:
        checks = [
            self._check_circuit_breaker,
            self._check_news_blackout,
            self._check_max_open_trades,
            self._check_strategy_already_open,
            self._check_family_exposure,
            self._check_portfolio_heat,
            self._check_entry_burst,
            self._check_directional_bias,
            self._check_confidence_score,
            self._check_live_win_rate,
            self._check_margin,
        ]
        context = {
            "strategy_id": strategy_id,
            "direction": direction,
            "lot": lot,
            "sl_distance": sl_distance,
            "balance": account_balance,
            "equity": account_equity,
            "free_margin": free_margin,
        }
        for check_fn in checks:
            allowed, reason = check_fn(context)
            if not allowed:
                self.logger.info(f"GATE BLOCKED {strategy_id}: {reason}")
                self.emit_event(
                    "gate_blocked",
                    f"Signal blocked for {strategy_id}: {reason}",
                    metadata={"strategy_id": strategy_id, "reason": reason,
                              "direction": direction},
                )
                return False, reason
        self.logger.info(f"GATE PASS {strategy_id} {direction.upper()}")
        return True, "all_checks_passed"

    def _check_circuit_breaker(self, ctx: dict) -> Tuple[bool, str]:
        row = self.db.fetchone(
            "SELECT config FROM agent_registry WHERE id = ?", ("risk_manager",)
        )
        if not row or not row["config"]:
            return True, "ok"
        try:
            config = json.loads(row["config"]) if isinstance(row["config"], str) else row["config"]
        except (json.JSONDecodeError, TypeError):
            return False, "risk_state_unreadable"
        state = config.get("risk_state", {})
        if state.get("circuit_breaker_active", False):
            scope = state.get("circuit_breaker_scope") or "unknown"
            return False, f"circuit_breaker_active ({scope})"
        return True, "ok"

    def _check_news_blackout(self, ctx: dict) -> Tuple[bool, str]:
        try:
            from agents.news_calendar import is_blackout_period
            if is_blackout_period(self.db):
                return False, "news_blackout"
        except Exception:
            pass
        return True, "ok"

    def _check_max_open_trades(self, ctx: dict) -> Tuple[bool, str]:
        from agents.risk_manager import get_max_open_trades
        max_trades = get_max_open_trades(self.db)
        row = self.db.fetchone(
            "SELECT COUNT(*) as cnt FROM live_trades WHERE status = 'open'"
        )
        open_count = (row["cnt"] or 0) if row else 0
        if open_count >= max_trades:
            return False, f"max_open_trades ({open_count}/{max_trades})"
        return True, "ok"

    def _check_strategy_already_open(self, ctx: dict) -> Tuple[bool, str]:
        row = self.db.fetchone(
            "SELECT COUNT(*) as cnt FROM live_trades WHERE strategy_id = ? AND status = 'open'",
            (ctx["strategy_id"],),
        )
        open_count = (row["cnt"] or 0) if row else 0
        if open_count >= MAX_OPEN_PER_STRATEGY:
            return False, f"strategy_already_open ({ctx['strategy_id']})"
        return True, "ok"

    def _check_family_exposure(self, ctx: dict) -> Tuple[bool, str]:
        from core.config import FAMILY_MAX_OPEN
        row = self.db.fetchone(
            "SELECT family FROM strategies WHERE id = ?", (ctx["strategy_id"],)
        )
        family = row["family"] if row else None
        if not family:
            return True, "ok"
        cnt = self.db.fetchone(
            "SELECT COUNT(*) AS cnt FROM live_trades lt "
            "JOIN strategies s ON s.id = lt.strategy_id "
            "WHERE lt.status = 'open' AND s.family = ?",
            (family,),
        )
        open_count = (cnt["cnt"] or 0) if cnt else 0
        max_open = self.get_config("family_max_open") or FAMILY_MAX_OPEN
        if open_count >= max_open:
            return False, f"family_exposure ({family}: {open_count}/{max_open})"
        return True, "ok"

    def _check_portfolio_heat(self, ctx: dict) -> Tuple[bool, str]:
        from core.config import PIP_VALUE
        from agents.risk_manager import get_max_portfolio_heat

        rows = self.db.fetchall(
            "SELECT lot, sl, entry_price FROM live_trades WHERE status = 'open'"
        )
        total_risk = 0.0
        for r in rows:
            sl_dist = abs(r["entry_price"] - r["sl"]) if r["sl"] else 0
            total_risk += r["lot"] * sl_dist * PIP_VALUE

        total_risk += ctx["lot"] * ctx["sl_distance"] * PIP_VALUE
        equity = ctx.get("equity") or ctx.get("balance") or 0.0
        if equity <= 0:
            return False, "zero_equity"

        heat = total_risk / equity
        max_heat = get_max_portfolio_heat(self.db)
        if heat > max_heat:
            return False, f"portfolio_heat_exceeded ({heat:.1%} > {max_heat:.0%})"
        return True, "ok"

    def _check_entry_burst(self, ctx: dict) -> Tuple[bool, str]:
        from datetime import datetime, timezone, timedelta
        window_start = (
            datetime.now(timezone.utc) - timedelta(minutes=ENTRY_WINDOW_MINUTES)
        ).isoformat()
        row = self.db.fetchone(
            "SELECT COUNT(*) AS cnt FROM live_trades WHERE direction = ? AND opened_at >= ?",
            (ctx["direction"], window_start),
        )
        recent = (row["cnt"] or 0) if row else 0
        if recent >= MAX_ENTRIES_PER_WINDOW:
            return False, (
                f"entry_burst ({recent} {ctx['direction']} entries "
                f"in last {ENTRY_WINDOW_MINUTES}min)"
            )
        return True, "ok"

    def _check_directional_bias(self, ctx: dict) -> Tuple[bool, str]:
        rows = self.db.fetchall(
            "SELECT direction FROM live_trades WHERE status = 'open'"
        )
        if not rows:
            return True, "ok"
        total = len(rows) + 1
        same_dir = sum(1 for r in rows if r["direction"] == ctx["direction"]) + 1
        max_bias = self.get_config("max_directional_bias") or MAX_DIRECTIONAL_BIAS
        if total >= 3 and same_dir / total > max_bias:
            return False, f"directional_bias ({ctx['direction']}: {same_dir}/{total} = {same_dir/total:.0%})"
        return True, "ok"

    def _check_confidence_score(self, ctx: dict) -> Tuple[bool, str]:
        row = self.db.fetchone(
            "SELECT confidence_score FROM strategy_live_stats WHERE strategy_id = ?",
            (ctx["strategy_id"],),
        )
        if not row:
            return True, "ok"
        score = row["confidence_score"] or 50.0
        min_score = self.get_config("min_confidence_score") or MIN_CONFIDENCE_SCORE
        if score < min_score:
            return False, f"low_confidence ({score:.0f} < {min_score:.0f})"
        return True, "ok"

    def _check_live_win_rate(self, ctx: dict) -> Tuple[bool, str]:
        row = self.db.fetchone(
            "SELECT total_trades, live_win_rate FROM strategy_live_stats WHERE strategy_id = ?",
            (ctx["strategy_id"],),
        )
        if not row:
            return True, "ok"
        total = row["total_trades"] or 0
        if total < MIN_LIVE_TRADES_FOR_WR:
            return True, "ok"
        wr = row["live_win_rate"] or 0.0
        if wr < MIN_LIVE_WIN_RATE:
            return False, f"live_win_rate_too_low ({wr:.0%} < {MIN_LIVE_WIN_RATE:.0%} after {total} trades)"
        return True, "ok"

    def _check_margin(self, ctx: dict) -> Tuple[bool, str]:
        from core.config import PIP_VALUE
        required = ctx["lot"] * ctx["sl_distance"] * PIP_VALUE
        available = ctx["free_margin"]
        if available < required * MIN_MARGIN_RATIO:
            return False, f"insufficient_margin (need {required*MIN_MARGIN_RATIO:.2f}, have {available:.2f})"
        return True, "ok"

    def _update_confidence_scores(self):
        rows = self.db.fetchall(
            "SELECT s.id, s.best_profit_factor, s.best_win_rate, "
            "s.best_max_drawdown, s.walk_forward_passed, s.regimes_passed, s.best_config "
            "FROM strategies s WHERE s.status = 'validated' AND s.walk_forward_passed = 1"
        )
        for r in rows:
            score = 0.0
            pf = r["best_profit_factor"] or 0
            if pf >= 1.3:
                score += min(20, (pf - 1.0) * 20)
            if r["walk_forward_passed"]:
                score += 25

            config = {}
            if r["best_config"]:
                try:
                    config = json.loads(r["best_config"]) if isinstance(r["best_config"], str) else r["best_config"]
                except (json.JSONDecodeError, TypeError):
                    pass
            mc = config.get("monte_carlo", {})
            p_ruin = mc.get("p_ruin_10d", mc.get("p_ruin", 0.5))
            if p_ruin < 0.05:
                score += 20
            elif p_ruin < 0.10:
                score += 15
            elif p_ruin < 0.20:
                score += 10

            sensitivity = config.get("sensitivity", {})
            if not sensitivity.get("is_fragile", True):
                score += 15

            regimes = r["regimes_passed"] or 0
            score += min(10, regimes * 5)

            live = self.db.fetchone(
                "SELECT total_trades, live_win_rate, live_profit_factor "
                "FROM strategy_live_stats WHERE strategy_id = ?",
                (r["id"],),
            )
            live_trades = (live["total_trades"] or 0) if live else 0
            live_wr = (live["live_win_rate"] or 0) if live else 0
            if live_trades >= MIN_LIVE_TRADES_FOR_WR:
                if live_wr > 0.50:
                    score += 10
                elif live_wr > 0.40:
                    score += 5

            if config.get("probation"):
                graduated = live_trades >= 50 and live_wr > 0.50
                if not graduated:
                    score = min(score, 45.0)

            plateau = self.db.fetchone(
                "SELECT COUNT(*) AS n_tested, "
                "SUM(CASE WHEN v.pf >= 1.3 AND v.dd <= 0.25 AND v.trades >= 30 THEN 1 ELSE 0 END) AS n_good "
                "FROM (SELECT strategy_id, MAX(profit_factor) AS pf, "
                "             MAX(total_trades) AS trades, MIN(max_drawdown) AS dd "
                "      FROM backtest_results GROUP BY strategy_id) v "
                "JOIN strategies c ON c.id = v.strategy_id WHERE c.parent_strategy = ?",
                (r["id"],),
            )
            n_tested = (plateau["n_tested"] or 0) if plateau else 0
            n_good = (plateau["n_good"] or 0) if plateau else 0
            if n_tested >= 10:
                ratio = n_good / n_tested
                if ratio >= 0.5:
                    score += 15
                elif ratio >= 0.3:
                    score += 5
                elif ratio < 0.15:
                    score = min(score, 35.0)
                if n_tested >= 15 and n_good == 0:
                    self.db.execute(
                        "UPDATE strategies SET walk_forward_passed = 0 WHERE id = ?",
                        (r["id"],),
                    )
                    self.emit_event(
                        "warning",
                        f"Strategy {r['id']} UNDEPLOYED: isolated peak (0/{n_tested} burst neighbors validated)",
                        metadata={"strategy_id": r["id"], "n_tested": n_tested},
                    )

            self.db.execute(
                "INSERT INTO strategy_live_stats (strategy_id, confidence_score) VALUES (?, ?) "
                "ON CONFLICT(strategy_id) DO UPDATE SET confidence_score = ?",
                (r["id"], score, score),
            )

    def get_lot_scaling(self, strategy_id: str) -> float:
        row = self.db.fetchone(
            "SELECT confidence_score FROM strategy_live_stats WHERE strategy_id = ?",
            (strategy_id,),
        )
        if not row:
            return 0.5
        score = row["confidence_score"] or 50.0
        if score >= 70:
            return 1.0
        if score >= 50:
            return 0.5
        return 0.25


def gate_check(db, strategy_id: str, direction: str,
               lot: float, sl_distance: float,
               account_balance: float, account_equity: float,
               free_margin: float) -> Tuple[bool, str]:
    gk = SignalGatekeeper.__new__(SignalGatekeeper)
    gk.db = db
    gk.agent_id = "signal_gatekeeper"
    gk.logger = __import__("logging").getLogger("agent.signal_gatekeeper")
    gk.get_config = lambda key: None
    gk.emit_event = lambda *args, **kwargs: None
    return gk.check_signal(
        strategy_id, direction, lot, sl_distance,
        account_balance, account_equity, free_margin,
    )


def get_confidence_scaling(db, strategy_id: str) -> float:
    row = db.fetchone(
        "SELECT confidence_score FROM strategy_live_stats WHERE strategy_id = ?",
        (strategy_id,),
    )
    if not row:
        return 0.5
    score = row["confidence_score"] or 50.0
    if score >= 70:
        return 1.0
    if score >= 50:
        return 0.5
    return 0.25
