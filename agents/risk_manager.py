"""Risk Manager Agent: enforces portfolio-level risk limits and circuit breakers."""
import json
from datetime import datetime, timezone, timedelta
from typing import Optional

from agents.base_agent import BaseAgent


# Default risk limits
DEFAULT_MAX_DAILY_DD = 0.10         # 10% max daily drawdown
DEFAULT_MAX_WEEKLY_DD = 0.20        # 20% max weekly drawdown
DEFAULT_MAX_CONSECUTIVE_LOSSES = 5  # after N losses, reduce position size
DEFAULT_MAX_OPEN_TRADES = 3         # max simultaneous positions
DEFAULT_SCALING_FACTOR = 0.5        # reduce lots by this factor after loss streak
DEFAULT_COOLDOWN_MINUTES = 60       # pause after circuit breaker trip


class RiskManager(BaseAgent):
    """
    Portfolio-level risk management agent.

    Responsibilities:
    - Circuit breaker: pauses trading if daily/weekly DD exceeds limits
    - Loss streak scaling: reduces position size after consecutive losses
    - Max exposure: limits number of simultaneous open trades
    - Reports risk status to the system via events
    """

    name = "risk_manager"

    def __init__(self, db):
        super().__init__(agent_id="risk_manager", db=db)

    # ──────────────────────────────────────────────────
    # BaseAgent interface
    # ──────────────────────────────────────────────────

    def setup(self):
        # Initialize risk state
        state = self.get_config("risk_state")
        if not state:
            self.set_config("risk_state", {
                "circuit_breaker_active": False,
                "circuit_breaker_until": None,
                "consecutive_losses": 0,
                "daily_pnl": 0.0,
                "weekly_pnl": 0.0,
                "daily_reset_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "weekly_reset_date": datetime.now(timezone.utc).strftime("%Y-%W"),
                "current_scaling": 1.0,
                "open_trades": 0,
            })
        self.logger.info("Risk Manager Agent ready")

    def tick(self):
        """Monitor risk limits and update risk state."""
        state = self.get_config("risk_state") or {}
        now = datetime.now(timezone.utc)

        # Reset daily P&L if new day
        today_str = now.strftime("%Y-%m-%d")
        if state.get("daily_reset_date") != today_str:
            state["daily_pnl"] = 0.0
            state["daily_reset_date"] = today_str
            self.logger.info("Daily P&L reset")

        # Reset weekly P&L if new week
        week_str = now.strftime("%Y-%W")
        if state.get("weekly_reset_date") != week_str:
            state["weekly_pnl"] = 0.0
            state["weekly_reset_date"] = week_str
            state["consecutive_losses"] = 0
            state["current_scaling"] = 1.0
            self.logger.info("Weekly P&L and loss streak reset")

        # Check if circuit breaker cooldown has expired
        if state.get("circuit_breaker_active"):
            cb_until = state.get("circuit_breaker_until")
            if cb_until:
                cb_dt = datetime.fromisoformat(cb_until)
                if now >= cb_dt:
                    state["circuit_breaker_active"] = False
                    state["circuit_breaker_until"] = None
                    self.emit_event("info", "Circuit breaker cooldown expired — trading resumed")
                    self.logger.info("Circuit breaker cooldown expired")

        # Process recent trade results from events table
        self._process_trade_events(state)

        # Check daily DD limit
        max_daily_dd = self.get_config("max_daily_dd") or DEFAULT_MAX_DAILY_DD
        if state["daily_pnl"] < -max_daily_dd and not state.get("circuit_breaker_active"):
            self._trip_circuit_breaker(state, "daily_dd", state["daily_pnl"], max_daily_dd)

        # Check weekly DD limit
        max_weekly_dd = self.get_config("max_weekly_dd") or DEFAULT_MAX_WEEKLY_DD
        if state["weekly_pnl"] < -max_weekly_dd and not state.get("circuit_breaker_active"):
            self._trip_circuit_breaker(state, "weekly_dd", state["weekly_pnl"], max_weekly_dd)

        # Update consecutive loss scaling
        max_losses = self.get_config("max_consecutive_losses") or DEFAULT_MAX_CONSECUTIVE_LOSSES
        if state.get("consecutive_losses", 0) >= max_losses:
            scaling = self.get_config("scaling_factor") or DEFAULT_SCALING_FACTOR
            state["current_scaling"] = scaling
        else:
            state["current_scaling"] = 1.0

        self.set_config("risk_state", state)

        # Emit periodic risk status
        self._emit_risk_status(state)

    def tick_interval(self) -> float:
        return self.get_config("tick_interval", 30)

    # ──────────────────────────────────────────────────
    # Trade event processing
    # ──────────────────────────────────────────────────

    def _process_trade_events(self, state: dict):
        """
        Process trade close events to update P&L and loss streak.
        Reads from the events table for trade_close events since last check.
        """
        last_processed = state.get("last_processed_event_id", 0)

        rows = self.db.fetchall(
            "SELECT id, metadata FROM events "
            "WHERE event_type = 'trade_close' AND id > ? "
            "ORDER BY id",
            (last_processed,),
        )

        for row in rows:
            try:
                meta = json.loads(row["metadata"]) if row["metadata"] else {}
                pnl_pct = meta.get("pnl_pct", 0.0)
                state["daily_pnl"] = state.get("daily_pnl", 0.0) + pnl_pct
                state["weekly_pnl"] = state.get("weekly_pnl", 0.0) + pnl_pct

                if pnl_pct < 0:
                    state["consecutive_losses"] = state.get("consecutive_losses", 0) + 1
                else:
                    state["consecutive_losses"] = 0

                state["last_processed_event_id"] = row["id"]
            except (json.JSONDecodeError, TypeError):
                continue

    # ──────────────────────────────────────────────────
    # Circuit breaker
    # ──────────────────────────────────────────────────

    def _trip_circuit_breaker(self, state: dict, reason: str, current_dd: float, limit: float):
        """Activate the circuit breaker — pauses all trading."""
        cooldown = self.get_config("cooldown_minutes") or DEFAULT_COOLDOWN_MINUTES
        cb_until = datetime.now(timezone.utc) + timedelta(minutes=cooldown)

        state["circuit_breaker_active"] = True
        state["circuit_breaker_until"] = cb_until.isoformat()

        self.emit_event(
            "warning",
            f"CIRCUIT BREAKER TRIPPED: {reason} — "
            f"DD={current_dd:.2%} exceeds limit {limit:.2%}. "
            f"Trading paused until {cb_until.strftime('%H:%M UTC')}",
            metadata={
                "reason": reason,
                "current_dd": current_dd,
                "limit": limit,
                "cooldown_until": cb_until.isoformat(),
            },
        )
        self.logger.warning(
            f"CIRCUIT BREAKER: {reason}, DD={current_dd:.2%} > {limit:.2%}"
        )

    # ──────────────────────────────────────────────────
    # Risk status reporting
    # ──────────────────────────────────────────────────

    def _emit_risk_status(self, state: dict):
        """Emit a risk status event for the dashboard."""
        self.emit_event(
            "risk_status",
            f"Risk: daily={state.get('daily_pnl', 0):.2%}, "
            f"weekly={state.get('weekly_pnl', 0):.2%}, "
            f"losses={state.get('consecutive_losses', 0)}, "
            f"scaling={state.get('current_scaling', 1.0):.0%}, "
            f"CB={'ACTIVE' if state.get('circuit_breaker_active') else 'off'}",
            metadata={
                "daily_pnl": state.get("daily_pnl", 0),
                "weekly_pnl": state.get("weekly_pnl", 0),
                "consecutive_losses": state.get("consecutive_losses", 0),
                "current_scaling": state.get("current_scaling", 1.0),
                "circuit_breaker_active": state.get("circuit_breaker_active", False),
            },
        )


