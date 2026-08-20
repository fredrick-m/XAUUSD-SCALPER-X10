"""Risk Engine V2: equity-based limits, persistent breakers and risk profiles.

Safety invariants
-----------------
- Drawdown anchors are created only from a real MT5 account equity sample.
- Trading is fail-closed while MT5 equity is unavailable.
- Demo execution has an explicit master switch, default OFF.
- A weekly drawdown lock always dominates a daily lock.
- State is persisted so restarts do not forgive drawdown.
"""
import json
from datetime import datetime, timezone
from typing import Optional

from agents.base_agent import BaseAgent
from core.config import PIP_VALUE, DEFAULT_RISK_PCT


RISK_PROFILES = {
    "conservative": {
        "risk_per_trade": 0.01,
        "max_daily_dd": 0.03,
        "max_weekly_dd": 0.06,
        "max_portfolio_heat": 0.08,
        "max_open_trades": 6,
        "max_consecutive_losses": 4,
    },
    "growth": {
        "risk_per_trade": 0.02,
        "max_daily_dd": 0.06,
        "max_weekly_dd": 0.12,
        "max_portfolio_heat": 0.12,
        "max_open_trades": 10,
        "max_consecutive_losses": 5,
    },
    # Research/demo profile only. paper_trade independently refuses live MT5.
    "x10_research": {
        "risk_per_trade": 0.04,
        "max_daily_dd": 0.10,
        "max_weekly_dd": 0.20,
        "max_portfolio_heat": 0.20,
        "max_open_trades": 12,
        "max_consecutive_losses": 5,
    },
}
DEFAULT_RISK_PROFILE = "x10_research"


