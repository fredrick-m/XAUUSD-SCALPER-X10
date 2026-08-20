import json

from agents.correlation_agent import CorrelationAgent
from core.db import Database


def test_apply_portfolio_state_demotes_stale_validated_strategy(tmp_path):
    db = Database(tmp_path / "portfolio.sqlite")
    try:
        db.init_schema()
        db.execute(
            "INSERT INTO strategies "
            "(id, file_path, status, walk_forward_passed, best_config) "
            "VALUES ('KEEP', 'keep.py', 'validated', 1, '{}')"
        )
        db.execute(
            "INSERT INTO strategies "
            "(id, file_path, status, walk_forward_passed, best_config) "
            "VALUES ('DROP', 'drop.py', 'validated', 1, '{}')"
        )

        agent = CorrelationAgent.__new__(CorrelationAgent)
        agent.db = db
        agent.agent_id = "correlation_agent"
        agent.logger = __import__("logging").getLogger("test.correlation_agent")

        strategies = [{"id": "KEEP"}, {"id": "DROP"}]
        agent._apply_portfolio_state(
            strategies,
            portfolio=["KEEP"],
            scores={"KEEP": 80.0},
            duplicate_of={},
            rejection_reasons={"DROP": "statistical_gate_failed"},
        )

        keep = db.fetchone("SELECT status, best_config FROM strategies WHERE id='KEEP'")
        drop = db.fetchone("SELECT status, best_config FROM strategies WHERE id='DROP'")

        assert keep["status"] == "validated"
        assert drop["status"] == "portfolio_reserve"

        keep_cfg = json.loads(keep["best_config"])
        drop_cfg = json.loads(drop["best_config"])
        assert keep_cfg["portfolio_selected"] is True
        assert drop_cfg["portfolio_selected"] is False
        assert drop_cfg["portfolio_rejection_reason"] == "statistical_gate_failed"
    finally:
        db.close()