# ──────────────────────────────────────────────────
# Public API for other agents to query risk state
# ──────────────────────────────────────────────────

def is_trading_allowed(db) -> bool:
    """Check if trading is allowed (circuit breaker not active)."""
    row = db.fetchone(
        "SELECT config FROM agent_registry WHERE id = ?", ("risk_manager",)
    )
    if not row or not row["config"]:
        return True
    config = json.loads(row["config"]) if isinstance(row["config"], str) else row["config"]
    state = config.get("risk_state", {})
    return not state.get("circuit_breaker_active", False)


def get_position_scaling(db) -> float:
    """Get current position scaling factor (1.0 = full size, 0.5 = half size)."""
    row = db.fetchone(
        "SELECT config FROM agent_registry WHERE id = ?", ("risk_manager",)
    )
    if not row or not row["config"]:
        return 1.0
    config = json.loads(row["config"]) if isinstance(row["config"], str) else row["config"]
    state = config.get("risk_state", {})
    return state.get("current_scaling", 1.0)


def get_max_open_trades(db) -> int:
    """Get max allowed simultaneous open trades."""
    row = db.fetchone(
        "SELECT config FROM agent_registry WHERE id = ?", ("risk_manager",)
    )
    if not row or not row["config"]:
        return DEFAULT_MAX_OPEN_TRADES
    config = json.loads(row["config"]) if isinstance(row["config"], str) else row["config"]
    return config.get("max_open_trades", DEFAULT_MAX_OPEN_TRADES)
