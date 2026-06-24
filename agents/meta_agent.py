"""Meta Agent: collects system state, calls Claude Opus for decisions, executes them."""
import json
import re
from typing import Optional

from agents.base_agent import BaseAgent
from agents.model_router import ModelRouter

# Agents that must never be disabled
_PROTECTED_AGENTS = {"token_manager", "model_router", "meta_agent"}


class MetaAgent(BaseAgent):
    name = "meta_agent"

    def __init__(self, db):
        super().__init__(agent_id="meta_agent", db=db)

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def setup(self):
        self.logger.info("Meta Agent ready")

    def tick(self):
        state = self._collect_system_state()
        prompt = self._build_decision_prompt(state)
        model = ModelRouter.route_task("meta_decision")
        raw = self.call_llm(prompt, model=model, task_type="meta_decision",
                            max_tokens=2048, temperature=0.3)
        decisions = self._parse_decisions(raw)
        for decision in decisions:
            self._execute_decision(decision)
        self.emit_event(
            "info",
            f"Meta Agent tick complete: {len(decisions)} decision(s) executed",
            {"decisions": decisions},
        )

    def tick_interval(self) -> float:
        return self.get_config("tick_interval", 300)

    # ── State collection ──────────────────────────────────────────────────────

    def _collect_system_state(self) -> dict:
        """Query the DB and return a structured dict describing the full system state."""
        # All agents
        agent_rows = self.db.fetchall(
            "SELECT id, name, status, error_count, restart_count, last_heartbeat, config "
            "FROM agent_registry ORDER BY name"
        )
        agents = []
        for row in agent_rows:
            agents.append({
                "id": row["id"],
                "name": row["name"],
                "status": row["status"],
                "error_count": row["error_count"],
                "restart_count": row["restart_count"],
                "last_heartbeat": row["last_heartbeat"],
            })

        # Task queue grouped by agent_target and status
        task_rows = self.db.fetchall(
            "SELECT agent_target, status, COUNT(*) as count "
            "FROM task_queue GROUP BY agent_target, status ORDER BY agent_target, status"
        )
        task_queue = {}
        for row in task_rows:
            target = row["agent_target"]
            if target not in task_queue:
                task_queue[target] = {}
            task_queue[target][row["status"]] = row["count"]

        # Strategy summary
        total_row = self.db.fetchone("SELECT COUNT(*) as cnt FROM strategies")
        total = total_row["cnt"] if total_row else 0

        validated_row = self.db.fetchone(
            "SELECT COUNT(*) as cnt FROM strategies WHERE status = 'validated'"
        )
        validated = validated_row["cnt"] if validated_row else 0

        retired_row = self.db.fetchone(
            "SELECT COUNT(*) as cnt FROM strategies WHERE status = 'retired'"
        )
        retired = retired_row["cnt"] if retired_row else 0

        best_pf_row = self.db.fetchone(
            "SELECT MAX(best_profit_factor) as v FROM strategies WHERE status != 'retired'"
        )
        best_wr_row = self.db.fetchone(
            "SELECT MAX(best_win_rate) as v FROM strategies WHERE status != 'retired'"
        )

        top5_rows = self.db.fetchall(
            "SELECT id, family, status, best_win_rate, best_profit_factor, best_max_drawdown, "
            "best_x10_count, best_final_balance "
            "FROM strategies WHERE status != 'retired' "
            "ORDER BY best_profit_factor DESC NULLS LAST LIMIT 5"
        )
        top5 = [dict(r) for r in top5_rows]

        strategies = {
            "total": total,
            "validated": validated,
            "retired": retired,
            "best_profit_factor": best_pf_row["v"] if best_pf_row else None,
            "best_win_rate": best_wr_row["v"] if best_wr_row else None,
            "top5": top5,
        }

        # Token usage — last hour and all-time
        hour_rows = self.db.fetchall(
            "SELECT agent_id, model, SUM(tokens_in) as tin, SUM(tokens_out) as tout, "
            "SUM(cost_usd) as cost, COUNT(*) as calls "
            "FROM token_usage "
            "WHERE timestamp >= datetime('now', '-1 hour') "
            "GROUP BY agent_id, model"
        )
        all_rows = self.db.fetchall(
            "SELECT agent_id, model, SUM(tokens_in) as tin, SUM(tokens_out) as tout, "
            "SUM(cost_usd) as cost, COUNT(*) as calls "
            "FROM token_usage GROUP BY agent_id, model"
        )

        def _summarise_token_rows(rows):
            result = {"total_cost": 0.0, "total_calls": 0, "by_agent": {}}
            for row in rows:
                result["total_cost"] += row["cost"] or 0.0
                result["total_calls"] += row["calls"] or 0
                aid = row["agent_id"]
                if aid not in result["by_agent"]:
                    result["by_agent"][aid] = {"cost": 0.0, "calls": 0}
                result["by_agent"][aid]["cost"] += row["cost"] or 0.0
                result["by_agent"][aid]["calls"] += row["calls"] or 0
            return result

        token_usage = {
            "last_hour": _summarise_token_rows(hour_rows),
            "all_time": _summarise_token_rows(all_rows),
        }

        # Last 50 events
        event_rows = self.db.fetchall(
            "SELECT agent_id, event_type, event_message, timestamp "
            "FROM events ORDER BY timestamp DESC LIMIT 50"
        )
        recent_events = [
            {
                "agent_id": r["agent_id"],
                "event_type": r["event_type"],
                "message": r["event_message"],
                "timestamp": r["timestamp"],
            }
            for r in event_rows
        ]

        return {
            "agents": agents,
            "task_queue": task_queue,
            "strategies": strategies,
            "token_usage": token_usage,
            "recent_events": recent_events,
        }

    # ── Prompt building ───────────────────────────────────────────────────────

    def _build_decision_prompt(self, state: dict) -> str:
        """Format the system state into a structured prompt for Claude Opus."""
        agents = state["agents"]
        task_queue = state["task_queue"]
        strategies = state["strategies"]
        token_usage = state["token_usage"]
        recent_events = state["recent_events"]

        # Format agents table
        agent_lines = []
        for a in agents:
            agent_lines.append(
                f"  - {a['id']}: status={a['status']}, errors={a['error_count']}, "
                f"restarts={a['restart_count']}, heartbeat={a['last_heartbeat']}"
            )
        agents_text = "\n".join(agent_lines) if agent_lines else "  (none)"

        # Format task queue
        tq_lines = []
        for target, statuses in task_queue.items():
            parts = ", ".join(f"{s}={c}" for s, c in statuses.items())
            tq_lines.append(f"  - {target}: {parts}")
        tq_text = "\n".join(tq_lines) if tq_lines else "  (empty)"

        # Format strategy summary
        strat = strategies
        top5_lines = []
        for s in strat.get("top5", []):
            top5_lines.append(
                f"    * {s['id']} ({s.get('family','?')}): status={s['status']}, "
                f"pf={s.get('best_profit_factor')}, wr={s.get('best_win_rate')}, "
                f"dd={s.get('best_max_drawdown')}, x10={s.get('best_x10_count')}"
            )
        top5_text = "\n".join(top5_lines) if top5_lines else "    (none)"

        # Format token usage
        lh = token_usage.get("last_hour", {})
        at = token_usage.get("all_time", {})
        token_text = (
            f"  Last hour: ${lh.get('total_cost', 0):.4f} across {lh.get('total_calls', 0)} calls\n"
            f"  All-time:  ${at.get('total_cost', 0):.4f} across {at.get('total_calls', 0)} calls"
        )

        # Format recent events (last 10 for brevity)
        event_lines = []
        for e in recent_events[:10]:
            event_lines.append(
                f"  [{e.get('timestamp','')}] {e['agent_id']} ({e['event_type']}): {e['message']}"
            )
        events_text = "\n".join(event_lines) if event_lines else "  (none)"

        prompt = f"""You are the Meta Agent for the XAUUSD-SCALPER-X10 multi-agent trading system.
Your role is to monitor system health and make strategic decisions to optimise performance.

## Current System State

### Agents
{agents_text}

### Task Queue (by agent target)
{tq_text}

### Strategy Summary
  Total strategies: {strat.get('total', 0)}
  Validated: {strat.get('validated', 0)}
  Retired: {strat.get('retired', 0)}
  Best profit factor: {strat.get('best_profit_factor')}
  Best win rate: {strat.get('best_win_rate')}

  Top 5 strategies by profit factor:
{top5_text}

### Token Usage
{token_text}

### Recent Events (last 10)
{events_text}

## Available Actions

You may respond with one or more of the following actions:

1. **reconfigure** — Update an agent's config parameters:
   {{"action": "reconfigure", "agent_id": "<id>", "config": {{<key>: <value>, ...}}, "reason": "..."}}

2. **disable** — Disable a malfunctioning agent (NOT allowed for: token_manager, model_router, meta_agent):
   {{"action": "disable", "agent_id": "<id>", "reason": "..."}}

3. **enable** — Re-enable a stopped or disabled agent:
   {{"action": "enable", "agent_id": "<id>", "reason": "..."}}

4. **no_changes** — Take no action (preferred when system is healthy):
   {{"action": "no_changes", "reason": "..."}}

## Decision Rules
- NEVER disable token_manager, model_router, or meta_agent (they are critical infrastructure).
- Prefer reconfigure over disable whenever possible.
- If an agent has high error_count (>5), consider reconfiguring its tick_interval or disabling it.
- If an agent is stopped and should be running, enable it.
- Keep token costs in mind — avoid unnecessary API calls.
- If the system is healthy, respond with no_changes.

## Response Format

Respond with a JSON object (no markdown fences, no extra text):
- Single action: {{"action": "...", ...}}
- Multiple actions: {{"actions": [{{"action": "...", ...}}, ...]}}

Analyse the state above and decide what actions, if any, to take.
"""
        return prompt

    # ── Decision parsing ──────────────────────────────────────────────────────

    @staticmethod
    def _parse_decisions(raw_response: str) -> list:
        """
        Parse JSON from LLM response. Handles:
          - Single {"action": ...}
          - {"actions": [...]}
          - A plain list [...]
          - Markdown code fences
        Returns [] on any parse error.
        """
        try:
            # Strip markdown code fences
            text = raw_response.strip()
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
            text = text.strip()

            parsed = json.loads(text)

            if isinstance(parsed, list):
                return parsed
            if isinstance(parsed, dict):
                if "actions" in parsed:
                    actions = parsed["actions"]
                    if isinstance(actions, list):
                        return actions
                # Single action dict
                if "action" in parsed:
                    return [parsed]
            return []
        except Exception:
            return []

    # ── Decision execution ────────────────────────────────────────────────────

    def _execute_decision(self, decision: dict):
        """Execute a single parsed decision dict."""
        action = decision.get("action", "").lower()
        agent_id = decision.get("agent_id", "")
        reason = decision.get("reason", "")

        if action == "no_changes":
            return

        elif action == "reconfigure":
            new_config = decision.get("config", {})
            if not agent_id or not isinstance(new_config, dict):
                self.logger.warning(f"reconfigure decision missing agent_id or config: {decision}")
                return
            row = self.db.fetchone(
                "SELECT config FROM agent_registry WHERE id = ?", (agent_id,)
            )
            if row is None:
                self.logger.warning(f"reconfigure: agent not found: {agent_id}")
                return
            existing = {}
            if row["config"]:
                try:
                    existing = json.loads(row["config"]) if isinstance(row["config"], str) else dict(row["config"])
                except Exception:
                    existing = {}
            existing.update(new_config)
            self.db.execute(
                "UPDATE agent_registry SET config = ? WHERE id = ?",
                (json.dumps(existing), agent_id),
            )
            self.logger.info(f"Reconfigured {agent_id}: {new_config}. Reason: {reason}")

        elif action == "disable":
            if agent_id in _PROTECTED_AGENTS:
                self.logger.warning(f"Refusing to disable protected agent: {agent_id}")
                return
            if not agent_id:
                self.logger.warning(f"disable decision missing agent_id: {decision}")
                return
            self.db.execute(
                "UPDATE agent_registry SET status = 'disabled' WHERE id = ?",
                (agent_id,),
            )
            self.logger.info(f"Disabled agent {agent_id}. Reason: {reason}")

        elif action == "enable":
            if not agent_id:
                self.logger.warning(f"enable decision missing agent_id: {decision}")
                return
            self.db.execute(
                "UPDATE agent_registry SET status = 'stopped', error_count = 0 WHERE id = ?",
                (agent_id,),
            )
            self.logger.info(f"Enabled agent {agent_id}. Reason: {reason}")

        else:
            self.logger.warning(f"Unknown action in decision: {action}")
