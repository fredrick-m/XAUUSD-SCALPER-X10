"""Base class for all agents in the multi-agent system."""
import json
import time
import traceback
from abc import ABC, abstractmethod
from typing import Any, Optional

from core.api_client import APIClient
from core.logger import get_logger, log_event


class BaseAgent(ABC):
    """Abstract base class. Subclasses implement setup(), tick(), cleanup()."""

    name: str = "unnamed_agent"

    def __init__(self, agent_id: str, db):
        self.agent_id = agent_id
        self.db = db
        self.logger = get_logger(self.name)
        self.api = APIClient(db=db, agent_id=agent_id)
        self._shutdown = False

    @abstractmethod
    def setup(self):
        """Called once when agent starts."""

    @abstractmethod
    def tick(self):
        """Called repeatedly — the agent's main work."""

    @abstractmethod
    def tick_interval(self) -> float:
        """Seconds to sleep between ticks."""

    def cleanup(self):
        """Called once on shutdown. Override if needed."""

    def run(self):
        """Main loop: setup -> tick -> cleanup. Do not override."""
        self.logger.info(f"Agent {self.name} ({self.agent_id}) starting")
        self.emit_event("info", f"Agent {self.name} started")

        try:
            self.setup()
        except Exception as e:
            self.logger.error(f"Setup failed: {e}")
            self.emit_event("error", f"Setup failed: {traceback.format_exc()}")
            return

        while not self._shutdown:
            self.update_heartbeat()
            try:
                self.tick()
            except Exception as e:
                self.logger.error(f"Tick error: {e}")
                self.emit_event("error", f"Tick error: {traceback.format_exc()}")
                self._increment_error_count()
            time.sleep(self.tick_interval())

        self.logger.info(f"Agent {self.name} shutting down")
        try:
            self.cleanup()
        except Exception as e:
            self.logger.error(f"Cleanup failed: {e}")
        self.emit_event("info", f"Agent {self.name} stopped")

    def request_shutdown(self):
        self._shutdown = True

    def emit_event(self, event_type: str, message: str, metadata: Optional[dict] = None):
        log_event(self.db, self.agent_id, event_type, message, metadata)

    def post_task(self, target_agent: str, task_type: str, payload: dict, priority: int = 5):
        self.db.execute(
            "INSERT INTO task_queue (agent_target, task_type, payload, priority, created_by) "
            "VALUES (?, ?, ?, ?, ?)",
            (target_agent, task_type, json.dumps(payload), priority, self.agent_id),
        )

    def get_pending_tasks(self) -> list:
        rows = self.db.fetchall(
            "SELECT * FROM task_queue WHERE agent_target = ? AND status = 'pending' ORDER BY priority, created_at",
            (self.agent_id,),
        )
        return [dict(row) for row in rows]

    def complete_task(self, task_id: int, result: Optional[dict] = None):
        result_json = json.dumps(result) if result else None
        self.db.execute(
            "UPDATE task_queue SET status = 'completed', completed_at = datetime('now'), result = ? WHERE id = ?",
            (result_json, task_id),
        )

    def fail_task(self, task_id: int, error: str):
        self.db.execute(
            "UPDATE task_queue SET status = 'failed', result = ? WHERE id = ?",
            (json.dumps({"error": error}), task_id),
        )

    def update_heartbeat(self):
        self.db.update_heartbeat(self.agent_id)

    def get_config(self, key: str, default: Any = None) -> Any:
        row = self.db.fetchone("SELECT config FROM agent_registry WHERE id = ?", (self.agent_id,))
        if row and row["config"]:
            config = json.loads(row["config"]) if isinstance(row["config"], str) else row["config"]
            return config.get(key, default)
        return default

    def set_config(self, key: str, value: Any):
        row = self.db.fetchone("SELECT config FROM agent_registry WHERE id = ?", (self.agent_id,))
        config = {}
        if row and row["config"]:
            config = json.loads(row["config"]) if isinstance(row["config"], str) else row["config"]
        config[key] = value
        self.db.execute(
            "UPDATE agent_registry SET config = ? WHERE id = ?",
            (json.dumps(config), self.agent_id),
        )

    def call_llm(self, prompt: str, model: str = "sonnet", task_type: str = "general", **kwargs) -> str:
        return self.api.call(prompt=prompt, model_key=model, task_type=task_type, **kwargs)

    def _increment_error_count(self):
        self.db.execute(
            "UPDATE agent_registry SET error_count = error_count + 1 WHERE id = ?",
            (self.agent_id,),
        )
