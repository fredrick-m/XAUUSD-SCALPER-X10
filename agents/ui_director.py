"""UI Director agent: serves the Flask dashboard and computes aggregate stats."""
import threading

from agents.base_agent import BaseAgent
from core.config import DASHBOARD_PORT


class UIDirector(BaseAgent):
    """Starts the Flask dashboard in a daemon thread and periodically emits system stats."""

    name = "ui_director"

    def __init__(self, db):
        super().__init__(agent_id="ui_director", db=db)
        self._server_started = False

    # ── Abstract interface ────────────────────────────────────────────────────

    def setup(self):
        self._start_dashboard_server()
        self.logger.info(f"UI Director ready — dashboard on port {DASHBOARD_PORT}")

    def tick(self):
        stats = self._compute_dashboard_stats()
        self.logger.debug(f"Dashboard stats: {stats}")

    def tick_interval(self) -> float:
        return self.get_config("tick_interval", 30)

    # ── Dashboard server ──────────────────────────────────────────────────────

    def _start_dashboard_server(self):
        if self._server_started:
            return
        try:
            from dashboard.app import app
            thread = threading.Thread(
                target=app.run,
                kwargs={
                    "host": "0.0.0.0",
                    "port": DASHBOARD_PORT,
                    "debug": False,
                    "use_reloader": False,
                },
                daemon=True,
            )
            thread.start()
            self._server_started = True
            self.emit_event(
                "milestone",
                f"Dashboard server started on port {DASHBOARD_PORT}",
            )
        except Exception as exc:
            self.emit_event("error", f"Failed to start dashboard server: {exc}")

    # ── Stats computation ─────────────────────────────────────────────────────

    def _compute_dashboard_stats(self) -> dict:
        agents_total = (
            self.db.fetchone("SELECT COUNT(*) AS c FROM agent_registry")["c"] or 0
        )
        agents_running = (
            self.db.fetchone(
                "SELECT COUNT(*) AS c FROM agent_registry WHERE status = 'running'"
            )["c"]
            or 0
        )
        total_strategies = (
            self.db.fetchone("SELECT COUNT(*) AS c FROM strategies")["c"] or 0
        )
        validated_strategies = (
            self.db.fetchone(
                "SELECT COUNT(*) AS c FROM strategies WHERE status = 'validated'"
            )["c"]
            or 0
        )
        cost_row = self.db.fetchone(
            "SELECT COALESCE(SUM(cost_usd), 0) AS c FROM token_usage"
        )
        total_cost_usd = float(cost_row["c"]) if cost_row else 0.0

        return {
            "agents_total": agents_total,
            "agents_running": agents_running,
            "total_strategies": total_strategies,
            "validated_strategies": validated_strategies,
            "total_cost_usd": total_cost_usd,
        }
