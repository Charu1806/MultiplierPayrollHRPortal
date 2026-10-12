"""Sync-driven payroll lifecycle."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "data" / "seed_db.py"
sys.path.insert(0, str(ROOT))

HEADERS = {"X-Customer-Id": "cust_acme", "Content-Type": "application/json"}


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


def _james_snapshot(api_client, as_of="2026-10-12"):
    r = api_client.get(f"/api/employees/emp_james?asOf={as_of}", headers=HEADERS)
    assert r.status_code == 200
    return r.json


def test_hr_edit_does_not_change_snapshot_until_sync(api_client):
    before = _james_snapshot(api_client)
    snapshot = before["payrollSnapshot"]["baseSalary"]
    patched = api_client.patch(
        "/api/employees/emp_james?asOf=2026-10-12",
        headers=HEADERS,
        json={"baseSalary": snapshot + 500, "allowances": 0, "unpaidLeaveDays": 0, "confirmAiCheck": True},
    )
    assert patched.status_code == 200
    assert patched.json["saveMessage"] == "Saved in HR tool"
    after = _james_snapshot(api_client)
    assert after["payrollSnapshot"]["baseSalary"] == snapshot
    assert after["salary"]["base"] == snapshot + 500

    synced = api_client.post("/api/sync?asOf=2026-10-12", headers=HEADERS, json={"trigger": "Manual"})
    assert synced.status_code == 200
    assert synced.json["trigger"] == "Manual"
    activity = synced.json["activity"]
    changed_ids = {row["id"] for row in activity["bonuses"] + activity["hikes"]}
    assert synced.json["added"] == len(activity["newEmployees"])
    assert synced.json["changed"] == len(changed_ids)
    assert synced.json["summary"] == (
        f"+{synced.json['added']} added, {synced.json['changed']} changed, {synced.json['exited']} exited"
    )
    assert any(row["id"] == "emp_james" for row in activity["hikes"])
    assert _james_snapshot(api_client)["payrollSnapshot"]["baseSalary"] == snapshot + 500
    overview = api_client.get("/api/cycles/current/overview?asOf=2026-10-12", headers=HEADERS).json
    james_change = next(row for row in overview["recentChanges"] if row["employeeId"] == "emp_james")
    assert james_change["kind"] == "hike"
    assert james_change["cycleAssignment"] == "current"
    review = api_client.get("/api/review?asOf=2026-10-12", headers=HEADERS).json
    james = next(line for line in review["lines"] if line["employeeId"] == "emp_james")
    assert james["approved"] is False


def test_sync_summary_counts_people_added_this_cycle(api_client):
    created = api_client.post(
        "/api/employees",
        headers=HEADERS,
        json={
            "name": "Noah Test",
            "country": "India",
            "workEmail": "noah.test@acmetech.example",
            "asOf": "2026-10-14",
        },
    )
    assert created.status_code == 201, created.json
    synced = api_client.post("/api/sync?asOf=2026-10-14", headers=HEADERS, json={"trigger": "Manual"})
    assert synced.status_code == 200, synced.json
    names = [row["name"] for row in synced.json["activity"]["newEmployees"]]
    assert "Noah Test" in names
    assert synced.json["added"] == len(names)
    assert synced.json["added"] >= 1
    assert synced.json["summary"].startswith(f"+{synced.json['added']} added")
    status = api_client.get("/api/sync?asOf=2026-10-14", headers=HEADERS).json
    assert status["lastSync"]["added"] == synced.json["added"]
    assert status["lastSync"]["summary"] == synced.json["summary"]


def test_earlier_date_does_not_pull_a_later_sync(api_client):
    later = api_client.post("/api/sync?asOf=2026-11-06", headers=HEADERS, json={"trigger": "Manual"})
    assert later.status_code == 200
    earlier = api_client.get("/api/sync?asOf=2026-10-12", headers=HEADERS).json
    assert earlier["manualRemaining"] == 1
    assert earlier["lastSync"]["syncedAt"].startswith("2026-10-01")
    assert earlier["lastSync"]["userInitiated"] is False
    same_day = api_client.get("/api/sync?asOf=2026-11-06", headers=HEADERS).json
    assert same_day["manualRemaining"] == 0
    assert same_day["lastSync"]["syncedAt"].startswith("2026-11-06")


def test_seed_sync_does_not_use_the_oct_1_allowance(api_client):
    status = api_client.get("/api/sync?asOf=2026-10-01", headers=HEADERS).json
    assert status["lastSync"]["userInitiated"] is False
    assert status["manualRemaining"] == 1
    first = api_client.post("/api/sync?asOf=2026-10-01", headers=HEADERS, json={"trigger": "Manual"})
    assert first.status_code == 200


def test_manual_sync_daily_limit(api_client):
    first = api_client.post("/api/sync?asOf=2026-10-12", headers=HEADERS, json={"trigger": "Manual"})
    assert first.status_code == 200
    second = api_client.post("/api/sync?asOf=2026-10-12", headers=HEADERS, json={"trigger": "Manual"})
    assert second.status_code == 429
    status = api_client.get("/api/sync?asOf=2026-10-12", headers=HEADERS).json
    assert status["manualUsedToday"] == 1
    assert status["manualRemaining"] == 0
    next_day = api_client.post("/api/sync?asOf=2026-10-13", headers=HEADERS, json={"trigger": "Manual"})
    assert next_day.status_code == 200


def test_final_sync_is_idempotent_and_does_not_use_the_manual_allowance(api_client):
    final = api_client.post("/api/sync?asOf=2026-10-23", headers=HEADERS, json={"trigger": "Final"})
    assert final.status_code == 200
    assert final.json["trigger"] == "Final"
    before_manual = api_client.get("/api/sync?asOf=2026-10-23", headers=HEADERS).json
    assert before_manual["manualRemaining"] == 1
    manual = api_client.post("/api/sync?asOf=2026-10-23", headers=HEADERS, json={"trigger": "Manual"})
    assert manual.status_code == 200
    again = api_client.post("/api/sync?asOf=2026-10-23", headers=HEADERS, json={"trigger": "Final"})
    assert again.status_code == 200
    assert again.json["idempotent"] is True
    after = api_client.get("/api/sync?asOf=2026-10-23", headers=HEADERS).json
    assert after["manualUsedToday"] == 1
    notes = api_client.get("/api/notifications?asOf=2026-10-23", headers=HEADERS)
    funding = [n for n in notes.json["notifications"] if "Funding request" in (n.get("subject") or "")]
    assert len(funding) == 1
    from server.db.connection import connect

    kinds = [row[0] for row in connect().execute("SELECT kind FROM funding_snapshots ORDER BY kind").fetchall()]
    assert kinds == ["baseline", "final"]
    overview = api_client.get("/api/cycles/current/overview?asOf=2026-10-23", headers=HEADERS)
    variance = overview.json["fundingVariance"]
    assert variance["reconciles"] is True
    assert abs(variance["forex"] + variance["employerRates"] + variance["other"] - variance["total"]) < 0.02


def test_failed_sync_keeps_the_previous_snapshot(api_client):
    from server.db.connection import connect
    from server.db.repositories import Store
    from server.services.sync import SyncFailed, run_sync

    before = _james_snapshot(api_client)["payrollSnapshot"]["baseSalary"]
    api_client.patch(
        "/api/employees/emp_james?asOf=2026-10-18",
        headers=HEADERS,
        json={"baseSalary": before + 100, "allowances": 0, "unpaidLeaveDays": 0, "confirmAiCheck": True},
    )
    store = Store(connect())
    with pytest.raises(SyncFailed):
        run_sync(store, "cust_acme", "2026-10-18", trigger="Manual", fail=True)
    assert _james_snapshot(api_client, "2026-10-18")["payrollSnapshot"]["baseSalary"] == before
    status = api_client.get("/api/sync?asOf=2026-10-18", headers=HEADERS)
    assert status.json["lastSync"]["syncedAt"].startswith("2026-10-01")
    assert status.json["lastSync"]["status"] == "success"
    assert status.json["lastSync"]["userInitiated"] is False
    recovered = api_client.post("/api/sync?asOf=2026-10-18", headers=HEADERS, json={"trigger": "Manual"})
    assert recovered.status_code == 200
    assert recovered.json["userInitiated"] is True
    assert _james_snapshot(api_client, "2026-10-18")["payrollSnapshot"]["baseSalary"] == before + 100


def test_late_change_is_next_cycle(api_client):
    before = _james_snapshot(api_client, "2026-10-24")["payrollSnapshot"]["baseSalary"]
    api_client.patch(
        "/api/employees/emp_james?asOf=2026-10-24",
        headers=HEADERS,
        json={"baseSalary": before + 250, "allowances": 0, "unpaidLeaveDays": 0, "confirmAiCheck": True},
    )
    synced = api_client.post("/api/sync?asOf=2026-10-24", headers=HEADERS, json={"trigger": "Manual"})
    assert synced.status_code == 200
    assert synced.json["changed"] == 0
    assert _james_snapshot(api_client, "2026-10-24")["payrollSnapshot"]["baseSalary"] == before
    overview = api_client.get("/api/cycles/current/overview?asOf=2026-10-24", headers=HEADERS)
    late = next(row for row in overview.json["recentChanges"] if row["employeeId"] == "emp_james")
    assert late["cycleAssignment"] == "next"
    november = api_client.post("/api/sync?asOf=2026-11-01", headers=HEADERS, json={"trigger": "Manual"})
    assert november.status_code == 200
    assert november.json["changed"] == 1
    assert _james_snapshot(api_client, "2026-11-01")["payrollSnapshot"]["baseSalary"] == before + 250


def test_headline_counts_reconcile_and_deadlines_match(api_client):
    overview = api_client.get("/api/cycles/current/overview?asOf=2026-10-12", headers=HEADERS).json
    ready = overview["readiness"]
    assert ready["changed"] == ready["needAction"] + ready["needApproval"] + ready["matched"]
    assert ready["reconciles"] is True
    deadline = "2026-10-22"
    assert overview["cycle"]["inputFinalisation"] == deadline
    assert overview["cycle"]["inputDeadline"] == deadline
    milestones = {row["title"]: row for row in overview["upNext"]}
    assert milestones["Input finalisation"]["deadline"] == deadline
    assert milestones["Review window"]["deadlineEnd"] == deadline
    assert overview["cycle"]["fundingDue"] == "2026-10-26"
    assert overview["cycle"]["submitted"] == "2026-10-27"
    assert overview["cycle"]["payDate"] == "2026-10-29"
    assert milestones["Funding (finance)"]["deadline"] == "2026-10-26"
    assert milestones["Payroll submitted"]["deadline"] == "2026-10-27"
    assert milestones["Pay day"]["deadline"] == "2026-10-29"
    assert overview["dates"]["fundingDue"] == "2026-10-26"
    assert overview["dates"]["submitted"] == "2026-10-27"
    assert overview["dates"]["payDate"] == "2026-10-29"
    issues = api_client.get("/api/issues?asOf=2026-10-12&status=open", headers=HEADERS).json["issues"]
    assert {i["id"] for i in issues} == {"issue_001", "issue_003"}
    assert all(i["deadline"] == deadline for i in issues)
    assert all("Salary up" not in i["title"] for i in issues)
    review = api_client.get("/api/review?asOf=2026-10-12", headers=HEADERS).json
    assert "Oct 22" in review["header"]


def test_payroll_owned_field_revalidates_without_a_full_sync(api_client):
    before = api_client.get("/api/issues?asOf=2026-10-12&status=open", headers=HEADERS).json["issues"]
    assert any(i["id"] == "issue_001" for i in before)
    saved = api_client.post(
        "/api/issues/issue_001/resolve?asOf=2026-10-12",
        headers=HEADERS,
        json={"resolution": "add_here", "payload": {"taxId": "12345678903"}, "actor": "HR admin"},
    )
    assert saved.status_code == 200
    after = api_client.get("/api/issues?asOf=2026-10-12&status=open", headers=HEADERS).json["issues"]
    assert all(i["id"] != "issue_001" for i in after)
    status = api_client.get("/api/sync?asOf=2026-10-12", headers=HEADERS).json
    assert status["manualRemaining"] == 1


def test_pay_day_categories_do_not_overlap(api_client):
    body = api_client.get("/api/cycles/current/overview?asOf=2026-10-29", headers=HEADERS).json
    outcomes = body["payOutcomes"]
    assert outcomes["simulated"] is True
    assert outcomes["paymentReturned"]["count"] == 0
    ids = _outcome_ids(outcomes)
    assert len(ids) == len(set(ids))
    eligible = (
        outcomes["paidSuccessfully"]["count"]
        + outcomes["paidPreviousSalary"]["count"]
        + outcomes["missingInputs"]["count"]
        + outcomes["paymentReturned"]["count"]
    )
    assert outcomes["paidSuccessfully"]["of"] == eligible
    if outcomes["paidPreviousSalary"]["count"]:
        assert outcomes["paidPreviousSalary"]["href"] == "/payroll/review"
    else:
        assert outcomes["paidPreviousSalary"]["href"] is None
    missing = outcomes["missingInputs"]
    if missing["count"] == 1:
        assert missing["href"].startswith("/payroll/actions?issue=")
    elif missing["count"] > 1:
        assert missing["href"] == "/payroll/actions"
    else:
        assert missing["href"] is None

    later = api_client.get("/api/cycles/current/overview?asOf=2026-10-30", headers=HEADERS).json["payOutcomes"]
    assert later["paymentReturned"]["count"] == 1
    returned_ids = _outcome_ids(later)
    assert returned_ids.count("emp_david") == 0
    assert len(returned_ids) == len(set(returned_ids))


def _outcome_ids(outcomes):
    ids = list(outcomes["paidSuccessfully"].get("employeeIds") or [])
    for bucket in (
        outcomes["paidPreviousSalary"]["employees"],
        outcomes["missingInputs"]["employees"],
        outcomes["addedAfterCutoff"]["employees"],
    ):
        ids.extend(row["id"] for row in bucket)
    return ids


def test_targeted_refresh_updates_the_snapshot_without_using_the_daily_sync(api_client):
    before = _james_snapshot(api_client)["payrollSnapshot"]["baseSalary"]
    patched = api_client.patch(
        "/api/employees/emp_james?asOf=2026-10-12",
        headers=HEADERS,
        json={"baseSalary": before + 80, "allowances": 0, "unpaidLeaveDays": 0, "confirmAiCheck": True},
    )
    assert patched.status_code == 200
    refreshed = api_client.post("/api/sync/refresh/emp_james?asOf=2026-10-12", headers=HEADERS, json={})
    assert refreshed.status_code == 200
    assert refreshed.json["cycleAssignment"] == "current"
    assert refreshed.json["payrollSnapshot"]["baseSalary"] == before + 80
    status = api_client.get("/api/sync?asOf=2026-10-12", headers=HEADERS).json
    assert status["manualRemaining"] == 1
    full = api_client.post("/api/sync?asOf=2026-10-12", headers=HEADERS, json={"trigger": "Manual"})
    assert full.status_code == 200


def test_november_prototype_date_uses_the_november_deadline(api_client):
    overview = api_client.get("/api/cycles/current/overview?asOf=2026-11-12", headers=HEADERS).json
    assert overview["cycle"]["label"] == "November 2026"
    assert overview["cycle"]["stage"] == "Inputs & review"
    assert overview["cycle"]["inputDeadline"] == "2026-11-22"
    assert overview["cycle"]["finalSync"] == "2026-11-23"
    assert overview["cycle"]["fundingDue"] == "2026-11-26"
    assert overview["cycle"]["submitted"] == "2026-11-27"
    assert overview["cycle"]["payDate"] == "2026-11-29"
    assert overview["payOutcomes"] is None
    assert overview["readiness"]["reconciles"] is True


def test_deadline_reminders_follow_configured_offsets(api_client):
    early = api_client.get("/api/notifications?asOf=2026-10-12", headers=HEADERS).json["notifications"]
    early_subjects = {n["subject"] for n in early}
    early_dates = {n["sendDate"] for n in early if "add inputs and finish review" in n["subject"]}
    assert early_dates == {"2026-10-01", "2026-10-10"}
    assert "21 days left to add inputs and finish review" in early_subjects
    assert "12 days left to add inputs and finish review" in early_subjects
    mid = api_client.get("/api/notifications?asOf=2026-10-15", headers=HEADERS).json["notifications"]
    assert any(n["subject"] == "7 days left to add inputs and finish review" and n["sendDate"] == "2026-10-15" for n in mid)
    day20 = api_client.get("/api/notifications?asOf=2026-10-20", headers=HEADERS).json["notifications"]
    assert any(n["subject"] == "2 days left to add inputs and finish review" and n["sendDate"] == "2026-10-20" for n in day20)
    day21 = api_client.get("/api/notifications?asOf=2026-10-21", headers=HEADERS).json["notifications"]
    assert any(n["subject"] == "1 day left to add inputs and finish review" and n["sendDate"] == "2026-10-21" for n in day21)
    skipped = {"2026-10-04", "2026-10-07", "2026-10-13", "2026-10-16", "2026-10-19"}
    assert skipped.isdisjoint({n["sendDate"] for n in day21 if "add inputs and finish review" in n["subject"]})
    due = api_client.get("/api/notifications?asOf=2026-10-22", headers=HEADERS).json["notifications"]
    subjects = {n["subject"] for n in due}
    assert "Last day to add inputs and finish review" in subjects
    before_funding = api_client.get("/api/notifications?asOf=2026-10-23", headers=HEADERS).json["notifications"]
    assert all(n.get("recipient") != "Finance" or n.get("sendDate") != "2026-10-23" for n in before_funding)
    finance = api_client.get("/api/notifications?asOf=2026-10-26", headers=HEADERS).json["notifications"]
    funding = [n for n in finance if n.get("recipient") == "Finance" and n.get("sendDate") == "2026-10-26"]
    assert funding
    assert "Add funds" in funding[0]["subject"]
    submitted = api_client.get("/api/notifications?asOf=2026-10-27", headers=HEADERS).json["notifications"]
    assert any(n["subject"] == "Payroll submitted" and n["sendDate"] == "2026-10-27" for n in submitted)
    paid = api_client.get("/api/notifications?asOf=2026-10-29", headers=HEADERS).json["notifications"]
    assert any(n["kind"] == "paid" and n["sendDate"] == "2026-10-29" for n in paid)
    assert all(n.get("kind") != "paid" or n.get("sendDate") != "2026-10-28" for n in paid)


def test_next_cycle_approval_does_not_rewrite_october(api_client):
    october = api_client.get("/api/review?asOf=2026-10-20", headers=HEADERS).json
    james = next(line for line in october["lines"] if line["employeeId"] == "emp_james")
    assert james["approved"] is False
    assert "£8,000" in james["carryNote"]
    november = api_client.get("/api/review?asOf=2026-11-17", headers=HEADERS).json
    carry = next(
        line
        for line in november["lines"]
        if line["employeeId"] == "emp_james" and line.get("origin") == "october_carry"
    )
    approved = api_client.post(
        f"/api/review/{carry['id']}/approve?asOf=2026-11-17",
        headers=HEADERS,
        json={"asOf": "2026-11-17"},
    )
    assert approved.status_code == 200
    still = api_client.get("/api/review?asOf=2026-10-20", headers=HEADERS).json
    james_again = next(line for line in still["lines"] if line["employeeId"] == "emp_james")
    assert james_again["approved"] is False
    assert "£8,000" in james_again["carryNote"]


def test_previous_cycle_banner_matches_missed_runs_and_movement(api_client):
    from server.db.connection import connect
    from server.db.repositories import Store
    from server.services.sync import payday_outcomes

    store = Store(connect())
    outcomes = payday_outcomes(store, "cust_acme", "2026-10-29")
    after_pay = payday_outcomes(store, "cust_acme", "2026-10-30")
    assert outcomes
    assert after_pay
    early = api_client.get("/api/cycles/current/overview?asOf=2026-10-29", headers=HEADERS)
    assert early.status_code == 200
    assert early.json.get("octoberSummary") is None
    assert early.json.get("previousPayrolls") == []
    closing = api_client.get("/api/cycles/current/overview?asOf=2026-10-30", headers=HEADERS)
    assert closing.status_code == 200
    highlight = closing.json["octoberSummary"]
    assert highlight["month"] == "October"
    assert highlight["paid"] == after_pay["paidSuccessfully"]["count"]
    assert closing.json.get("previousPayrolls") == []
    later = api_client.get("/api/cycles/current/overview?asOf=2026-11-01", headers=HEADERS)
    assert later.status_code == 200
    assert later.json.get("octoberSummary") is None
    final = payday_outcomes(store, "cust_acme", "2026-10-31")
    summary = later.json["previousPayrolls"][0]
    assert summary["month"] == "October"
    assert summary["paid"] == final["paidSuccessfully"]["count"]
    assert summary["of"] == final["paidSuccessfully"]["of"]
    assert summary["paidPreviousSalary"]["count"] == final["paidPreviousSalary"]["count"]
    assert summary["missingInputs"]["count"] == final["missingInputs"]["count"]
    assert summary["addedAfterCutoff"]["count"] == final["addedAfterCutoff"]["count"]
    assert summary["paymentReturned"]["count"] == final["paymentReturned"]["count"]
    assert after_pay["paymentReturned"]["count"] >= outcomes["paymentReturned"]["count"]
    assert summary["paid"] == final["paidSuccessfully"]["count"]
    assert "arrears" not in summary["message"]
    assert "carried over" not in summary["message"]
    late_ids = {row["id"] for row in outcomes["addedAfterCutoff"]["employees"]}
    assert summary["added"]["count"] >= len(late_ids)
    if summary["paidPreviousSalary"]["count"]:
        assert summary["paidPreviousSalary"]["href"] == "/payroll/review"
    if summary["added"]["count"] == 1:
        assert summary["added"]["href"].startswith("/people/")
    elif summary["added"]["count"] > 1:
        assert summary["added"]["href"] == "/people"


def test_persona_reports_use_the_month_milestones(api_client):
    early = api_client.get("/api/notifications?asOf=2026-10-12", headers=HEADERS).json["notifications"]
    early_global = [n for n in early if n.get("audience") == "global"]
    assert {n["sendDate"] for n in early_global} == {"2026-10-10"}
    assert "employee window" in (early_global[0].get("subject") or "").lower()
    india_early = [n for n in early if n.get("audience") == "country" and n.get("country") == "India"]
    assert {n["sendDate"] for n in india_early} == {"2026-10-03", "2026-10-10"}
    schedule = next(n for n in india_early if n["sendDate"] == "2026-10-03")
    assert "schedule" in (schedule.get("bodySummary") or "").lower()
    assert "Open overview" in (schedule.get("ctaLabel") or "")
    employee_early = [n for n in early if n.get("audience") == "employee"]
    assert employee_early
    assert {n["sendDate"] for n in employee_early} == {"2026-10-10"}
    assert "miss payment this cycle" in (employee_early[0].get("bodySummary") or "")

    later = api_client.get("/api/notifications?asOf=2026-10-22", headers=HEADERS).json["notifications"]
    global_reports = [n for n in later if n.get("audience") == "global"]
    assert {n["sendDate"] for n in global_reports} == {
        "2026-10-10",
        "2026-10-15",
        "2026-10-16",
        "2026-10-19",
        "2026-10-20",
        "2026-10-22",
    }
    final_report = next(n for n in global_reports if n["sendDate"] == "2026-10-20")
    assert (final_report.get("bodySummary") or "").startswith("You can ignore this if nothing is still open.")
    assert "3 days" in (final_report.get("bodySummary") or "")
    assert "Open overview" in (final_report.get("ctaLabel") or "")
    india = [n for n in later if n.get("audience") == "country" and n.get("country") == "India"]
    assert {n["sendDate"] for n in india} == {
        "2026-10-03",
        "2026-10-10",
        "2026-10-13",
        "2026-10-14",
        "2026-10-15",
        "2026-10-16",
        "2026-10-18",
        "2026-10-19",
        "2026-10-20",
        "2026-10-21",
        "2026-10-22",
    }
    escalated = next(n for n in india if n["sendDate"] == "2026-10-18")
    assert (escalated.get("bodySummary") or "").startswith("You can ignore this if nothing is still open.")
    final = next(n for n in india if n["sendDate"] == "2026-10-22")
    assert final.get("cc")
    assert "last day" in (final.get("bodySummary") or "").lower()
    employees = [n for n in later if n.get("audience") == "employee"]
    assert employees
    assert {n["sendDate"] for n in employees} <= {"2026-10-10", "2026-10-13", "2026-10-14", "2026-10-15"}
    assert "miss payment this cycle" in (employees[0].get("bodySummary") or "")

    paid = api_client.get("/api/notifications?asOf=2026-10-29", headers=HEADERS).json["notifications"]
    global_paid = [n for n in paid if n.get("audience") == "global"]
    assert {n["sendDate"] for n in global_paid} == {
        "2026-10-10",
        "2026-10-15",
        "2026-10-16",
        "2026-10-19",
        "2026-10-20",
        "2026-10-22",
        "2026-10-23",
        "2026-10-25",
        "2026-10-26",
        "2026-10-29",
    }
    oct_23 = [n for n in global_paid if n["sendDate"] == "2026-10-23"]
    assert len(oct_23) == 2
    funding = next(n for n in oct_23 if "with finance" in (n.get("bodySummary") or ""))
    forecast = next(n for n in oct_23 if "will be paid" in (n.get("bodySummary") or ""))
    assert "will miss payment" in (forecast.get("bodySummary") or "")
    india_23 = [
        n
        for n in paid
        if n.get("audience") == "country" and n.get("country") == "India" and n["sendDate"] == "2026-10-23"
    ]
    assert len(india_23) == 2
    assert any("add funds" in (n.get("subject") or "").lower() for n in india_23)
    assert any("will be paid" in (n.get("bodySummary") or "") for n in india_23)
    added = next(n for n in global_paid if n["sendDate"] == "2026-10-25")
    assert "Funds added: Yes" in (added.get("bodySummary") or "")
    payday = next(n for n in global_paid if n["sendDate"] == "2026-10-29")
    assert "Amount paid:" in (payday.get("bodySummary") or "")
    assert "were affected" in (payday.get("bodySummary") or "")
    india_paid = next(
        n for n in paid if n.get("audience") == "country" and n.get("country") == "India" and n["sendDate"] == "2026-10-29"
    )
    assert "paid" in (india_paid.get("bodySummary") or "").lower()
    assert "next cycle" in (india_paid.get("bodySummary") or "").lower()

    closing = api_client.get("/api/notifications?asOf=2026-10-30", headers=HEADERS).json["notifications"]
    global_close = [n for n in closing if n.get("audience") == "global" and n["sendDate"] == "2026-10-30"]
    assert len(global_close) == 1
    assert "were paid" in (global_close[0].get("bodySummary") or "")
    assert "missed payment" in (global_close[0].get("bodySummary") or "")
    india_close = next(
        n
        for n in closing
        if n.get("audience") == "country" and n.get("country") == "India" and n["sendDate"] == "2026-10-30"
    )
    assert "were paid" in (india_close.get("bodySummary") or "")
    assert "missed payment" in (india_close.get("bodySummary") or "")


def test_alt_dataset_exposes_the_sync_keys():
    from domain.config import cycle_config, reload

    import os

    os.environ["DATASET"] = "alt"
    reload()
    try:
        cy = cycle_config()
        october = cy["cycles"]["october"]
        assert october["inputDeadline"] == october["inputFinalisation"] == "2026-10-10"
        assert october["finalSync"]
        assert cy["sync"]["maxPerDay"] == 1
        assert cy["reminders"]["daysOfMonth"] == [1, 10, 15, 20, 21, 22]
    finally:
        os.environ.pop("DATASET", None)
        reload()
