"""Dashboard and notification dates follow the active cycle, not a fixed October."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "data" / "seed_db.py"
sys.path.insert(0, str(ROOT))

HEADERS = {"X-Customer-Id": "cust_acme"}

# Global leader mail lands on these days of the pay month, plus pay day (29) and the 30th close.
GLOBAL_DAYS = (10, 15, 16, 19, 20, 22, 23, 25, 26, 27, 28, 29, 30)


@pytest.fixture()
def api_client(tmp_path):
    db = tmp_path / "payroll_clarity.db"
    subprocess.check_call([sys.executable, str(SEED), "--db", str(db), "--seed", "42"], cwd=str(ROOT))
    from server.db.connection import set_db_path
    from server.app import create_app

    set_db_path(db)
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def _iso(as_of: str, day: int) -> str:
    year, month, _day = as_of.split("-")
    return f"{year}-{month}-{day:02d}"


def _global_days_due(as_of: str) -> set:
    return {_iso(as_of, day) for day in GLOBAL_DAYS if _iso(as_of, day) <= as_of}


CASES = [
    ("2026-10-12", "October", "2026-10-29", "2026-10-28", [], False),
    ("2026-10-30", "October", "2026-10-29", "2026-10-28", [], True),
    ("2026-11-14", "November", "2026-11-29", "2026-11-28", ["October"], False),
    ("2026-11-30", "November", "2026-11-29", "2026-11-28", ["October"], True),
    ("2026-12-05", "December", "2026-12-29", "2026-12-28", ["November", "October"], False),
    ("2027-01-10", "January", "2027-01-29", "2027-01-28", ["December", "November", "October"], False),
]


@pytest.mark.parametrize("as_of,month,pay,submitted,earlier,highlight", CASES)
def test_dashboard_and_notifications_follow_the_month(api_client, as_of, month, pay, submitted, earlier, highlight):
    overview = api_client.get(f"/api/cycles/current/overview?asOf={as_of}", headers=HEADERS)
    assert overview.status_code == 200, overview.json
    body = overview.json
    assert body["cycle"]["label"].startswith(month)
    assert body["cycle"]["payDate"] == pay
    assert body["cycle"]["submitted"] == submitted
    assert body["dates"]["payDate"] == pay
    assert body["dates"]["submitted"] == submitted
    # Milestones are the same day-of-month in whatever month is open.
    year, mon, _day = pay.split("-")
    assert body["dates"]["inputDeadline"].endswith("-22")
    assert body["dates"]["inputDeadline"].startswith(f"{year}-{mon}")
    report_day = f"{year}-{mon}-20"
    report = next((row for row in body.get("upNext") or [] if row.get("title") == "Final report"), None)
    if as_of <= report_day:
        assert report and report["deadline"] == report_day
    else:
        assert report is None

    banner = body.get("octoberSummary")
    if highlight:
        assert banner and banner["month"] == month
        assert banner["payDateLabel"].split()[0][:3] == month[:3]
    else:
        assert banner is None
    assert [row["month"] for row in body.get("previousPayrolls") or []] == earlier

    notes = api_client.get(f"/api/notifications?asOf={as_of}&channel=email", headers=HEADERS)
    assert notes.status_code == 200, notes.json
    rows = notes.json["notifications"]
    prefix = "-".join(as_of.split("-")[:2])
    global_now = [
        n
        for n in rows
        if n.get("audience") == "global" and str(n.get("sendDate") or "").startswith(prefix)
    ]
    assert {n["sendDate"] for n in global_now} == _global_days_due(as_of)
    assert all((n.get("subject") or "").startswith(month) for n in global_now)
    if _iso(as_of, 10) <= as_of:
        window = next(n for n in global_now if "employee window is open" in (n.get("subject") or ""))
        assert month[:3] in (window.get("bodySummary") or "")
        if month != "October":
            assert "Oct " not in (window.get("bodySummary") or "")
            assert not (window.get("subject") or "").startswith("October")

    india = [
        n
        for n in rows
        if n.get("audience") == "country"
        and n.get("country") == "India"
        and str(n.get("sendDate") or "").startswith(prefix)
    ]
    assert india
    schedule = next(n for n in india if n["sendDate"] == _iso(as_of, 3))
    assert month in (schedule.get("subject") or "")
    assert "schedule" in (schedule.get("bodySummary") or "").lower()
    assert f"{month[:3]} 20" in (schedule.get("bodySummary") or "")
    assert month[:3] in (schedule.get("bodySummary") or "")
    if month != "October":
        assert "Oct " not in (schedule.get("bodySummary") or "")
