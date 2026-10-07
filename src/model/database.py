"""SQLite connection management and schema creation.

The service opens one short-lived connection per request instead of sharing a
global connection, which keeps the threaded HTTP server free of locking
surprises.  WAL journalling plus a busy timeout keeps concurrent readers fast.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator

SCHEMA_VERSION = 1

_SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS calculation_history (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        expression   TEXT    NOT NULL,
        result       TEXT    NOT NULL,
        result_value REAL,
        is_favorite  INTEGER NOT NULL DEFAULT 0,
        created_at   TEXT    NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_calculation_history_created_at
        ON calculation_history (created_at DESC, id DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_calculation_history_expression
        ON calculation_history (expression)
    """,
)


class Database:
    """Owns the SQLite file and knows how to (de)serialise access to it."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    # -- lifecycle ----------------------------------------------------------
    def initialize(self) -> None:
        """Create the file, the tables and the indexes if they do not exist."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as connection:
            for statement in _SCHEMA_STATEMENTS:
                connection.execute(statement)
            connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        self.ensure_initialized()

    def ensure_initialized(self) -> None:
        """Fail fast with an actionable message when the schema is missing."""
        if not self.path.exists():
            raise RuntimeError(
                f"The database file {self.path} does not exist. "
                "Run 'python scripts/init_db.py' first."
            )
        with self.connection() as connection:
            row = connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
                ("calculation_history",),
            ).fetchone()
        if row is None:
            raise RuntimeError(
                "The calculation_history table is missing. "
                "Run 'python scripts/init_db.py' first."
            )

    # -- connections --------------------------------------------------------
    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        """Yield a connection; commit on success, roll back on failure."""
        connection = sqlite3.connect(self.path, timeout=10.0)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA busy_timeout = 5000")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    # -- diagnostics --------------------------------------------------------
    def health(self) -> dict:
        """Return a small status report used by ``GET /api/health``."""
        try:
            with self.connection() as connection:
                total = connection.execute(
                    "SELECT COUNT(*) AS total FROM calculation_history"
                ).fetchone()["total"]
            return {
                "status": "ok",
                "path": str(self.path),
                "records": int(total),
                "schema_version": SCHEMA_VERSION,
                "checked_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
        except sqlite3.Error as error:
            return {
                "status": "error",
                "path": str(self.path),
                "message": str(error),
                "checked_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
