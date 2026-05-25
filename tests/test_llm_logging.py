"""Tests for agentkit.llm.SqliteCallLogger."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest


def _record(**over):
    base = {
        "alias": "fast",
        "model": "deepseek/deepseek-v4-flash",
        "input_tokens": 10,
        "output_tokens": 5,
        "cost_usd": 0.001,
        "duration_ms": 12.5,
        "error": None,
    }
    base.update(over)
    return base


def test_logger_creates_table_and_inserts(tmp_path: Path):
    from agentkit.llm import SqliteCallLogger
    db = tmp_path / "calls.sqlite"
    logger = SqliteCallLogger(db)
    logger(_record())
    rows = sqlite3.connect(str(db)).execute(
        "SELECT alias, model, input_tokens, output_tokens, cost_usd, error FROM llm_calls"
    ).fetchall()
    assert rows == [("fast", "deepseek/deepseek-v4-flash", 10, 5, 0.001, None)]


def test_logger_extra_columns(tmp_path: Path):
    from agentkit.llm import SqliteCallLogger
    db = tmp_path / "calls.sqlite"
    logger = SqliteCallLogger(db, extra_columns={"handler": "TEXT", "purpose": "TEXT"})
    logger(_record(handler="sepa", purpose="extract"))
    row = sqlite3.connect(str(db)).execute(
        "SELECT handler, purpose FROM llm_calls"
    ).fetchone()
    assert row == ("sepa", "extract")


def test_logger_is_idempotent_across_instances(tmp_path: Path):
    from agentkit.llm import SqliteCallLogger
    db = tmp_path / "calls.sqlite"
    SqliteCallLogger(db)(_record())
    SqliteCallLogger(db)(_record())  # second instance must not crash on CREATE
    n = sqlite3.connect(str(db)).execute("SELECT COUNT(*) FROM llm_calls").fetchone()[0]
    assert n == 2


def test_logger_rejects_bad_identifier(tmp_path: Path):
    from agentkit.llm import SqliteCallLogger
    with pytest.raises(ValueError):
        SqliteCallLogger(tmp_path / "x.sqlite", table="bad name;DROP")
