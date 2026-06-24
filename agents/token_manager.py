"""Token Manager: tracks and optimizes API token consumption."""
from agents.base_agent import BaseAgent


class TokenManager(BaseAgent):
    name = "token_manager"

    def __init__(self, db):
        super().__init__(agent_id="token_manager", db=db)

    def setup(self):
        self.logger.info("Token Manager ready")

    def tick(self):
        summary = self.compute_summary()
        if summary["total_calls"] > 0:
            self.logger.info(
                f"Tokens — calls: {summary['total_calls']}, "
                f"cost: ${summary['total_cost']:.4f}, "
                f"agents: {len(summary['by_agent'])}"
            )
            self.emit_event("info", "token_summary", summary)

    def tick_interval(self) -> float:
        return self.get_config("tick_interval", 60)

    def compute_summary(self) -> dict:
        rows = self.db.fetchall(
            "SELECT agent_id, model, "
            "SUM(tokens_in) as total_in, SUM(tokens_out) as total_out, "
            "SUM(cost_usd) as total_cost, COUNT(*) as calls, "
            "SUM(cached_tokens) as cached "
            "FROM token_usage GROUP BY agent_id, model"
        )
        by_agent = {}
        by_model = {}
        total_cost = 0.0
        total_calls = 0
        total_cached = 0
        for row in rows:
            agent_id = row["agent_id"]
            model = row["model"]
            cost = row["total_cost"] or 0
            calls = row["calls"] or 0
            cached = row["cached"] or 0
            if agent_id not in by_agent:
                by_agent[agent_id] = {"cost": 0, "calls": 0}
            by_agent[agent_id]["cost"] += cost
            by_agent[agent_id]["calls"] += calls
            if model not in by_model:
                by_model[model] = {"cost": 0, "calls": 0}
            by_model[model]["cost"] += cost
            by_model[model]["calls"] += calls
            total_cost += cost
            total_calls += calls
            total_cached += cached
        return {
            "total_cost": round(total_cost, 6),
            "total_calls": total_calls,
            "total_cached_tokens": total_cached,
            "by_agent": by_agent,
            "by_model": by_model,
        }
