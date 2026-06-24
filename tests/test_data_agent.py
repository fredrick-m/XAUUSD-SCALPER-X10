"""Tests for Data Agent."""
import pytest
from pathlib import Path


@pytest.fixture
def tmp_db(tmp_path):
    from core.db import Database
    db = Database(tmp_path / "test.sqlite")
    db.init_schema()
    db.execute(
        "INSERT INTO agent_registry (id, name, module_path, class_name, config) VALUES (?, ?, ?, ?, ?)",
        ("data_agent", "data_agent", "agents.data_agent", "DataAgent", '{"tick_interval": 0.01}'),
    )
    yield db
    db.close()


def test_data_agent_imports():
    from agents.data_agent import DataAgent
    assert DataAgent.name == "data_agent"


def test_check_existing_data(tmp_db):
    from agents.data_agent import DataAgent
    agent = DataAgent(tmp_db)
    inventory = agent.scan_existing_data()
    assert isinstance(inventory, list)


def test_quality_check_on_sample_data(tmp_path, tmp_db):
    from agents.data_agent import quality_score
    import pandas as pd
    csv_path = tmp_path / "sample.csv"
    rows = []
    for i in range(100):
        rows.append({
            "time": f"2025-01-01 00:{i // 60:02d}:{i % 60:02d}",
            "Open": 2000 + i * 0.1,
            "High": 2000 + i * 0.1 + 0.5,
            "Low": 2000 + i * 0.1 - 0.3,
            "Close": 2000 + i * 0.1 + 0.2,
            "Volume": 100 + i,
        })
    pd.DataFrame(rows).to_csv(csv_path, index=False)
    score = quality_score(csv_path)
    assert score >= 0.8


def test_register_data_in_db(tmp_db):
    from agents.data_agent import DataAgent
    agent = DataAgent(tmp_db)
    agent.register_data(
        data_id="xauusd_m1_mt5",
        timeframe="M1",
        source="MT5",
        file_path="/fake/path.csv",
        start_date="2025-01-01",
        end_date="2025-12-31",
        bar_count=100000,
        quality=0.95,
    )
    row = tmp_db.fetchone("SELECT * FROM data_registry WHERE id = ?", ("xauusd_m1_mt5",))
    assert row["timeframe"] == "M1"
    assert row["bar_count"] == 100000
