"""Knowledge Base Agent: auto-populates the Obsidian vault with strategy cards,
backtest summaries, daily journals, decision logs, and system insights.

Watches the database for new events and translates them into markdown notes
that form the system's long-term memory."""
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from agents.base_agent import BaseAgent
from core.config import BASE_DIR


KB_DIR = BASE_DIR / "knowledge_base"
STRATEGIES_DIR = KB_DIR / "strategies"
BACKTESTS_DIR = KB_DIR / "backtests"
INSIGHTS_DIR = KB_DIR / "insights"
DECISIONS_DIR = KB_DIR / "decisions"
DAILY_DIR = KB_DIR / "daily"

for _d in [STRATEGIES_DIR, BACKTESTS_DIR, INSIGHTS_DIR, DECISIONS_DIR, DAILY_DIR]:
    _d.mkdir(parents=True, exist_ok=True)


class KnowledgeBaseAgent(BaseAgent):
    """Writes Obsidian-compatible markdown notes from system events."""

    name = "knowledge_base_agent"

    def __init__(self, db):
        super().__init__(agent_id="knowledge_base_agent", db=db)
        self._last_event_id: int = 0
        self._last_backtest_id: int = 0
        self._known_strategies: set = set()

    # ── lifecycle ────────────────────────────────────────────────────────

    def setup(self):
        self._load_watermarks()
        self.logger.info("Knowledge Base Agent ready — Obsidian vault writer")

    def tick_interval(self) -> float:
        return 120.0  # every 2 minutes

    def tick(self):
        self._sync_strategies()
        self._sync_backtests()
        self._sync_decisions()
        self._write_daily_journal()
        self._sync_insights()

    # ── watermarks (avoid reprocessing) ──────────────────────────────────

    def _load_watermarks(self):
        """Load last-processed IDs to avoid duplicate writes."""
        wm_path = KB_DIR / ".watermarks.json"
        if wm_path.exists():
            try:
                wm = json.loads(wm_path.read_text(encoding="utf-8"))
                self._last_event_id = wm.get("last_event_id", 0)
                self._last_backtest_id = wm.get("last_backtest_id", 0)
            except Exception:
                pass

    def _save_watermarks(self):
        wm_path = KB_DIR / ".watermarks.json"
        wm_path.write_text(json.dumps({
            "last_event_id": self._last_event_id,
            "last_backtest_id": self._last_backtest_id,
        }), encoding="utf-8")

    # ── 1. Strategy cards ────────────────────────────────────────────────

    def _sync_strategies(self):
        """Write/update a markdown card for each strategy."""
        rows = self.db.fetchall(
            "SELECT id, file_path, family, status, best_win_rate, best_profit_factor, "
            "best_max_drawdown, best_x10_count, best_final_balance, best_config, "
            "generation, created_by, created_at "
            "FROM strategies ORDER BY created_at"
        )
        if not rows:
            return

        new_count = 0
        for row in rows:
            row = dict(row)
            sid = row["id"]
            if sid in self._known_strategies:
                continue

            note_path = STRATEGIES_DIR / f"{sid}.md"
            status = row.get("status", "candidate")
            wr = row.get("best_win_rate")
            pf = row.get("best_profit_factor")
            dd = row.get("best_max_drawdown")
            x10 = row.get("best_x10_count")
            bal = row.get("best_final_balance")
            config = self._parse_json(row.get("best_config"))

            # Determine timeframe from ID prefix
            sid_lower = sid.lower()
            if sid_lower.startswith(("c", "d")):
                tf = "M5"
            elif sid_lower.startswith("e"):
                tf = "M5"
            else:
                tf = "M1"

            lines = [
                f"# {sid}",
                f"",
                f"**Status** : {status}",
                f"**Family** : {row.get('family', 'unknown')}",
                f"**Timeframe** : {tf}",
                f"**Generation** : {row.get('generation', 0)}",
                f"**Created by** : {row.get('created_by', 'unknown')}",
                f"**Created** : {row.get('created_at', 'unknown')}",
                f"",
                f"## Best Results",
                f"| Metric | Value |",
                f"|--------|-------|",
                f"| Win Rate | {wr:.1%} |" if wr else "| Win Rate | — |",
                f"| Profit Factor | {pf:.2f} |" if pf else "| Profit Factor | — |",
                f"| Max Drawdown | {dd:.1%} |" if dd else "| Max Drawdown | — |",
                f"| x10 Count | {x10} |" if x10 is not None else "| x10 Count | — |",
                f"| Final Balance | ${bal:.2f} |" if bal else "| Final Balance | — |",
                f"",
            ]

            if config:
                lines.append("## Parameters")
                lines.append("```json")
                lines.append(json.dumps(config, indent=2))
                lines.append("```")
                lines.append("")

            lines.append("## Links")
            lines.append(f"- [[{sid} Backtest]]")
            lines.append("")

            note_path.write_text("\n".join(lines), encoding="utf-8")
            self._known_strategies.add(sid)
            new_count += 1

        if new_count:
            self.logger.info(f"Wrote {new_count} strategy cards to Obsidian")

    # ── 2. Backtest summaries ────────────────────────────────────────────

    def _sync_backtests(self):
        """Write markdown summaries for new backtest results."""
        rows = self.db.fetchall(
            "SELECT id, strategy_id, win_rate, profit_factor, max_drawdown, "
            "x10_count, final_balance, total_trades, config, walk_forward, run_at "
            "FROM backtest_results WHERE id > ? ORDER BY id",
            (self._last_backtest_id,)
        )
        if not rows:
            return

        for row in rows:
            row = dict(row)
            bt_id = row["id"]
            sid = row["strategy_id"]
            config = self._parse_json(row.get("config"))

            sl = config.get("sl_atr", "?") if config else "?"
            tp = config.get("tp_atr", "?") if config else "?"
            risk = config.get("risk_pct", "?") if config else "?"

            note_path = BACKTESTS_DIR / f"{sid}_bt{bt_id}.md"
            wr = row.get("win_rate")
            pf = row.get("profit_factor")
            dd = row.get("max_drawdown")

            lines = [
                f"# {sid} — Backtest #{bt_id}",
                f"",
                f"**Date** : {row.get('run_at', 'unknown')}",
                f"**Walk-Forward** : {'Yes' if row.get('walk_forward') else 'No'}",
                f"",
                f"## Config",
                f"- SL ATR: {sl}",
                f"- TP ATR: {tp}",
                f"- Risk: {risk}",
                f"",
                f"## Results",
                f"| Metric | Value |",
                f"|--------|-------|",
                f"| Win Rate | {wr:.1%} |" if wr else "| Win Rate | — |",
                f"| Profit Factor | {pf:.2f} |" if pf else "| Profit Factor | — |",
                f"| Max Drawdown | {dd:.1%} |" if dd else "| Max Drawdown | — |",
                f"| Trades | {row.get('total_trades', 0)} |",
                f"| Final Balance | ${row.get('final_balance', 0):.2f} |",
                f"| x10 Count | {row.get('x10_count', 0)} |",
                f"",
                f"## Links",
                f"- [[{sid}]]",
                f"",
            ]

            note_path.write_text("\n".join(lines), encoding="utf-8")
            self._last_backtest_id = max(self._last_backtest_id, bt_id)

        self._save_watermarks()
        self.logger.info(f"Wrote {len(rows)} backtest notes to Obsidian")

    # ── 3. Decision logs (from meta_agent events) ────────────────────────

    def _sync_decisions(self):
        """Pull meta_agent decision events and write decision notes."""
        rows = self.db.fetchall(
            "SELECT id, agent_id, event_type, event_message, metadata, timestamp "
            "FROM events WHERE id > ? AND agent_id = 'meta_agent' "
            "AND event_type IN ('decision', 'analysis', 'action') "
            "ORDER BY id",
            (self._last_event_id,)
        )
        if not rows:
            # Still update watermark from non-meta events
            latest = self.db.fetchone(
                "SELECT MAX(id) as max_id FROM events"
            )
            if latest and latest["max_id"]:
                self._last_event_id = max(self._last_event_id, latest["max_id"])
                self._save_watermarks()
            return

        for row in rows:
            row = dict(row)
            ev_id = row["id"]
            ts = row.get("timestamp", "unknown")

            note_path = DECISIONS_DIR / f"decision_{ev_id}.md"
            meta = self._parse_json(row.get("metadata"))

            lines = [
                f"# Decision #{ev_id}",
                f"",
                f"**Date** : {ts}",
                f"**Type** : {row.get('event_type', 'unknown')}",
                f"",
                f"## Details",
                f"{row.get('event_message', '')}",
                f"",
            ]

            if meta:
                lines.append("## Metadata")
                lines.append("```json")
                lines.append(json.dumps(meta, indent=2, default=str))
                lines.append("```")
                lines.append("")

            note_path.write_text("\n".join(lines), encoding="utf-8")
            self._last_event_id = max(self._last_event_id, ev_id)

        self._save_watermarks()
        self.logger.info(f"Wrote {len(rows)} decision notes to Obsidian")

    # ── 4. Daily journal ─────────────────────────────────────────────────

    def _write_daily_journal(self):
        """Write/update today's daily journal with system stats."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        note_path = DAILY_DIR / f"{today}.md"

        # Gather stats
        total_strats = self.db.fetchone("SELECT COUNT(*) as c FROM strategies")
        total_strats = total_strats["c"] if total_strats else 0

        validated = self.db.fetchone(
            "SELECT COUNT(*) as c FROM strategies WHERE status = 'validated'"
        )
        validated = validated["c"] if validated else 0

        total_bt = self.db.fetchone("SELECT COUNT(*) as c FROM backtest_results")
        total_bt = total_bt["c"] if total_bt else 0

        today_bt = self.db.fetchone(
            "SELECT COUNT(*) as c FROM backtest_results WHERE date(run_at) = ?",
            (today,)
        )
        today_bt = today_bt["c"] if today_bt else 0

        # Best strategy today
        best_today = self.db.fetchone(
            "SELECT strategy_id, profit_factor, win_rate, final_balance "
            "FROM backtest_results WHERE date(run_at) = ? "
            "ORDER BY profit_factor DESC LIMIT 1",
            (today,)
        )

        # Recent events count
        events_today = self.db.fetchone(
            "SELECT COUNT(*) as c FROM events WHERE date(timestamp) = ?",
            (today,)
        )
        events_today = events_today["c"] if events_today else 0

        # Active agents
        active_agents = self.db.fetchone(
            "SELECT COUNT(*) as c FROM agent_registry WHERE status = 'running'"
        )
        active_agents = active_agents["c"] if active_agents else 0

        lines = [
            f"# Journal — {today}",
            f"",
            f"## System Stats",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Total Strategies | {total_strats} |",
            f"| Validated | {validated} |",
            f"| Total Backtests | {total_bt} |",
            f"| Backtests Today | {today_bt} |",
            f"| Events Today | {events_today} |",
            f"| Active Agents | {active_agents} |",
            f"",
        ]

        if best_today:
            bt = dict(best_today)
            lines.extend([
                f"## Best Result Today",
                f"- **Strategy** : [[{bt['strategy_id']}]]",
                f"- **PF** : {bt.get('profit_factor', 0):.2f}",
                f"- **WR** : {bt.get('win_rate', 0):.1%}",
                f"- **Balance** : ${bt.get('final_balance', 0):.2f}",
                f"",
            ])

        # Milestones
        if validated > 0:
            val_rows = self.db.fetchall(
                "SELECT id, best_profit_factor, best_final_balance "
                "FROM strategies WHERE status = 'validated' ORDER BY best_profit_factor DESC"
            )
            if val_rows:
                lines.append("## Validated Strategies")
                for v in val_rows:
                    v = dict(v)
                    lines.append(
                        f"- [[{v['id']}]] — PF {v.get('best_profit_factor', 0):.2f}, "
                        f"${v.get('best_final_balance', 0):.2f}"
                    )
                lines.append("")

        lines.extend([
            f"## Notes",
            f"_Auto-generated by knowledge_base_agent_",
            f"",
        ])

        note_path.write_text("\n".join(lines), encoding="utf-8")

    # ── 5. Sync strategy_analyzer insights ───────────────────────────────

    def _sync_insights(self):
        """Pull insights from strategy_analyzer's JSON and write Obsidian notes."""
        insights_json = BASE_DIR / "logs" / "strategy_insights.json"
        if not insights_json.exists():
            return

        try:
            data = json.loads(insights_json.read_text(encoding="utf-8"))
        except Exception:
            return

        insights = data.get("insights", [])
        if not insights:
            return

        # Write a single consolidated insights note (updated each tick)
        note_path = INSIGHTS_DIR / "System Insights (Auto).md"
        updated = data.get("updated_at", "unknown")

        lines = [
            f"# System Insights (Auto-Generated)",
            f"",
            f"**Last Updated** : {updated}",
            f"**Strategies Analyzed** : {data.get('total_strategies_analyzed', 0)}",
            f"**Total Backtests** : {data.get('total_backtests', 0)}",
            f"",
            f"## Key Insights",
        ]

        for i, insight in enumerate(insights, 1):
            lines.append(f"{i}. {insight}")

        lines.append("")

        # Family performance table
        family_perf = data.get("family_performance", {})
        if family_perf:
            lines.extend([
                "## Family Performance",
                "| Family | Count | Avg PF | Avg WR | Max PF | % Profitable |",
                "|--------|-------|--------|--------|--------|-------------|",
            ])
            for fam, stats in sorted(
                family_perf.items(),
                key=lambda x: x[1].get("avg_pf", 0),
                reverse=True
            ):
                lines.append(
                    f"| {fam} | {stats.get('count', 0)} | "
                    f"{stats.get('avg_pf', 0):.2f} | "
                    f"{stats.get('avg_wr', 0):.1%} | "
                    f"{stats.get('max_pf', 0):.2f} | "
                    f"{stats.get('pf_above_1_pct', 0):.0f}% |"
                )
            lines.append("")

        # SL/TP ranges
        sl_tp = data.get("best_sl_tp_ranges", {})
        if sl_tp.get("sample_size", 0) > 0:
            lines.extend([
                "## Optimal Parameter Ranges",
                f"- **Min viable SL** : {sl_tp.get('min_viable_sl', '?')}",
                f"- **Optimal SL range** : {sl_tp.get('optimal_sl_range', '?')}",
                f"- **Optimal TP range** : {sl_tp.get('optimal_tp_range', '?')}",
                f"- **Best SL bucket** : {sl_tp.get('best_sl_bucket', '?')}",
                f"- **Best TP bucket** : {sl_tp.get('best_tp_bucket', '?')}",
                f"- **Sample size** : {sl_tp.get('sample_size', 0)}",
                "",
            ])

        # Failure modes
        fm = data.get("failure_modes", {})
        if fm:
            lines.extend([
                "## Failure Modes",
                "| Mode | Count |",
                "|------|-------|",
            ])
            for mode, count in sorted(fm.items(), key=lambda x: x[1], reverse=True):
                lines.append(f"| {mode} | {count} |")
            lines.append("")

        lines.extend([
            "## Links",
            "- [[M5 Breakthrough]]",
            "- [[Philosophie — Amelioration Continue]]",
            "",
        ])

        note_path.write_text("\n".join(lines), encoding="utf-8")

    # ── helpers ──────────────────────────────────────────────────────────

    def _parse_json(self, raw) -> Optional[Dict]:
        if raw is None:
            return None
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, str):
            try:
                return json.loads(raw)
            except (json.JSONDecodeError, ValueError):
                return None
        return None
