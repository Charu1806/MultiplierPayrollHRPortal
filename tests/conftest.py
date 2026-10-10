"""Shared fixtures for Payroll Clarity edge-case tests."""

from __future__ import annotations

import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
DB_PATH = DATA / "payroll_clarity.db"
SEED = DATA / "seed_db.py"

sys.path.insert(0, str(DATA))


@pytest.fixture(scope="session")
def db_path(tmp_path_factory) -> Path:
    """Fresh seeded DB for the test session (does not clobber project DB)."""
    out = tmp_path_factory.mktemp("db") / "payroll_clarity.db"
    subprocess.check_call(
        [sys.executable, str(SEED), "--db", str(out), "--seed", "42"],
        cwd=str(ROOT),
    )
    return out


@pytest.fixture
def conn(db_path: Path):
    c = sqlite3.connect(db_path)
    c.row_factory = sqlite3.Row
    yield c
    c.close()


@pytest.fixture
def baseline_issues():
    """Oct 12 open issues (Priya's issue_004 appears only after she is added)."""
    return [
        {
            "id": "issue_001",
            "title": "Missing tax ID",
            "severity": "blocking",
            "employee_id": "emp_lena",
            "country": "Germany",
            "owner": "HR admin",
            "deadline": "2026-10-15",
            "status": "open",
        },
        {
            "id": "issue_002",
            "title": "Salary up 3x",
            "severity": "needs_confirmation",
            "employee_id": "emp_james",
            "country": "UK",
            "owner": "HR admin",
            "deadline": "2026-10-15",
            "status": "open",
        },
        {
            "id": "issue_003",
            "title": "Missing CPF",
            "severity": "blocking",
            "employee_id": "emp_beatriz",
            "country": "Brazil",
            "owner": "HR admin",
            "deadline": "2026-10-15",
            "status": "open",
        },
    ]


@pytest.fixture
def baseline_emails():
    """Computed-style email templates (action counts filled live by the API)."""
    return [
        {
            "id": "notif_oct12",
            "send_date": "2026-10-12",
            "subject": "3 days to input finalisation: 3 actions",
            "channel": "email",
            "action_count": 3,
            "recipient": "HR admin",
        },
        {
            "id": "notif_oct14",
            "send_date": "2026-10-14",
            "subject": "Cutoff tomorrow: 2 blocking items",
            "channel": "email",
            "action_count": 2,
            "recipient": "HR admin",
        },
        {
            "id": "notif_oct15",
            "send_date": "2026-10-15",
            "subject": "Cutoff today: 3 items still open",
            "channel": "email",
            "action_count": 3,
            "recipient": "HR admin",
        },
        {
            "id": "notif_oct17",
            "send_date": "2026-10-17",
            "subject": "Payroll ready for review: 6 lines need your check · approve by Oct 22",
            "channel": "email",
            "action_count": 0,
            "recipient": "HR admin",
        },
        {
            "id": "notif_oct20",
            "send_date": "2026-10-20",
            "subject": "Reminder: 2 days left to review · 6 lines still open",
            "channel": "email",
            "action_count": 0,
            "recipient": "HR admin",
        },
        {
            "id": "notif_oct22_finance",
            "send_date": "2026-10-22",
            "subject": "Funding due Oct 23",
            "channel": "email",
            "action_count": 0,
            "recipient": "Finance",
        },
    ]
