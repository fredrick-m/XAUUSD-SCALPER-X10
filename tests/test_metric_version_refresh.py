import json

from core.config import BACKTEST_METRIC_VERSION
from core.db import Database
from scripts.refresh_x10_metric_version import refresh


def test_metric_refresh_archives_requeues_stamps_and_is_idempotent(tmp_path):
    db = Database(tmp_path / "test.sqlite")
    try:
        db.init_schema()
        old_config = {
            "monte_carlo": {"p_ruin": 0.01},
            "sensitivity": {"is_fragile": False},
            "portfolio_selected": True,
        }
        db.execute(
            "INSERT INTO strategies "
            "(id, file_path, status, best_win_rate, best_profit_factor, "
            "best_max_drawdown, best_x10_count, best_final_balance, "
            "walk_forward_passed, best_config) "
            "VALUES (?, ?, 'validated', ?, ?, ?, ?, ?, 1, ?)",
            ("S_TEST", "strategies/s_test.py", 0.70, 2.0, 0.10, 5, 5000.0,
             json.dumps(old_config)),
        )
        db.execute(
            "INSERT INTO backtest_results "
            "(strategy_id, risk_pct, total_trades, win_rate, profit_factor, "
            "max_drawdown, x10_count, final_balance, return_pct, blown_account) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("S_TEST", 0.04, 200, 0.70, 2.0, 0.10, 5, 5000.0, 900.0, 0),
        )

        first = refresh(db)
        assert first["already_applied"] is False
        assert first["archived_results"] == 1
        assert first["requeued"] == 1

        active = db.fetchone("SELECT COUNT(*) AS n FROM backtest_results")
        archived = db.fetchone("SELECT COUNT(*) AS n FROM backtest_results_archive")
        assert active["n"] == 0
        assert archived["n"] == 1

        strategy = db.fetchone(
            "SELECT status, walk_forward_passed, best_profit_factor, best_x10_count, best_config "
            "FROM strategies WHERE id='S_TEST'"
        )
        assert strategy["status"] == "candidate"
        assert strategy["walk_forward_passed"] == 0
        assert strategy["best_profit_factor"] is None
        assert strategy["best_x10_count"] is None

        config = json.loads(strategy["best_config"])
        assert config["metric_version"] == BACKTEST_METRIC_VERSION
        assert config["metric_refresh_pending"] is True
        assert "monte_carlo" not in config
        assert "sensitivity" not in config
        assert "portfolio_selected" not in config

        # Simulate the existing runner inserting a fresh V2 result with
        # config=None. The migration trigger must stamp it automatically.
        db.execute(
            "INSERT INTO backtest_results "
            "(strategy_id, risk_pct, config, total_trades, win_rate, profit_factor, "
            "max_drawdown, x10_count, final_balance, return_pct, blown_account) "
            "VALUES (?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("S_TEST", 0.04, 150, 0.65, 1.5, 0.18, 1, 1200.0, 140.0, 0),
        )
        fresh = db.fetchone(
            "SELECT config FROM backtest_results WHERE strategy_id='S_TEST'"
        )
        assert json.loads(fresh["config"])["metric_version"] == BACKTEST_METRIC_VERSION

        second = refresh(db)
        assert second["already_applied"] is True
        archived_again = db.fetchone("SELECT COUNT(*) AS n FROM backtest_results_archive")
        assert archived_again["n"] == 1
        # Re-running the same migration must not archive the new V2 row.
        active_again = db.fetchone("SELECT COUNT(*) AS n FROM backtest_results")
        assert active_again["n"] == 1
    finally:
        db.close()