class RiskManager(BaseAgent):
    name = "risk_manager"

    def __init__(self, db):
        super().__init__(agent_id="risk_manager", db=db)

    def setup(self):
        # Explicit human-controlled switch. Never inherit an implicit ON state
        # from the absence of a config key.
        if self.get_config("demo_execution_enabled", None) is None:
            self.set_config("demo_execution_enabled", False)

        state = self.get_config("risk_state") or {}
        now = datetime.now(timezone.utc)
        equity = self._current_equity()
        defaults = {
            "circuit_breaker_active": False,
            "circuit_breaker_reason": None,
            "circuit_breaker_scope": None,
            "consecutive_losses": 0,
            "daily_reset_date": now.strftime("%Y-%m-%d"),
            "weekly_reset_date": now.strftime("%Y-%W"),
            "daily_start_equity": None,
            "daily_peak_equity": None,
            "weekly_start_equity": None,
            "weekly_peak_equity": None,
            "daily_drawdown": 0.0,
            "weekly_drawdown": 0.0,
            "current_equity": None,
            "equity_ready": False,
            "equity_source": "unavailable",
            "equity_anchor_source": None,
            "last_equity_at": None,
            "current_scaling": 0.0,
            "open_trades": 0,
            "portfolio_heat": 0.0,
            "last_processed_event_id": 0,
        }
        for k, v in defaults.items():
            state.setdefault(k, v)

        if equity is not None:
            self._ensure_equity_anchors(state, equity, now)
        else:
            self._lock_for_equity_unavailable(state)

        self.set_config("risk_state", state)
        self.logger.info(
            f"Risk Engine V2 ready — profile={self._profile_name()} "
            f"equity_ready={bool(state.get('equity_ready'))} "
            f"demo_execution={bool(self.get_config('demo_execution_enabled', False))}"
        )

    def tick(self):
        state = self.get_config("risk_state") or {}
        now = datetime.now(timezone.utc)
        profile = self._profile()
        equity = self._current_equity()
        self._process_trade_events(state)

        if equity is None:
            state["equity_ready"] = False
            state["equity_source"] = "unavailable"
            state["current_scaling"] = 0.0
            self._lock_for_equity_unavailable(state)
            self.set_config("risk_state", state)
            self._emit_risk_status(state, profile)
            return

        self._ensure_equity_anchors(state, equity, now)
        self._reset_periods_if_needed(state, equity, now)
        state["equity_ready"] = True
        state["equity_source"] = "mt5"
        state["current_equity"] = equity
        state["last_equity_at"] = now.isoformat()

        daily_peak = float(state.get("daily_peak_equity") or equity)
        weekly_peak = float(state.get("weekly_peak_equity") or equity)
        state["daily_peak_equity"] = max(daily_peak, equity)
        state["weekly_peak_equity"] = max(weekly_peak, equity)
        state["daily_drawdown"] = self._drawdown_from_reference(
            equity,
            max(float(state.get("daily_start_equity") or equity), float(state["daily_peak_equity"])),
        )
        state["weekly_drawdown"] = self._drawdown_from_reference(
            equity,
            max(float(state.get("weekly_start_equity") or equity), float(state["weekly_peak_equity"])),
        )

        open_row = self.db.fetchone("SELECT COUNT(*) AS cnt FROM live_trades WHERE status='open'")
        state["open_trades"] = int(open_row["cnt"] or 0) if open_row else 0
        state["portfolio_heat"] = self._calculate_portfolio_heat(equity)
        self._evaluate_breakers(state, profile)
        state["current_scaling"] = self._dynamic_scaling(state, profile)
        self.set_config("risk_state", state)
        self._emit_risk_status(state, profile)

    def tick_interval(self) -> float:
        return self.get_config("tick_interval", 30)

    def _profile_name(self) -> str:
        name = self.get_config("risk_profile") or DEFAULT_RISK_PROFILE
        return name if name in RISK_PROFILES else DEFAULT_RISK_PROFILE

    def _profile(self) -> dict:
        return dict(RISK_PROFILES[self._profile_name()])

    @staticmethod
    def _drawdown_from_reference(equity: float, reference: float) -> float:
        if reference <= 0:
            return 0.0
        return max(0.0, (reference - equity) / reference)

    def _current_equity(self) -> Optional[float]:
        """Return a real MT5 equity sample, never a synthetic live fallback."""
        try:
            import MetaTrader5 as mt5
            account = mt5.account_info()
            if account is not None:
                equity = float(getattr(account, "equity", 0.0) or 0.0)
                if equity > 0:
                    return equity
        except Exception:
            pass
        return None

    def _ensure_equity_anchors(self, state: dict, equity: float, now: datetime):
        anchors_valid = (
            state.get("equity_anchor_source") == "mt5"
            and state.get("daily_start_equity") is not None
            and state.get("weekly_start_equity") is not None
            and state.get("daily_peak_equity") is not None
            and state.get("weekly_peak_equity") is not None
        )
        if not anchors_valid:
            state["daily_reset_date"] = now.strftime("%Y-%m-%d")
            state["weekly_reset_date"] = now.strftime("%Y-%W")
            state["daily_start_equity"] = equity
            state["daily_peak_equity"] = equity
            state["weekly_start_equity"] = equity
            state["weekly_peak_equity"] = equity
            state["daily_drawdown"] = 0.0
            state["weekly_drawdown"] = 0.0
            state["equity_anchor_source"] = "mt5"
        state["equity_ready"] = True
        state["equity_source"] = "mt5"
        state["current_equity"] = equity
        state["last_equity_at"] = now.isoformat()
        if state.get("circuit_breaker_scope") == "readiness":
            self._clear_circuit_breaker(state, "MT5 equity available")

    def _lock_for_equity_unavailable(self, state: dict):
        if state.get("circuit_breaker_active"):
            return
        state["circuit_breaker_active"] = True
        state["circuit_breaker_reason"] = "equity_unavailable"
        state["circuit_breaker_scope"] = "readiness"
        state["current_scaling"] = 0.0
        self.emit_event(
            "warning",
            "RISK LOCK: MT5 equity unavailable. Trading blocked until a real account equity sample is available.",
            metadata={"reason": "equity_unavailable", "scope": "readiness"},
        )

    def _reset_periods_if_needed(self, state: dict, equity: float, now: datetime):
        week = now.strftime("%Y-%W")
        if state.get("weekly_reset_date") != week:
            state["weekly_reset_date"] = week
            state["weekly_start_equity"] = equity
            state["weekly_peak_equity"] = equity
            state["weekly_drawdown"] = 0.0
            state["consecutive_losses"] = 0
            if state.get("circuit_breaker_scope") == "weekly":
                self._clear_circuit_breaker(state, "new trading week")

        today = now.strftime("%Y-%m-%d")
        if state.get("daily_reset_date") != today:
            state["daily_reset_date"] = today
            state["daily_start_equity"] = equity
            state["daily_peak_equity"] = equity
            state["daily_drawdown"] = 0.0
            if state.get("circuit_breaker_scope") == "daily":
                self._clear_circuit_breaker(state, "new trading day")

    def _evaluate_breakers(self, state: dict, profile: dict):
        weekly_dd = float(state.get("weekly_drawdown", 0.0) or 0.0)
        daily_dd = float(state.get("daily_drawdown", 0.0) or 0.0)
        if weekly_dd >= profile["max_weekly_dd"]:
            if state.get("circuit_breaker_scope") != "weekly":
                self._trip_circuit_breaker(
                    state, "weekly_dd", "weekly", weekly_dd, profile["max_weekly_dd"]
                )
            return
        if daily_dd >= profile["max_daily_dd"] and not state.get("circuit_breaker_active"):
            self._trip_circuit_breaker(
                state, "daily_dd", "daily", daily_dd, profile["max_daily_dd"]
            )

    def _calculate_portfolio_heat(self, equity: float) -> float:
        rows = self.db.fetchall("SELECT lot, sl, entry_price FROM live_trades WHERE status='open'")
        total_risk = 0.0
        for r in rows:
            lot = float(r["lot"] or 0.0)
            entry = float(r["entry_price"] or 0.0)
            sl = float(r["sl"] or 0.0)
            if lot <= 0 or entry <= 0:
                continue
            if sl <= 0:
                total_risk += equity
                continue
            total_risk += lot * abs(entry - sl) * PIP_VALUE
        return total_risk / equity if equity > 0 else 1.0

    def _process_trade_events(self, state: dict):
        last_id = int(state.get("last_processed_event_id", 0) or 0)
        rows = self.db.fetchall(
            "SELECT id, metadata FROM events WHERE event_type='trade_close' AND id>? ORDER BY id",
            (last_id,),
        )
        for row in rows:
            try:
                meta = json.loads(row["metadata"]) if row["metadata"] else {}
                pnl = float(meta.get("pnl", 0.0) or 0.0)
                if pnl < 0:
                    state["consecutive_losses"] = int(state.get("consecutive_losses", 0) or 0) + 1
                elif pnl > 0:
                    state["consecutive_losses"] = 0
                state["last_processed_event_id"] = row["id"]
            except (json.JSONDecodeError, TypeError, ValueError):
                state["last_processed_event_id"] = row["id"]

    def _dynamic_scaling(self, state: dict, profile: dict) -> float:
        if not state.get("equity_ready", False) or state.get("circuit_breaker_active"):
            return 0.0
        scale = 1.0
        daily_ratio = float(state.get("daily_drawdown", 0.0) or 0.0) / max(profile["max_daily_dd"], 1e-9)
        weekly_ratio = float(state.get("weekly_drawdown", 0.0) or 0.0) / max(profile["max_weekly_dd"], 1e-9)
        stress = max(daily_ratio, weekly_ratio)
        if stress >= 0.75:
            scale *= 0.25
        elif stress >= 0.50:
            scale *= 0.50
        elif stress >= 0.25:
            scale *= 0.75
        losses = int(state.get("consecutive_losses", 0) or 0)
        max_losses = int(profile["max_consecutive_losses"])
        if losses >= max_losses:
            scale *= 0.50
        elif losses >= max(2, max_losses - 2):
            scale *= 0.75
        heat = float(state.get("portfolio_heat", 0.0) or 0.0)
        heat_limit = max(profile["max_portfolio_heat"], 1e-9)
        if heat >= heat_limit:
            return 0.0
        if heat >= 0.80 * heat_limit:
            scale *= 0.50
        elif heat >= 0.60 * heat_limit:
            scale *= 0.75
        return round(max(0.10, min(scale, 1.0)), 4)

    def _trip_circuit_breaker(self, state: dict, reason: str, scope: str, current_dd: float, limit: float):
        previous_scope = state.get("circuit_breaker_scope")
        state["circuit_breaker_active"] = True
        state["circuit_breaker_reason"] = reason
        state["circuit_breaker_scope"] = scope
        state["current_scaling"] = 0.0
        self.emit_event(
            "warning",
            f"CIRCUIT BREAKER: {reason} — DD={current_dd:.2%} >= {limit:.2%}. Locked until next {scope} reset.",
            metadata={
                "reason": reason, "scope": scope, "previous_scope": previous_scope,
                "current_dd": current_dd, "limit": limit,
            },
        )
        self.logger.warning(f"Circuit breaker locked ({scope}): {current_dd:.2%} >= {limit:.2%}")

    def _clear_circuit_breaker(self, state: dict, reason: str):
        state["circuit_breaker_active"] = False
        state["circuit_breaker_reason"] = None
        state["circuit_breaker_scope"] = None
        self.emit_event("info", f"Circuit breaker cleared: {reason}")

    def _emit_risk_status(self, state: dict, profile: dict):
        enabled = bool(self.get_config("demo_execution_enabled", False))
        self.emit_event(
            "risk_status",
            f"Risk[{self._profile_name()}]: demo={'ON' if enabled else 'OFF'}, "
            f"equity_ready={bool(state.get('equity_ready'))}, "
            f"dailyDD={state.get('daily_drawdown', 0):.2%}, weeklyDD={state.get('weekly_drawdown', 0):.2%}, "
            f"scale={state.get('current_scaling', 0):.0%}, heat={state.get('portfolio_heat', 0):.1%}, "
            f"CB={'ACTIVE' if state.get('circuit_breaker_active') else 'off'}",
            metadata={
                "demo_execution_enabled": enabled,
                "risk_profile": self._profile_name(),
                "risk_per_trade": profile["risk_per_trade"],
                "equity_ready": state.get("equity_ready", False),
                "equity_source": state.get("equity_source"),
                "current_equity": state.get("current_equity"),
                "daily_drawdown": state.get("daily_drawdown", 0.0),
                "weekly_drawdown": state.get("weekly_drawdown", 0.0),
                "current_scaling": state.get("current_scaling", 0.0),
                "portfolio_heat": state.get("portfolio_heat", 0.0),
                "open_trades": state.get("open_trades", 0),
                "consecutive_losses": state.get("consecutive_losses", 0),
                "circuit_breaker_active": state.get("circuit_breaker_active", False),
                "circuit_breaker_scope": state.get("circuit_breaker_scope"),
            },
        )


