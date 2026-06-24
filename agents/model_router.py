"""Model Router: picks the optimal Claude model for each task type."""
from agents.base_agent import BaseAgent

_ROUTING_TABLE = {
    "syntax_check": "haiku",
    "parse_data": "haiku",
    "classify": "haiku",
    "format": "haiku",
    "quality_check": "haiku",
    "analyze_results": "sonnet",
    "evaluate_plugin": "sonnet",
    "debug_strategy": "sonnet",
    "summarize": "sonnet",
    "generate_strategy": "opus",
    "meta_decision": "opus",
    "create_agent": "opus",
    "complex_analysis": "opus",
}

_DEFAULT_MODEL = "sonnet"


class ModelRouter(BaseAgent):
    name = "model_router"

    def __init__(self, db):
        super().__init__(agent_id="model_router", db=db)

    def setup(self):
        self.logger.info("Model Router ready")

    def tick(self):
        rows = self.db.fetchall(
            "SELECT model, task_type, COUNT(*) as calls, AVG(tokens_out) as avg_out "
            "FROM token_usage GROUP BY model, task_type"
        )
        if rows:
            self.logger.debug(f"Model usage: {len(rows)} task/model combos tracked")

    def tick_interval(self) -> float:
        return self.get_config("tick_interval", 30)

    @staticmethod
    def route_task(task_type: str) -> str:
        return _ROUTING_TABLE.get(task_type, _DEFAULT_MODEL)
