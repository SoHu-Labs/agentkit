"""SQLite logger for agentkit.llm.complete() call records (optional, opt-in)."""
from __future__ import annotations

import re
import sqlite3
import time
from pathlib import Path
from typing import Any

# Canonical columns produced by complete()'s log_fn record.
_CANONICAL_COLUMNS: dict[str, str] = {
    "alias": "TEXT",
    "model": "TEXT",
    "input_tokens": "INTEGER",
    "output_tokens": "INTEGER",
    "cost_usd": "REAL",
    "duration_ms": "REAL",
    "error": "TEXT",
}

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _check_ident(name: str) -> str:
    if not _IDENT.match(name):
        raise ValueError(f"Invalid SQL identifier: {name!r}")
    return name


class SqliteCallLogger:
    """Callable that logs a complete() record to a SQLite table.

    Pass an instance as ``log_fn`` to ``agentkit.llm.complete``. The table is
    created on first use with the canonical columns plus any ``extra_columns``
    (a ``{name: sql_type}`` mapping). Extra column values are read from matching
    keys in the record, so callers stuff e.g. ``record["handler"]`` themselves.
    """

    def __init__(
        self,
        db_path: str | Path,
        *,
        table: str = "llm_calls",
        extra_columns: dict[str, str] | None = None,
    ) -> None:
        self._db_path = Path(db_path)
        self._table = _check_ident(table)
        self._extra = {_check_ident(k): v for k, v in (extra_columns or {}).items()}
        self._conn: sqlite3.Connection | None = None

    def _connect(self) -> sqlite3.Connection:
        if self._conn is None:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(self._db_path))
            cols = {**_CANONICAL_COLUMNS, **self._extra}
            col_defs = ", ".join(f"{name} {decl}" for name, decl in cols.items())
            self._conn.execute(
                f"CREATE TABLE IF NOT EXISTS {self._table} "
                f"(id INTEGER PRIMARY KEY AUTOINCREMENT, {col_defs}, "
                f"created_at TEXT NOT NULL)"
            )
            self._conn.commit()
        return self._conn

    def __call__(self, record: dict[str, Any]) -> None:
        conn = self._connect()
        cols = list(_CANONICAL_COLUMNS) + list(self._extra)
        created = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        values = [record.get(c) for c in cols] + [created]
        col_names = ", ".join(cols + ["created_at"])
        placeholders = ", ".join("?" for _ in range(len(cols) + 1))
        conn.execute(
            f"INSERT INTO {self._table} ({col_names}) VALUES ({placeholders})",
            values,
        )
        conn.commit()
