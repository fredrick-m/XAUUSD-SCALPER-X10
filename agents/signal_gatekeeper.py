"""Signal Gatekeeper: strict pre-trade filter for portfolio-level risk control."""
import json
from datetime import datetime, timezone
from typing import Tuple

from agents.base_agent import BaseAgent


# ── Gatekeeper thresholds ────────────────────────────
MAX_PORTFOLIO_HEAT = 0.25        # max 25% of balance at risk across all open trades
MAX_DIRECTIONAL_BIAS = 0.60      # max 60% of open trades in one direction
MIN_CONFIDENCE_SCORE = 30.0      # minimum confidence to allow a trade
MIN_LIVE_WIN_RATE = 0.40         # after 5+ live trades, must maintain 40% WR
MIN_LIVE_TRADES_FOR_WR = 5       # only enforce live WR after N trades
MAX_OPEN_PER_STRATEGY = 1        # max 1 open trade per strategy
MIN_MARGIN_RATIO = 1.5           # free margin must be 1.5x the required margin
MAX_OPEN_TRADES_DEFAULT = 15     # default max simultaneous positions


class SignalGatekeeper(BaseAgent):
    """
    Pre-trade filter that paper_trade consults before placing any order.

    Checks:
    1. Portfolio heat (total exposure vs balance)
    2. Directional bias (not too many trades same direction)
    3. Strategy confidence score
    4. Strategy live win rate (after N trades)
    5. Max open trades limit
    6. One trade per strategy limit
    7. Circuit breaker not active
    8. Sufficient margin
    """

    name = "signal_gatekeeper"

    def __init__(self, db):
        super().__init__(agent_id="signal_gatekeeper", db=db)

    def setup(self):
        self.logger.info("Signal Gatekeeper ready — strict filters active")

    def tick(self):
        """Periodic: update confidence scores for all active strategies."""
        self._update_confidence_scores()

    def tick_interval(self) -> float:
        return self.get_config("tick_interval", 120)

    # ──────────────────────────────────────────────────
    # Main gate: GO or NO-GO
    # ──────────────────────────────────────────────────

    def check_signal(self, strategy_id: str, direction: str,
                     lot: float, sl_distance: float,
                     account_balance: float, account_equity: float,
                     free_margin: float) -> Tuple[bool, str]:
        """
        Check if a trade signal should be executed.

        Args:
            strategy_id: ID of the strategy requesting the trade
            direction: 'buy' or 'sell'
            lot: proposed lot size
            sl_distance: distance to SL in price units
            account_balance: current account balance
            account_equity: current account equity
            free_margin: available free margin

        Returns:
            (allowed: bool, reason: str)
        """
        checks = [
            self._check_circuit_breaker,
            self._check_news_blackout,
            self._check_max_open_trades,
            self._check_strategy_already_open,
            self._check_family_exposure,
            self._check_portfolio_heat,
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

    # ──────────────────────────────────────────────────
    # Individual checks
    # ──────────────────────────────────────────────────

    def _check_circuit_breaker(self, ctx: dict) -> Tuple[bool, str]:
        """Check if circuit breaker is active."""
        row = self.db.fetchone(
            "SELECT config FROM agent_registry WHERE id = ?", ("risk_manager",)
        )
        if not row or not row["config"]:
            return True, "ok"
        config = json.loads(row["config"]) if isinstance(row["config"], str) else row["config"]
        state = config.get("risk_state", {})
        if state.get("circuit_breaker_active", False):
            return False, "circuit_breaker_active"
        return True, "ok"

    def _check_news_blackout(self, ctx: dict) -> Tuple[bool, str]:
        """No new entries around high-impact USD news (NFP, CPI, FOMC...).

        The strategies only see price — a rate decision gaps straight
        through their stops. The news_calendar agent maintains the blackout
        windows (±30 min); this check finally wires it into execution.
        """
        try:
            from agents.news_calendar import is_blackout_period
            if is_blackout_period(self.db):
                return False, "news_blackout"
        except Exception:
            pass  # never let a calendar failure block all trading
        return True, "ok"

    def _check_max_open_trades(self, ctx: dict) -> Tuple[bool, str]:
        """Check if we're at the maximum number of open trades."""
        max_trades = self.get_config("max_open_trades") or MAX_OPEN_TRADES_DEFAULT
        row = self.db.fetchone(
            "SELECT COUNT(*) as cnt FROM live_trades WHERE status = 'open'"
        )
        open_count = (row["cnt"] or 0) if row else 0
        if open_count >= max_trades:
            return False, f"max_open_trades ({open_count}/{max_trades})"
        return True, "ok"

    def _check_strategy_already_open(self, ctx: dict) -> Tuple[bool, str]:
        """Check if this strategy already has an open trade."""
        row = self.db.fetchone(
            "SELECT COUNT(*) as cnt FROM live_trades "
            "WHERE strategy_id = ? AND status = 'open'",
            (ctx["strategy_id"],),
        )
        open_count = (row["cnt"] or 0) if row else 0
        if open_count >= MAX_OPEN_PER_STRATEGY:
            return False, f"strategy_already_open ({ctx['strategy_id']})"
        return True, "ok"

    def _check_family_exposure(self, ctx: dict) -> Tuple[bool, str]:
        """Cap concurrent open trades per template family.

        Variants of one family fire on the same market conditions; letting
        several of them stack positions multiplies a single bet, not the
        diversification.
        """
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
        """
        Portfolio heat = total risk across all open trades / balance.
        Risk per trade = lot * sl_distance * pip_value (approx).
        """
        from core.config import PIP_VALUE

        rows = self.db.fetchall(
            "SELECT lot, sl, entry_price, direction FROM live_trades WHERE status = 'open'"
        )
        total_risk = 0.0
        for r in rows:
            sl_dist = abs(r["entry_price"] - r["sl"]) if r["sl"] else 0
            total_risk += r["lot"] * sl_dist * PIP_VALUE

        # Add proposed trade risk
        proposed_risk = ctx["lot"] * ctx["sl_distance"] * PIP_VALUE
        total_risk += proposed_risk

        balance = ctx["balance"]
        if balance <= 0:
            return False, "zero_balance"

        heat = total_risk / balance
        max_heat = self.get_config("max_portfolio_heat") or MAX_PORTFOLIO_HEAT
        if heat > max_heat:
            return False, f"portfolio_heat_exceeded ({heat:.1%} > {max_heat:.0%})"
        return True, "ok"

    def _check_directional_bias(self, ctx: dict) -> Tuple[bool, str]:
        """Ensure not too many trades in the same direction."""
        rows = self.db.fetchall(
            "SELECT direction FROM live_trades WHERE status = 'open'"
        )
        if not rows:
            return True, "ok"

        total = len(rows)
        same_dir = sum(1 for r in rows if r["direction"] == ctx["direction"])
        # Adding this trade
        same_dir += 1
        total += 1

        max_bias = self.get_config("max_directional_bias") or MAX_DIRECTIONAL_BIAS
        if total >= 3 and same_dir / total > max_bias:
            return False, f"directional_bias ({ctx['direction']}: {same_dir}/{total} = {same_dir/total:.0%})"
        return True, "ok"

    def _check_confidence_score(self, ctx: dict) -> Tuple[bool, str]:
        """Check strategy's confidence score."""
        row = self.db.fetchone(
            "SELECT confidence_score FROM strategy_live_stats WHERE strategy_id = ?",
            (ctx["strategy_id"],),
        )
        if not row:
            # New strategy with no live stats — allow with default score
            return True, "ok"

        score = row["confidence_score"] or 50.0
        min_score = self.get_config("min_confidence_score") or MIN_CONFIDENCE_SCORE
        if score < min_score:
            return False, f"low_confidence ({score:.0f} < {min_score:.0f})"
        return True, "ok"

    def _check_live_win_rate(self, ctx: dict) -> Tuple[bool, str]:
        """After N live trades, enforce minimum win rate."""
        row = self.db.fetchone(
            "SELECT total_trades, live_win_rate FROM strategy_live_stats "
            "WHERE strategy_id = ?",
            (ctx["strategy_id"],),
        )
        if not row:
            return True, "ok"

        total = row["total_trades"] or 0
        if total < MIN_LIVE_TRADES_FOR_WR:
            return True, "ok"  # Not enough data to judge

        wr = row["live_win_rate"] or 0.0
        if wr < MIN_LIVE_WIN_RATE:
            return False, f"live_win_rate_too_low ({wr:.0%} < {MIN_LIVE_WIN_RATE:.0%} after {total} trades)"
        return True, "ok"

    def _check_margin(self, ctx: dict) -> Tuple[bool, str]:
        """Check if there's enough free margin for the trade."""
        from core.config import PIP_VALUE
        # Rough margin requirement: lot * price / leverage
        # For safety, just check free_margin > lot * sl_distance * pip_value * ratio
        required = ctx["lot"] * ctx["sl_distance"] * PIP_VALUE
        available = ctx["free_margin"]
        if available < required * MIN_MARGIN_RATIO:
            return False, f"insufficient_margin (need {required*MIN_MARGIN_RATIO:.2f}, have {available:.2f})"
        return True, "ok"

    # ──────────────────────────────────────────────────
    # Confidence score calculation
    # ──────────────────────────────────────────────────

    def _update_confidence_scores(self):
        """Recalculate confidence scores for all deployed strategies."""
        rows = self.db.fetchall(
            "SELECT s.id, s.best_profit_factor, s.best_win_rate, "
            "s.best_max_drawdown, s.walk_forward_passed, s.regimes_passed, "
            "s.best_config "
            "FROM strategies s "
            "WHERE s.status = 'validated' AND s.walk_forward_passed = 1"
        )

        for r in rows:
            score = 0.0

            # Backtest PF score (0-20 points)
            pf = r["best_profit_factor"] or 0
            if pf >= 1.3:
                score += min(20, (pf - 1.0) * 20)

            # Walk-forward bonus (25 points)
            if r["walk_forward_passed"]:
                score += 25

            # Monte Carlo survival (0-20 points)
            config = {}
            if r["best_config"]:
                try:
                    config = json.loads(r["best_config"]) if isinstance(r["best_config"], str) else r["best_config"]
                except (json.JSONDecodeError, TypeError):
                    pass
            mc = config.get("monte_carlo", {})
            p_ruin = mc.get("p_ruin", 0.5)
            if p_ruin < 0.05:
                score += 20
            elif p_ruin < 0.10:
                score += 15
            elif p_ruin < 0.20:
                score += 10

            # Sensitivity stability (0-15 points)
            sensitivity = config.get("sensitivity", {})
            if not sensitivity.get("is_fragile", True):
                score += 15

            # Regime robustness (0-10 points)
            regimes = r["regimes_passed"] or 0
            score += min(10, regimes * 5)

            # Live track record bonus (0-10 points)
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

            # Probation penalty: validated on a small backtest sample →
            # reduced size until 50+ live trades with a winning record
            # complete the missing evidence (automatic graduation).
            if config.get("probation"):
                graduated = live_trades >= 50 and live_wr > 0.50
                if not graduated:
                    score = min(score, 45.0)  # cap below the half-lot tier

            # Store/update confidence score
            self.db.execute(
                "INSERT INTO strategy_live_stats (strategy_id, confidence_score) "
                "VALUES (?, ?) "
                "ON CONFLICT(strategy_id) DO UPDATE SET confidence_score = ?",
                (r["id"], score, score),
            )

    # ──────────────────────────────────────────────────
    # Lot scaling by confidence
    # ──────────────────────────────────────────────────

    def get_lot_scaling(self, strategy_id: str) -> float:
        """
        Returns lot scaling factor based on confidence score.
        Score >= 70 → 1.0 (full lot)
        Score 50-69 → 0.5 (half lot)
        Score < 50  → 0.25 (quarter lot)
        """
        row = self.db.fetchone(
            "SELECT confidence_score FROM strategy_live_stats WHERE strategy_id = ?",
            (strategy_id,),
        )
        if not row:
            return 0.5  # Default: half lot for unknown strategies

        score = row["confidence_score"] or 50.0
        if score >= 70:
            return 1.0
        elif score >= 50:
            return 0.5
        else:
            return 0.25


# ──────────────────────────────────────────────────
# Public API for paper_trade to call
# ──────────────────────────────────────────────────

def gate_check(db, strategy_id: str, direction: str,
               lot: float, sl_distance: float,
               account_balance: float, account_equity: float,
               free_margin: float) -> Tuple[bool, str]:
    """
    Standalone gate check function for use by paper_trade agent.
    Creates a lightweight check without full agent lifecycle.
    """
    gk = SignalGatekeeper.__new__(SignalGatekeeper)
    gk.db = db
    gk.agent_id = "signal_gatekeeper"
    gk.logger = __import__("logging").getLogger("agent.signal_gatekeeper")

    return gk.check_signal(
        strategy_id, direction, lot, sl_distance,
        account_balance, account_equity, free_margin,
    )


def get_confidence_scaling(db, strategy_id: str) -> float:
    """Get lot scaling factor for a strategy based on confidence."""
    row = db.fetchone(
        "SELECT confidence_score FROM strategy_live_stats WHERE strategy_id = ?",
        (strategy_id,),
    )
    if not row:
        return 0.5
    score = row["confidence_score"] or 50.0
    if score >= 70:
        return 1.0
    elif score >= 50:
        return 0.5
    return 0.25
