"""Risk Engine V2: equity-based limits, persistent breakers and risk profiles."""
import json
from datetime import datetime, timezone

from agents.base_agent import BaseAgent
from core.config import INITIAL_BALANCE, PIP_VALUE


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
        state = self.get_config("risk_state") or {}
        equity = self._current_equity()
        now = datetime.now(timezone.utc)
        defaults = {
            "circuit_breaker_active": False,
            "circuit_breaker_reason": None,
            "circuit_breaker_scope": None,
            "consecutive_losses": 0,
            "daily_reset_date": now.strftime("%Y-%m-%d"),
            "weekly_reset_date": now.strftime("%Y-%W"),
            "daily_start_equity": equity,
            "daily_peak_equity": equity,
            "weekly_start_equity": equity,
            "weekly_peak_equity": equity,
            "daily_drawdown": 0.0,
            "weekly_drawdown": 0.0,
            "current_equity": equity,
            "current_scaling": 1.0,
            "open_trades": 0,
            "portfolio_heat": 0.0,
            "last_processed_event_id": 0,
        }
        for k, v in defaults.items():
            state.setdefault(k, v)
        self.set_config("risk_state", state)
        self.logger.info(f"Risk Engine V2 ready — profile={self._profile_name()}")

    def tick(self):
        state = self.get_config("risk_state") or {}
        now = datetime.now(timezone.utc)
        profile = self._profile()
        equity = self._current_equity()

        self._reset_periods_if_needed(state, equity, now)
        self._process_trade_events(state)

        state["current_equity"] = equity
        state["daily_peak_equity"] = max(float(state.get("daily_peak_equity") or equity), equity)
        state["weekly_peak_equity"] = max(float(state.get("weekly_peak_equity") or equity), equity)
        state["daily_drawdown"] = self._drawdown_from_reference(
            equity, max(float(state.get("daily_start_equity") or equity), float(state["daily_peak_equity"]))
        )
        state["weekly_drawdown"] = self._drawdown_from_reference(
            equity, max(float(state.get("weekly_start_equity") or equity), float(state["weekly_peak_equity"]))
        )

        open_row = self.db.fetchone("SELECT COUNT(*) AS cnt FROM live_trades WHERE status='open'")
        state["open_trades"] = int(open_row["cnt"] or 0) if open_row else 0
        state["portfolio_heat"] = self._calculate_portfolio_heat(equity)

        if not state.get("circuit_breaker_active"):
            if state["daily_drawdown"] >= profile["max_daily_dd"]:
                self._trip_circuit_breaker(
                    state, "daily_dd", "daily", state["daily_drawdown"], profile["max_daily_dd"]
                )
            elif state["weekly_drawdown"] >= profile["max_weekly_dd"]:
                self._trip_circuit_breaker(
                    state, "weekly_dd", "weekly", state["weekly_drawdown"], profile["max_weekly_dd"]
                )

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

    def _current_equity(self) -> float:
        try:
            import MetaTrader5 as mt5
            account = mt5.account_info()
            if account and account.equity > 0:
                return float(account.equity)
        except Exception:
            pass
        return float(INITIAL_BALANCE)

    def _reset_periods_if_needed(self, state: dict, equity: float, now: datetime):
        today = now.strftime("%Y-%m-%d")
        if state.get("daily_reset_date") != today:
            state["daily_reset_date"] = today
            state["daily_start_equity"] = equity
            state["daily_peak_equity"] = equity
            state["daily_drawdown"] = 0.0
            # A daily breaker remains locked for the whole UTC trading day.
            if state.get("circuit_breaker_scope") == "daily":
                self._clear_circuit_breaker(state, "new trading day")

        week = now.strftime("%Y-%W")
        if state.get("weekly_reset_date") != week:
            state["weekly_reset_date"] = week
            state["weekly_start_equity"] = equity
            state["weekly_peak_equity"] = equity
            state["weekly_drawdown"] = 0.0
            state["consecutive_losses"] = 0
            if state.get("circuit_breaker_scope") == "weekly":
                self._clear_circuit_breaker(state, "new trading week")

    def _calculate_portfolio_heat(self, equity: float) -> float:
        rows = self.db.fetchall(
            "SELECT lot, sl, entry_price FROM live_trades WHERE status='open'"
        )
        total_risk = 0.0
        for r in rows:
            sl_dist = abs(float(r["entry_price"] or 0) - float(r["sl"] or 0))
            total_risk += float(r["lot"] or 0) * sl_dist * PIP_VALUE
        return total_risk / equity if equity > 0 else 0.0

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
        """Reduce risk as drawdown/heat/loss streak deteriorate; never increase it."""
        scale = 1.0
        daily_ratio = state.get("daily_drawdown", 0.0) / max(profile["max_daily_dd"], 1e-9)
        weekly_ratio = state.get("weekly_drawdown", 0.0) / max(profile["max_weekly_dd"], 1e-9)
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
        if heat >= 0.80 * heat_limit:
            scale *= 0.50
        elif heat >= 0.60 * heat_limit:
            scale *= 0.75

        if state.get("circuit_breaker_active"):
            return 0.0
        return round(max(0.10, min(scale, 1.0)), 4)

    def _trip_circuit_breaker(self, state: dict, reason: str, scope: str, current_dd: float, limit: float):
        state["circuit_breaker_active"] = True
        state["circuit_breaker_reason"] = reason
        state["circuit_breaker_scope"] = scope
        state["current_scaling"] = 0.0
        self.emit_event(
            "warning",
            f"CIRCUIT BREAKER: {reason} — DD={current_dd:.2%} >= {limit:.2%}. "
            f"Locked until next {scope} reset.",
            metadata={"reason": reason, "scope": scope, "current_dd": current_dd, "limit": limit},
        )
        self.logger.warning(f"Circuit breaker locked ({scope}): {current_dd:.2%} >= {limit:.2%}")

    def _clear_circuit_breaker(self, state: dict, reason: str):
        state["circuit_breaker_active"] = False
        state["circuit_breaker_reason"] = None
        state["circuit_breaker_scope"] = None
        self.emit_event("info", f"Circuit breaker cleared: {reason}")

    def _emit_risk_status(self, state: dict, profile: dict):
        self.emit_event(
            "risk_status",
            f"Risk[{self._profile_name()}]: dailyDD={state.get('daily_drawdown', 0):.2%}, "
            f"weeklyDD={state.get('weekly_drawdown', 0):.2%}, "
            f"scale={state.get('current_scaling', 1):.0%}, heat={state.get('portfolio_heat', 0):.1%}, "
            f"CB={'ACTIVE' if state.get('circuit_breaker_active') else 'off'}",
            metadata={
                "risk_profile": self._profile_name(),
                "risk_per_trade": profile["risk_per_trade"],
                "daily_drawdown": state.get("daily_drawdown", 0.0),
                "weekly_drawdown": state.get("weekly_drawdown", 0.0),
                "current_scaling": state.get("current_scaling", 1.0),
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


def is_trading_allowed(db) -> bool:
    config, _ = _read_risk_config(db)
    return not config.get("risk_state", {}).get("circuit_breaker_active", False)


def get_position_scaling(db) -> float:
    config, _ = _read_risk_config(db)
    return float(config.get("risk_state", {}).get("current_scaling", 1.0) or 0.0)


def get_base_risk_pct(db) -> float:
    _, profile = _read_risk_config(db)
    return float(profile["risk_per_trade"])


def get_effective_risk_pct(db) -> float:
    """Current per-trade risk after profile selection and dynamic de-risking."""
    return get_base_risk_pct(db) * get_position_scaling(db)


def get_max_open_trades(db) -> int:
    config, profile = _read_risk_config(db)
    return int(config.get("max_open_trades", profile["max_open_trades"]))


def get_max_portfolio_heat(db) -> float:
    config, profile = _read_risk_config(db)
    return float(config.get("max_portfolio_heat", profile["max_portfolio_heat"]))
