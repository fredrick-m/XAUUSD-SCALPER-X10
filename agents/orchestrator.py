"""Orchestrator: main daemon that launches, monitors, and restarts agents."""
import importlib
import json
import signal
import threading
import time
from typing import Dict, Optional

import requests

from core.config import CORE_AGENTS, HEARTBEAT_INTERVAL, HEARTBEAT_TIMEOUT, MAX_AGENT_RESTARTS, INTERNET_CHECK_URL
from core.db import Database
from core.logger import get_logger, log_event


def check_internet(url: str = INTERNET_CHECK_URL, timeout: float = 5) -> bool:
    try:
        requests.head(url, timeout=timeout)
        return True
    except (requests.ConnectionError, requests.Timeout):
        return False


class Orchestrator:
    def __init__(self, db: Database):
        self.db = db
        self.logger = get_logger("orchestrator")
        self._shutdown = False
        self._agent_threads: Dict[str, threading.Thread] = {}
        self._agent_instances: Dict[str, object] = {}

    def register_core_agents(self):
        for agent_def in CORE_AGENTS:
            existing = self.db.fetchone(
                "SELECT id FROM agent_registry WHERE name = ?", (agent_def["name"],)
            )
            if not existing:
                self.db.execute(
                    "INSERT INTO agent_registry (id, name, module_path, class_name, config, can_spawn_children) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        agent_def["name"],
                        agent_def["name"],
                        agent_def["module_path"],
                        agent_def["class_name"],
                        json.dumps(agent_def.get("config", {})),
                        agent_def.get("can_spawn_children", False),
                    ),
                )
                self.logger.info(f"Registered agent: {agent_def['name']}")

    def _load_agent(self, agent_row) -> Optional[object]:
        try:
            module = importlib.import_module(agent_row["module_path"])
            agent_class = getattr(module, agent_row["class_name"])
            return agent_class(self.db)
        except Exception as e:
            self.logger.error(f"Failed to load agent {agent_row['name']}: {e}")
            log_event(self.db, agent_row["id"], "error", f"Load failed: {e}")
            return None

    def _start_agent(self, agent_row):
        agent_id = agent_row["id"]
        if agent_id in self._agent_threads and self._agent_threads[agent_id].is_alive():
            return
        agent = self._load_agent(agent_row)
        if agent is None:
            return
        self._agent_instances[agent_id] = agent
        thread = threading.Thread(target=agent.run, name=f"agent-{agent_id}", daemon=True)
        thread.start()
        self._agent_threads[agent_id] = thread
        self.db.execute("UPDATE agent_registry SET status = 'running' WHERE id = ?", (agent_id,))
        self.logger.info(f"Started agent: {agent_id}")

    def _stop_agent(self, agent_id: str):
        if agent_id in self._agent_instances:
            self._agent_instances[agent_id].request_shutdown()
            thread = self._agent_threads.get(agent_id)
            if thread:
                thread.join(timeout=3)
            try:
                self.db.execute("UPDATE agent_registry SET status = 'stopped' WHERE id = ?", (agent_id,))
            except Exception:
                pass
            self.logger.info(f"Stopped agent: {agent_id}")

    def _check_agents(self):
        agents = self.db.fetchall("SELECT * FROM agent_registry WHERE status IN ('running', 'stopped')")
        for agent_row in agents:
            agent_id = agent_row["id"]
            thread = self._agent_threads.get(agent_id)
            if agent_row["status"] == "running" and (thread is None or not thread.is_alive()):
                restart_count = agent_row["restart_count"] or 0
                if restart_count < MAX_AGENT_RESTARTS:
                    self.logger.warning(f"Agent {agent_id} died, restarting ({restart_count + 1}/{MAX_AGENT_RESTARTS})")
                    self.db.execute("UPDATE agent_registry SET restart_count = restart_count + 1 WHERE id = ?", (agent_id,))
                    self._start_agent(agent_row)
                else:
                    self.logger.error(f"Agent {agent_id} exceeded max restarts, disabling")
                    self.db.execute("UPDATE agent_registry SET status = 'disabled' WHERE id = ?", (agent_id,))
                    log_event(self.db, agent_id, "error", "Agent disabled after max restarts")

    def run(self):
        self.logger.info("=" * 60)
        self.logger.info("XAUUSD-SCALPER-X10 Autonomous Multi-Agent System")
        self.logger.info("=" * 60)
        log_event(self.db, "orchestrator", "milestone", "System starting")
        agents = self.db.fetchall("SELECT * FROM agent_registry WHERE status != 'disabled'")
        for agent_row in agents:
            self._start_agent(agent_row)
        internet_was_down = False
        _internet_pause_elapsed = 0.0
        _heartbeat_elapsed = 0.0
        _tick = 0.5  # poll interval in seconds for responsiveness
        while not self._shutdown:
            time.sleep(_tick)
            if self._shutdown:
                break
            if not check_internet():
                if not internet_was_down:
                    self.logger.warning("Internet connection lost — pausing agents")
                    log_event(self.db, "orchestrator", "warning", "Internet lost")
                    internet_was_down = True
                    _internet_pause_elapsed = 0.0
                _internet_pause_elapsed += _tick
                continue
            elif internet_was_down:
                self.logger.info("Internet restored — resuming")
                log_event(self.db, "orchestrator", "info", "Internet restored")
                internet_was_down = False
                _heartbeat_elapsed = 0.0
            _heartbeat_elapsed += _tick
            if _heartbeat_elapsed >= HEARTBEAT_INTERVAL:
                self._check_agents()
                _heartbeat_elapsed = 0.0
        self.logger.info("Orchestrator shutting down...")
        # Signal all agents to shut down first, then join them
        for agent_id, agent in list(self._agent_instances.items()):
            try:
                agent.request_shutdown()
            except Exception:
                pass
        for agent_id in list(self._agent_instances.keys()):
            thread = self._agent_threads.get(agent_id)
            if thread:
                thread.join(timeout=3)
            try:
                self.db.execute("UPDATE agent_registry SET status = 'stopped' WHERE id = ?", (agent_id,))
            except Exception:
                pass
            self.logger.info(f"Stopped agent: {agent_id}")
        try:
            log_event(self.db, "orchestrator", "milestone", "System stopped")
        except Exception:
            pass
        self.logger.info("All agents stopped. Goodbye.")

    def shutdown(self):
        self._shutdown = True
