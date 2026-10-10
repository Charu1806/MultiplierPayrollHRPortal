"""SQLite connection for the issue & cycle store."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = ROOT / "data" / "payroll_clarity.db"

# CLARITY_DB_PATH lets test runners (Playwright) point the API at an isolated copy.
_db_path: Path = Path(os.environ.get("CLARITY_DB_PATH") or DEFAULT_DB)


def set_db_path(path: Path) -> None:
    global _db_path
    _db_path = Path(path)


def get_db_path() -> Path:
    return _db_path


def connect(db_path: Optional[Path] = None) -> sqlite3.Connection:
    path = Path(db_path) if db_path else _db_path
    conn = sqlite3.connect(str(path), check_same_thread=False, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn
