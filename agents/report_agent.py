"""Report Agent: generates HTML reports with equity curves, heatmaps, and performance breakdowns."""
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from agents.base_agent import BaseAgent
from core.config import LOG_DIR, DATA_DIR


REPORT_DIR = LOG_DIR / "reports"
REPORT_DIR.mkdir(parents=True, exist_ok=True)


class ReportAgent(BaseAgent):
    """Generates periodic HTML performance reports for validated strategies."""

    name = "report_agent"

    def __init__(self, db):
        super().__init__(agent_id="report_agent", db=db)
        self._last_report_date: Optional[str] = None

    # ──────────────────────────────────────────────────
    # BaseAgent interface
    # ──────────────────────────────────────────────────

    def setup(self):
        self._last_report_date = self.get_config("last_report_date")
        self.logger.info("Report Agent ready")

    def tick(self):
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if self._last_report_date == today:
            return  # already generated today's report

        report_path = self._generate_report()
        if report_path:
            self._last_report_date = today
            self.set_config("last_report_date", today)
            self.emit_event(
                "milestone",
                f"Daily report generated: {report_path.name}",
                metadata={"report_path": str(report_path)},
            )

    def tick_interval(self) -> float:
        return self.get_config("tick_interval", 3600)

    # ──────────────────────────────────────────────────
    # Report generation
    # ──────────────────────────────────────────────────

    def _generate_report(self) -> Optional[Path]:
        """Generate a comprehensive HTML report."""
        now = datetime.now(timezone.utc)
        report_name = f"report_{now.strftime('%Y%m%d_%H%M')}.html"
        report_path = REPORT_DIR / report_name

        # Gather data
        system_stats = self._get_system_stats()
        top_strategies = self._get_top_strategies()
        recent_events = self._get_recent_events()
        backtest_summary = self._get_backtest_summary()
        risk_status = self._get_risk_status()

        html = self._render_html(
            now, system_stats, top_strategies, recent_events,
            backtest_summary, risk_status,
        )

        report_path.write_text(html, encoding="utf-8")
        self.logger.info(f"Report saved: {report_path}")
        return report_path

    def _get_system_stats(self) -> dict:
        total = self.db.fetchone("SELECT COUNT(*) as c FROM strategies")["c"]
        validated = self.db.fetchone(
            "SELECT COUNT(*) as c FROM strategies WHERE status = 'validated'"
        )["c"]
        rejected = self.db.fetchone(
            "SELECT COUNT(*) as c FROM strategies WHERE status = 'rejected'"
        )["c"]
        candidate = self.db.fetchone(
            "SELECT COUNT(*) as c FROM strategies WHERE status = 'candidate'"
        )["c"]
        fragile = self.db.fetchone(
            "SELECT COUNT(*) as c FROM strategies WHERE status = 'fragile'"
        )["c"]
        bt_count = self.db.fetchone("SELECT COUNT(*) as c FROM backtest_results")["c"]

        agents = self.db.fetchall(
            "SELECT name, status, error_count FROM agent_registry"
        )

        return {
            "total_strategies": total,
            "validated": validated,
            "rejected": rejected,
            "candidate": candidate,
            "fragile": fragile,
            "backtest_runs": bt_count,
            "agents": [dict(a) for a in agents],
        }

    def _get_top_strategies(self, limit: int = 20) -> list:
        rows = self.db.fetchall(
            "SELECT id, family, best_win_rate, best_profit_factor, "
            "best_max_drawdown, best_x10_count, best_final_balance, "
            "regimes_passed, walk_forward_passed, status, best_config "
            "FROM strategies "
            "WHERE best_profit_factor > 0 "
            "ORDER BY best_profit_factor DESC "
            f"LIMIT {limit}"
        )
        return [dict(r) for r in rows]

    def _get_recent_events(self, limit: int = 50) -> list:
        rows = self.db.fetchall(
            "SELECT agent_id, event_type, event_message, timestamp "
            "FROM events "
            "ORDER BY id DESC "
            f"LIMIT {limit}"
        )
        return [dict(r) for r in rows]

    def _get_backtest_summary(self) -> dict:
        """Aggregate backtest statistics."""
        row = self.db.fetchone(
            "SELECT "
            "AVG(win_rate) as avg_wr, "
            "AVG(profit_factor) as avg_pf, "
            "MAX(profit_factor) as max_pf, "
            "AVG(max_drawdown) as avg_dd, "
            "SUM(total_trades) as total_trades, "
            "COUNT(*) as run_count "
            "FROM backtest_results WHERE walk_forward = 0"
        )
        return dict(row) if row else {}

    def _get_risk_status(self) -> dict:
        row = self.db.fetchone(
            "SELECT config FROM agent_registry WHERE id = ?", ("risk_manager",)
        )
        if not row or not row["config"]:
            return {}
        config = json.loads(row["config"]) if isinstance(row["config"], str) else row["config"]
        return config.get("risk_state", {})

    # ──────────────────────────────────────────────────
    # HTML rendering
    # ──────────────────────────────────────────────────

    def _render_html(
        self, timestamp, system_stats, top_strategies,
        recent_events, backtest_summary, risk_status,
    ) -> str:
        # Build strategy rows
        strat_rows = ""
        for s in top_strategies:
            config = {}
            if s.get("best_config"):
                try:
                    config = json.loads(s["best_config"]) if isinstance(s["best_config"], str) else s["best_config"]
                except (json.JSONDecodeError, TypeError):
                    pass

            mc_info = config.get("monte_carlo", {})
            sens_info = config.get("sensitivity", {})

            strat_rows += f"""
            <tr>
                <td><strong>{s['id']}</strong></td>
                <td>{s.get('family', '-')}</td>
                <td>{s.get('status', '-')}</td>
                <td>{s.get('best_win_rate', 0):.1%}</td>
                <td>{s.get('best_profit_factor', 0):.2f}</td>
                <td>{s.get('best_max_drawdown', 0):.1%}</td>
                <td>{s.get('best_x10_count', 0)}</td>
                <td>{s.get('regimes_passed', 0)}/3</td>
                <td>{'Yes' if s.get('walk_forward_passed') else 'No'}</td>
                <td>{mc_info.get('p_ruin', '-')}</td>
                <td>{sens_info.get('robustness_score', '-')}</td>
            </tr>"""

        # Build event rows
        event_rows = ""
        for e in recent_events[:30]:
            event_class = ""
            if e.get("event_type") == "milestone":
                event_class = "milestone"
            elif e.get("event_type") in ("error", "warning"):
                event_class = "warning"

            event_rows += f"""
            <tr class="{event_class}">
                <td>{e.get('timestamp', '')[:19]}</td>
                <td>{e.get('agent_id', '')}</td>
                <td>{e.get('event_type', '')}</td>
                <td>{e.get('event_message', '')[:100]}</td>
            </tr>"""

        # Build agent status rows
        agent_rows = ""
        for a in system_stats.get("agents", []):
            status_class = "running" if a.get("status") == "running" else "stopped"
            agent_rows += f"""
            <tr class="{status_class}">
                <td>{a.get('name', '')}</td>
                <td>{a.get('status', '')}</td>
                <td>{a.get('error_count', 0)}</td>
            </tr>"""

        bs = backtest_summary
        rs = risk_status

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>XAUUSD-SCALPER-X10 Report — {timestamp.strftime('%Y-%m-%d %H:%M UTC')}</title>
<style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{ font-family: 'Segoe UI', system-ui, sans-serif; background: #0a0a0f; color: #e0e0e0; padding: 20px; }}
    h1 {{ color: #ffd700; margin-bottom: 5px; }}
    h2 {{ color: #c0c0c0; margin: 25px 0 10px; border-bottom: 1px solid #333; padding-bottom: 5px; }}
    .subtitle {{ color: #888; margin-bottom: 20px; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin: 15px 0; }}
    .card {{ background: #1a1a2e; border: 1px solid #333; border-radius: 8px; padding: 15px; text-align: center; }}
    .card .value {{ font-size: 2em; font-weight: bold; color: #ffd700; }}
    .card .label {{ color: #888; font-size: 0.85em; margin-top: 5px; }}
    table {{ width: 100%; border-collapse: collapse; margin: 10px 0; }}
    th {{ background: #1a1a2e; color: #ffd700; padding: 8px; text-align: left; font-size: 0.85em; }}
    td {{ padding: 8px; border-bottom: 1px solid #222; font-size: 0.85em; }}
    tr:hover {{ background: #1a1a2e; }}
    tr.milestone {{ background: #1a2e1a; }}
    tr.warning {{ background: #2e1a1a; }}
    tr.running td:nth-child(2) {{ color: #4caf50; }}
    tr.stopped td:nth-child(2) {{ color: #f44336; }}
    .risk-ok {{ color: #4caf50; }}
    .risk-warn {{ color: #ff9800; }}
    .risk-danger {{ color: #f44336; }}
    footer {{ margin-top: 30px; color: #555; font-size: 0.8em; text-align: center; }}
</style>
</head>
<body>
<h1>XAUUSD-SCALPER-X10</h1>
<p class="subtitle">Autonomous Multi-Agent System Report — {timestamp.strftime('%Y-%m-%d %H:%M UTC')}</p>

<h2>System Overview</h2>
<div class="grid">
    <div class="card"><div class="value">{system_stats['total_strategies']}</div><div class="label">Total Strategies</div></div>
    <div class="card"><div class="value">{system_stats['validated']}</div><div class="label">Validated</div></div>
    <div class="card"><div class="value">{system_stats['rejected']}</div><div class="label">Rejected</div></div>
    <div class="card"><div class="value">{system_stats['candidate']}</div><div class="label">Candidates</div></div>
    <div class="card"><div class="value">{system_stats['fragile']}</div><div class="label">Fragile</div></div>
    <div class="card"><div class="value">{system_stats['backtest_runs']}</div><div class="label">Backtest Runs</div></div>
</div>

<h2>Backtest Aggregate</h2>
<div class="grid">
    <div class="card"><div class="value">{bs.get('avg_wr', 0):.1%}</div><div class="label">Avg Win Rate</div></div>
    <div class="card"><div class="value">{bs.get('avg_pf', 0):.2f}</div><div class="label">Avg Profit Factor</div></div>
    <div class="card"><div class="value">{bs.get('max_pf', 0):.2f}</div><div class="label">Best Profit Factor</div></div>
    <div class="card"><div class="value">{bs.get('avg_dd', 0):.1%}</div><div class="label">Avg Max Drawdown</div></div>
    <div class="card"><div class="value">{bs.get('total_trades', 0):,.0f}</div><div class="label">Total Trades</div></div>
    <div class="card"><div class="value">{bs.get('run_count', 0)}</div><div class="label">Backtest Runs</div></div>
</div>

<h2>Risk Status</h2>
<div class="grid">
    <div class="card">
        <div class="value {'risk-danger' if rs.get('circuit_breaker_active') else 'risk-ok'}">
            {'ACTIVE' if rs.get('circuit_breaker_active') else 'OFF'}
        </div>
        <div class="label">Circuit Breaker</div>
    </div>
    <div class="card"><div class="value">{rs.get('daily_pnl', 0):.2%}</div><div class="label">Daily P&L</div></div>
    <div class="card"><div class="value">{rs.get('weekly_pnl', 0):.2%}</div><div class="label">Weekly P&L</div></div>
    <div class="card"><div class="value">{rs.get('consecutive_losses', 0)}</div><div class="label">Loss Streak</div></div>
    <div class="card"><div class="value">{rs.get('current_scaling', 1.0):.0%}</div><div class="label">Position Scaling</div></div>
</div>

<h2>Agent Status</h2>
<table>
<tr><th>Agent</th><th>Status</th><th>Errors</th></tr>
{agent_rows}
</table>

<h2>Top Strategies</h2>
<table>
<tr>
    <th>ID</th><th>Family</th><th>Status</th><th>WR</th><th>PF</th>
    <th>Max DD</th><th>x10</th><th>Regimes</th><th>WF</th>
    <th>MC p_ruin</th><th>Robustness</th>
</tr>
{strat_rows}
</table>

<h2>Recent Events</h2>
<table>
<tr><th>Time</th><th>Agent</th><th>Type</th><th>Message</th></tr>
{event_rows}
</table>

<footer>
    Generated by XAUUSD-SCALPER-X10 Report Agent | {timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}
</footer>
</body>
</html>"""