def _read_risk_config(db) -> tuple[dict, dict]:
    row = db.fetchone("SELECT config FROM agent_registry WHERE id=?", ("risk_manager",))
    config = {}
    if row and row["config"]:
        try:
            config = json.loads(row["config"]) if isinstance(row["config"], str) else dict(row["config"])
        except (json.JSONDecodeError, TypeError, ValueError):
            config = {}
    name = config.get("risk_profile", DEFAULT_RISK_PROFILE)
    if name not in RISK_PROFILES:
        name = DEFAULT_RISK_PROFILE
    return config, RISK_PROFILES[name]


def is_demo_execution_enabled(db) -> bool:
    config, _ = _read_risk_config(db)
    return config.get("demo_execution_enabled") is True


def is_trading_allowed(db) -> bool:
    ready, _ = get_risk_readiness(db)
    return ready


def get_base_risk_pct(db) -> float:
    _, profile = _read_risk_config(db)
    return float(profile["risk_per_trade"])


def get_position_scaling(db) -> float:
    config, profile = _read_risk_config(db)
    state = config.get("risk_state", {})
    if config.get("demo_execution_enabled") is not True:
        return 0.0
    if not state.get("equity_ready", False) or state.get("circuit_breaker_active", False):
        return 0.0
    stress_scale = float(state.get("current_scaling", 0.0) or 0.0)
    profile_ratio = float(profile["risk_per_trade"]) / max(float(DEFAULT_RISK_PCT), 1e-9)
    return max(0.0, profile_ratio * stress_scale)


def get_effective_risk_pct(db) -> float:
    config, profile = _read_risk_config(db)
    state = config.get("risk_state", {})
    if config.get("demo_execution_enabled") is not True:
        return 0.0
    if not state.get("equity_ready", False) or state.get("circuit_breaker_active", False):
        return 0.0
    stress_scale = float(state.get("current_scaling", 0.0) or 0.0)
    return float(profile["risk_per_trade"]) * stress_scale


def get_max_open_trades(db) -> int:
    config, profile = _read_risk_config(db)
    return int(config.get("max_open_trades", profile["max_open_trades"]))


def get_max_portfolio_heat(db) -> float:
    config, profile = _read_risk_config(db)
    return float(config.get("max_portfolio_heat", profile["max_portfolio_heat"]))


def get_risk_readiness(db) -> tuple[bool, str]:
    config, _ = _read_risk_config(db)
    state = config.get("risk_state", {})
    if not state:
        return False, "risk_state_missing"
    if not state.get("equity_ready", False):
        return False, "mt5_equity_unavailable"
    if state.get("circuit_breaker_active", False):
        scope = state.get("circuit_breaker_scope") or "unknown"
        return False, f"circuit_breaker_active:{scope}"
    if config.get("demo_execution_enabled") is not True:
        return False, "demo_execution_disabled"
    return True, "ready"
