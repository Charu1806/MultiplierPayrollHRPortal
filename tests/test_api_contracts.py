"""Clarity API contract tests — /api (round 1)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "data" / "seed_db.py"

sys.path.insert(0, str(ROOT))


@pytest.fixture()
def api_client(tmp_path):
    """Fresh seeded DB + Flask test client per test."""
    db = tmp_path / "payroll_clarity.db"
    subprocess.check_call(
        [sys.executable, str(SEED), "--db", str(db), "--seed", "42"],
        cwd=str(ROOT),
    )
    from server.db.connection import set_db_path
    from server.app import create_app

    set_db_path(db)
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


HEADERS = {"X-Customer-Id": "cust_acme"}
JSON_HEADERS = {"X-Customer-Id": "cust_acme", "Content-Type": "application/json"}


class TestHealthAndMeta:
    def test_health(self, api_client):
        r = api_client.get("/health")
        assert r.status_code == 200
        assert r.json["status"] == "ok"

    def test_request_id_header(self, api_client):
        r = api_client.get("/health", headers={"X-Request-Id": "demo-1"})
        assert r.headers.get("X-Request-Id") == "demo-1"

    def test_prototype_dates(self, api_client):
        r = api_client.get("/api/meta/prototype-dates", headers=HEADERS)
        assert r.status_code == 200
        assert "2026-10-12" in r.json["dates"]
        assert "2026-11-01" in r.json["dates"]
        assert len(r.json["dates"]) >= 10
        assert "2026-10-16" in r.json["dates"]
        assert "2026-10-17" in r.json["dates"]
        assert "2026-11-17" in r.json["dates"]


class TestOverviewContract:
    def test_oct12_overview_shape_and_counts(self, api_client):
        r = api_client.get(
            "/api/cycles/current/overview?asOf=2026-10-12",
            headers=HEADERS,
        )
        assert r.status_code == 200
        body = r.json
        assert body["customer"]["name"] == "Acme Tech"
        assert body["customer"]["hrTool"] == "Workday"
        assert body["cycle"]["label"] == "October 2026"
        assert body["cycle"]["stage"] == "Inputs & review"
        assert body["asOf"] == "2026-10-12"
        assert body["statusLine"]["openActions"] == 2
        assert body["statusLine"]["countdown"] == "10 days left"
        countries = {c["country"]: c for c in body["countries"]}
        assert countries["India"]["employeeCount"] == 50
        assert countries["UK"]["employeeCount"] == 30
        assert countries["Germany"]["employeeCount"] == 22
        assert countries["Brazil"]["employeeCount"] == 18
        assert countries["Germany"]["status"] == "Action needed"
        assert countries["Brazil"]["status"] == "Action needed"
        assert countries["UK"]["status"] == "On track"
        titles = {u.get("title") for u in body["upNext"]}
        assert "Input finalisation" in titles
        assert "Review window" in titles
        assert any(u.get("href") == "/payroll/actions" for u in body["upNext"])
        assert "actions need you" in (body["statusLine"].get("message") or "")


class TestIssuesResolve:
    def test_list_open_issues_blocking_first(self, api_client):
        r = api_client.get("/api/issues?status=open", headers=HEADERS)
        assert r.status_code == 200
        ids = [i["id"] for i in r.json["issues"]]
        assert set(ids) == {"issue_001", "issue_003"}
        assert ids[0] in ("issue_001", "issue_003")  # blocking first
        assert len(ids) == 2

    def test_bank_return_appears_after_pay_not_as_missed_october_input(self, api_client):
        at_close = api_client.get("/api/issues?status=open&asOf=2026-10-15", headers=HEADERS)
        assert at_close.status_code == 200
        assert all(i["id"] != "issue_david_return" for i in at_close.json["issues"])
        later = api_client.get("/api/issues?status=open&asOf=2026-11-02", headers=HEADERS)
        assert later.status_code == 200
        david = next(i for i in later.json["issues"] if i["id"] == "issue_david_return")
        lena = next(i for i in later.json["issues"] if i["id"] == "issue_001")
        assert david["carriedOver"] is False
        assert "30 Oct" in david["detail"]
        assert "Missed October pay" not in david["detail"]
        assert lena["carriedOver"] is True
        assert lena["detail"] == "Missed October pay. November pay at risk."

    def test_bank_return_leaves_action_needed_when_account_is_added(self, api_client):
        before = api_client.get("/api/issues?status=open&asOf=2026-11-12", headers=HEADERS)
        assert any(i["id"] == "issue_david_return" for i in before.json["issues"])
        saved = api_client.post(
            "/api/issues/issue_david_return/resolve",
            headers=JSON_HEADERS,
            json={
                "resolution": "add_details",
                "payload": {"fields": {"Bank account": "123456789012"}},
                "actor": "HR admin",
                "asOf": "2026-11-12",
            },
        )
        assert saved.status_code == 200, saved.get_json()
        assert saved.json["issue"]["status"] == "resolved"
        assert saved.json.get("partial") is not True
        after = api_client.get("/api/issues?status=open&asOf=2026-11-12", headers=HEADERS)
        assert all(i["id"] != "issue_david_return" for i in after.json["issues"])
        earlier = api_client.get("/api/issues?status=open&asOf=2026-10-30", headers=HEADERS)
        assert any(i["id"] == "issue_david_return" for i in earlier.json["issues"])

    def test_resolve_lena_drops_count_germany_on_track(self, api_client):
        r = api_client.post(
            "/api/issues/issue_001/resolve",
            headers=JSON_HEADERS,
            json={
                "resolution": "add_here",
                "payload": {"taxId": "12345678903"},
                "actor": "HR admin",
                "asOf": "2026-10-12",
            },
        )
        assert r.status_code == 200
        assert r.json["issue"]["status"] == "resolved"
        assert r.json["overview"]["statusLine"]["openActions"] == 1
        de = next(
            c for c in r.json["overview"]["countries"] if c["country"] == "Germany"
        )
        assert de["status"] == "On track"

    def test_confirm_james_keeps_september_pay(self, api_client):
        before = api_client.get(
            "/api/employees/emp_james?asOf=2026-10-12", headers=HEADERS
        )
        assert before.status_code == 200
        sept_before = before.json["septemberPay"]
        assert sept_before == 4000
        r = api_client.post(
            "/api/issues/issue_002/resolve",
            headers=JSON_HEADERS,
            json={"resolution": "confirm", "actor": "HR admin", "asOf": "2026-10-12"},
        )
        assert r.status_code == 200
        after = api_client.get("/api/employees/emp_james", headers=HEADERS)
        assert after.json["septemberPay"] == sept_before == 4000

    def test_fix_in_workday_not_built(self, api_client):
        r = api_client.post(
            "/api/issues/issue_001/resolve",
            headers=JSON_HEADERS,
            json={"resolution": "fix_in_workday", "asOf": "2026-10-12"},
        )
        assert r.status_code == 501


class TestSignoffGate:
    def test_signoff_409_while_lines_unapproved(self, api_client):
        r = api_client.post(
            "/api/review/signoff",
            headers=JSON_HEADERS,
            json={"asOf": "2026-10-22"},
        )
        assert r.status_code == 409
        assert "Approve" in r.json["detail"]

    def test_signoff_200_after_all_lines_approved(self, api_client):
        rev = api_client.get("/api/review?asOf=2026-10-22", headers=HEADERS)
        for line in rev.json["lines"]:
            api_client.post(
                f"/api/review/{line['id']}/approve",
                headers=JSON_HEADERS,
                json={"asOf": "2026-10-22"},
            )
        r = api_client.post(
            "/api/review/signoff",
            headers=JSON_HEADERS,
            json={"asOf": "2026-10-22"},
        )
        assert r.status_code == 200
        assert r.json.get("signedOff") is True or r.json.get("approved") is True or "sign" in str(r.json).lower()


class TestReviewAndEmployees:
    def test_review_closed_before_window(self, api_client):
        r = api_client.get("/api/review?asOf=2026-10-14", headers=HEADERS)
        assert r.status_code == 200
        assert r.json["windowState"] == "open"
        assert r.json["available"] is True
        assert r.json["lines"]

    def test_review_open_with_totals(self, api_client):
        r = api_client.get("/api/review?asOf=2026-10-17", headers=HEADERS)
        assert r.status_code == 200
        assert r.json["windowState"] == "open"
        assert r.json["available"] is True
        assert r.json["changedLines"] == 38
        assert r.json["matchedLines"] == 32
        assert r.json["needsHumanCheck"] == 6
        assert len(r.json["lines"]) == 6
        assert r.json["changedLines"] == r.json["matchedLines"] + r.json["needsHumanCheck"]

    def test_salary_saved_from_profile_stays_approved_and_matched(self, api_client):
        before = api_client.get("/api/employees/emp_james?asOf=2026-10-17", headers=HEADERS)
        snapshot = before.json["payrollSnapshot"]["baseSalary"]
        saved = api_client.patch(
            "/api/employees/emp_james",
            headers=JSON_HEADERS,
            json={"asOf": "2026-10-17", "baseSalary": 12000, "confirmAiCheck": True},
        )
        assert saved.status_code == 200, saved.get_json()
        assert saved.json["saveMessage"] == "Saved in HR tool"
        held = api_client.get("/api/employees/emp_james?asOf=2026-10-17", headers=HEADERS)
        assert held.json["payrollSnapshot"]["baseSalary"] == snapshot
        synced = api_client.post(
            "/api/sync?asOf=2026-10-17",
            headers=JSON_HEADERS,
            json={"trigger": "Manual"},
        )
        assert synced.status_code == 200
        review = api_client.get("/api/review?asOf=2026-10-17", headers=HEADERS)
        body = review.json
        assert body["changedLines"] == body["matchedLines"] + body["needsHumanCheck"]
        james = next(line for line in body["lines"] if line["employeeId"] == "emp_james")
        assert james["id"] == "rev_001"
        assert james["approved"] is False
        assert len(body["lines"]) == 6

    def test_unapproved_lines_carry_as_arrear_or_deductible(self, api_client):
        r = api_client.get("/api/review?asOf=2026-10-17", headers=HEADERS)
        block = r.json["ifUnapproved"]
        assert block["settled"] is False
        headline = block["headline"].lower()
        assert "previous pay" in headline
        assert "arrear" in headline
        assert "deductible" in headline
        by_id = {item["employeeId"]: item for item in block["items"]}
        assert by_id["emp_james"]["kind"] == "arrears"
        assert by_id["emp_james"]["difference"] == "£8,000"
        assert "arrear" in by_id["emp_james"]["note"]
        assert by_id["emp_chloe"]["kind"] == "recovery"
        assert by_id["emp_chloe"]["kindLabel"] == "deductible"
        assert by_id["emp_chloe"]["difference"] == "£1,450"
        james = next(line for line in r.json["lines"] if line["employeeId"] == "emp_james")
        assert "£8,000" in james["carryNote"]
        assert "arrear" in james["carryNote"]

    def test_approved_line_does_not_carry_next_cycle(self, api_client):
        rev = api_client.get("/api/review?asOf=2026-10-20", headers=HEADERS)
        james = next(line for line in rev.json["lines"] if line["employeeId"] == "emp_james")
        approved = api_client.post(
            f"/api/review/{james['id']}/approve",
            headers=JSON_HEADERS,
            json={"asOf": "2026-10-20"},
        )
        assert approved.status_code == 200
        ids = {item["employeeId"] for item in approved.json["ifUnapproved"]["items"]}
        assert "emp_james" not in ids
        assert "emp_chloe" in ids
        assert approved.json["changedLines"] == 38
        assert approved.json["matchedLines"] == 33
        assert approved.json["needsHumanCheck"] == 5
        assert approved.json["remaining"] == 5
        assert approved.json["changedLines"] == approved.json["matchedLines"] + approved.json["needsHumanCheck"]
        november = api_client.get("/api/review?asOf=2026-11-17", headers=HEADERS)
        carry = {
            line["employeeId"]
            for line in november.json["lines"]
            if line.get("origin") == "october_carry"
        }
        assert "emp_james" not in carry
        assert "emp_chloe" in carry

    def test_review_counts_and_carry_follow_pay_not_a_fixed_list(self, api_client):
        """Editing pay changes the warning amount. Undo puts the line back in Need your check."""
        before = api_client.get("/api/review?asOf=2026-10-17", headers=HEADERS)
        chloe = next(line for line in before.json["lines"] if line["employeeId"] == "emp_chloe")
        assert "£1,450" in chloe["carryNote"]
        saved = api_client.patch(
            "/api/employees/emp_chloe",
            headers=JSON_HEADERS,
            json={"asOf": "2026-10-17", "baseSalary": 3000, "confirmAiCheck": True},
        )
        assert saved.status_code == 200, saved.get_json()
        synced = api_client.post(
            "/api/sync?asOf=2026-10-17",
            headers=JSON_HEADERS,
            json={"trigger": "Manual"},
        )
        assert synced.status_code == 200, synced.get_json()
        undone = api_client.post(
            f"/api/review/{chloe['id']}/unapprove",
            headers=JSON_HEADERS,
            json={"asOf": "2026-10-17"},
        )
        assert undone.status_code == 200
        body = undone.json
        assert body["changedLines"] == 38
        assert body["matchedLines"] == 32
        assert body["needsHumanCheck"] == 6
        assert body["remaining"] == 6
        item = next(row for row in body["ifUnapproved"]["items"] if row["employeeId"] == "emp_chloe")
        assert item["difference"] == "£600"
        assert "£1,450" not in item["note"]
        november = api_client.get("/api/review?asOf=2026-11-17", headers=HEADERS)
        carry = next(
            line
            for line in november.json["lines"]
            if line["employeeId"] == "emp_chloe" and line.get("origin") == "october_carry"
        )
        assert "£600" in carry["changeSummary"]
        assert "£1,450" not in carry["changeSummary"]

    def test_next_cycle_shows_unapproved_differences(self, api_client):
        early = api_client.get("/api/review?asOf=2026-11-01", headers=HEADERS)
        assert early.status_code == 200
        assert early.json["windowState"] == "open"
        block = early.json["ifUnapproved"]
        assert block["settled"] is True
        assert "previous pay was deposited" in block["headline"].lower()
        ids = {item["employeeId"] for item in block["items"]}
        assert ids == {
            "emp_james",
            "emp_ananya",
            "emp_rajesh",
            "emp_thiago",
            "emp_chloe",
            "emp_mateo",
        }
        chloe = next(item for item in block["items"] if item["employeeId"] == "emp_chloe")
        assert chloe["kindLabel"] == "deductible"
        assert "£1,450" in chloe["note"]
        opened = api_client.get("/api/review?asOf=2026-11-17", headers=HEADERS)
        assert opened.json["windowState"] == "open"
        by_emp = {
            line["employeeId"]: line
            for line in opened.json["lines"]
            if line.get("origin") == "october_carry"
        }
        assert "Arrears" in by_emp["emp_james"]["changeSummary"]
        assert "£8,000" in by_emp["emp_james"]["changeSummary"]
        assert "Deductible" in by_emp["emp_chloe"]["changeSummary"]
        assert "not signed off" in by_emp["emp_chloe"]["whyFlagged"].lower()

    def test_signed_off_payroll_does_not_carry(self, api_client):
        rev = api_client.get("/api/review?asOf=2026-10-22", headers=HEADERS)
        for line in rev.json["lines"]:
            api_client.post(
                f"/api/review/{line['id']}/approve",
                headers=JSON_HEADERS,
                json={"asOf": "2026-10-22"},
            )
        signed = api_client.post(
            "/api/review/signoff",
            headers=JSON_HEADERS,
            json={"asOf": "2026-10-22"},
        )
        assert signed.status_code == 200
        early = api_client.get("/api/review?asOf=2026-11-01", headers=HEADERS)
        assert not (early.json.get("ifUnapproved") or {}).get("items")

    def test_employees_count_120(self, api_client):
        r = api_client.get("/api/employees?asOf=2026-10-12", headers=HEADERS)
        assert r.status_code == 200
        assert r.json["count"] == 120

    def test_hr_list_is_the_offer_record_not_pay_analysis(self, api_client):
        r = api_client.get("/api/employees?asOf=2026-10-12&page=1&pageSize=100", headers=HEADERS)
        by_id = {row["id"]: row for row in r.json["employees"]}
        ananya = by_id["emp_ananya"]["hrRecord"]
        assert ananya["basePay"] == 135000
        assert ananya["identity"]["field"] == "PAN"
        assert ananya["identity"]["state"] == "on_file"
        assert ananya["aadhaar"]["state"] == "not_recorded"
        assert ananya["bank"]["field"] == "Bank account"
        assert ananya["bank"]["state"] == "on_file"
        assert ananya["insurance"] == "not_added"
        assert ananya["employeeAdds"] == []
        assert "Manager" in ananya["other"]
        lena = by_id["emp_lena"]["hrRecord"]
        assert lena["identity"]["field"] == "Tax ID"
        assert lena["identity"]["state"] == "missing"
        assert lena["identity"]["owner"] == "employee"
        assert lena["employeeAdds"] == [{"field": "Tax ID", "owner": "employee"}]
        assert lena["aadhaar"]["state"] == "not_used"
        beatriz = by_id["emp_beatriz"]["hrRecord"]
        assert beatriz["identity"]["field"] == "CPF"
        assert beatriz["identity"]["state"] == "missing"


class TestNotificationsAndDocuments:
    def test_oct12_one_email_three_actions(self, api_client):
        r = api_client.get(
            "/api/notifications?asOf=2026-10-20", headers=HEADERS
        )
        assert r.status_code == 200
        n = next(item for item in r.json["notifications"] if item["subject"] == "2 days left to add inputs and finish review")
        assert n["actionCount"] == 2
        detail = api_client.get(
            f"/api/notifications/{n['id']}?asOf=2026-10-20", headers=HEADERS
        )
        assert detail.status_code == 200
        assert "new employees, salary changes, and bonuses" in detail.json["bodySummary"]
        assert "finish review" in detail.json["bodySummary"]
        assert detail.json["cta"]["href"] == "/payroll/actions"
        assert len(detail.json["actions"]) == 2
        assert detail.json["actions"][0]["actionText"] == "Resolve actions in Action needed"
        assert detail.json["actions"][1]["actionText"] == "Finish review"

    def test_cutoff_tomorrow_counts_every_open_action(self, api_client):
        r = api_client.get("/api/notifications?asOf=2026-10-22", headers=HEADERS)
        notes = r.json["notifications"]
        cutoff = next(n for n in notes if n["subject"] == "Last day to add inputs and finish review")
        assert cutoff["actionCount"] == 2
        detail = api_client.get(f"/api/notifications/{cutoff['id']}?asOf=2026-10-22", headers=HEADERS)
        body = detail.json["bodySummary"]
        assert "22 October" in body
        assert "new employees, salary changes, and bonuses" in body
        assert "finish review" in body
        assert "next cycle" in body
        assert detail.json["policy"]["href"] == "/payroll/input-policy"
        assert detail.json["policy"]["note"] == "Demo"
        assert len(detail.json["actions"]) == 2
        action = detail.json["actions"][0]
        assert action["actionText"] == "Resolve actions in Action needed"
        assert action["href"] == "/payroll/actions"
        assert detail.json["actions"][1]["href"] == "/payroll/review"
        assert "Salary up 3x" not in action["actionText"]

    def test_document_fixtures(self, api_client):
        r = api_client.get("/api/documents/fixtures", headers=HEADERS)
        names = {f["filename"] for f in r.json["fixtures"]}
        assert "offer_letter_priya.pdf" in names
        assert "bonus_letter_james.pdf" in names


class TestJoinerJourney:
    def test_create_priya_creates_issue_004(self, api_client):
        created = api_client.post(
            "/api/employees",
            headers=JSON_HEADERS,
            json={
                "name": "Priya Nair",
                "country": "India",
                "role": "Software Engineer",
                "workEmail": "priya.nair@acmetech.example",
                "asOf": "2026-10-13",
            },
        )
        assert created.status_code == 201
        eid = created.json["id"]
        assert created.json["isNew"] is True
        assert created.json["dateAdded"] == "2026-10-13"
        missing = created.json["missingFields"]
        assert "PAN" in missing
        assert "Bank account" in missing
        assert "Manager" in missing
        assert created.json["payTiming"]["level"] == "amber"

        issues = api_client.get(
            "/api/issues?status=open&asOf=2026-10-13", headers=HEADERS
        )
        ids = {i["id"] for i in issues.json["issues"]}
        assert "issue_004" in ids

        attached = api_client.post(
            f"/api/employees/{eid}/documents",
            headers=JSON_HEADERS,
            json={"fixture": "offer_letter_priya.pdf", "asOf": "2026-10-13"},
        )
        assert attached.status_code == 200
        assert attached.json["payTiming"]["level"] == "amber"
        assert any(m["status"] == "missing" for m in attached.json["mappings"])

    def test_hr_manager_does_not_resolve_employee_fields(self, api_client):
        created = api_client.post(
            "/api/employees",
            headers=JSON_HEADERS,
            json={
                "name": "Sofia Mendes",
                "country": "India",
                "role": "Designer",
                "workEmail": "sofia.mendes@acmetech.example",
                "asOf": "2026-10-13",
            },
        )
        assert created.status_code == 201
        issues = api_client.get(
            "/api/issues?status=open&asOf=2026-10-13", headers=HEADERS
        ).json["issues"]
        issue = next(i for i in issues if i["employeeId"] == created.json["id"])
        saved = api_client.post(
            f"/api/issues/{issue['id']}/resolve",
            headers=JSON_HEADERS,
            json={
                "resolution": "add_details",
                "asOf": "2026-10-13",
                "payload": {"fields": {"Manager": "Shilpa"}},
            },
        )
        assert saved.status_code == 200, saved.json
        assert saved.json["partial"] is True
        assert saved.json["issue"]["status"] == "open"
        assert "Manager" not in saved.json["issue"]["missingFields"]
        assert "PAN" in saved.json["issue"]["missingFields"]
        assert "Bank account" in saved.json["issue"]["missingFields"]
        assert "Manager" not in saved.json["issue"]["title"]

    def test_manager_does_not_hold_pay(self, api_client):
        created = api_client.post(
            "/api/employees",
            headers=JSON_HEADERS,
            json={
                "name": "Sofia Mendes",
                "country": "India",
                "role": "Designer",
                "workEmail": "sofia.pay@acmetech.example",
                "asOf": "2026-10-13",
            },
        )
        assert created.status_code == 201, created.json
        eid = created.json["id"]
        assert "Manager" in created.json["missingFields"]
        assert "Manager" not in created.json["paymentMissingFields"]
        assert "PAN" in created.json["paymentMissingFields"]
        assert "Manager" not in created.json["payTiming"]["message"]

        filled = api_client.post(
            f"/api/employees/{eid}/missing-fields",
            headers=JSON_HEADERS,
            json={
                "asOf": "2026-10-13",
                "fields": {
                    "PAN": "ABCDE1234F",
                    "Bank account": "123456789012",
                    "IFSC": "HDFC0000123",
                },
            },
        )
        assert filled.status_code == 200, filled.json
        assert filled.json["missingFields"] == ["Manager"]
        assert filled.json["paymentMissingFields"] == []
        assert filled.json["payTiming"]["level"] == "green"

        notes = api_client.get(
            "/api/notifications?asOf=2026-10-13&channel=email", headers=HEADERS
        ).json["notifications"]
        assert not any(
            n.get("kind") == "details_confirmed" and "Sofia Mendes" in (n.get("subject") or "")
            for n in notes
        )

        issues = api_client.get(
            "/api/issues?status=open&asOf=2026-10-13", headers=HEADERS
        ).json["issues"]
        issue = next(i for i in issues if i["employeeId"] == eid)
        assert issue["status"] == "open"
        assert "Manager" in issue["title"]
        assert issue["severity"] != "blocking"
        assert "does not hold" in issue["impact"]

    def test_create_same_email_twice_returns_existing(self, api_client):
        body = {
            "name": "Priya Nair",
            "country": "India",
            "workEmail": "priya.nair@acmetech.example",
            "asOf": "2026-10-13",
        }
        first = api_client.post("/api/employees", headers=JSON_HEADERS, json=body)
        assert first.status_code == 201
        second = api_client.post(
            "/api/employees",
            headers=JSON_HEADERS,
            json={**body, "workEmail": "PRIYA.NAIR@acmetech.example", "manager": "Ananya Rao"},
        )
        assert second.status_code == 200
        assert second.json["id"] == first.json["id"]
        listed = api_client.get("/api/employees?asOf=2026-10-13", headers=HEADERS)
        assert listed.json["count"] == 121

    def test_joiner_hidden_before_date_added(self, api_client):
        created = api_client.post(
            "/api/employees",
            headers=JSON_HEADERS,
            json={"name": "Arjun Mehta", "country": "India", "asOf": "2026-10-17"},
        )
        eid = created.json["id"]
        before = api_client.get("/api/employees?asOf=2026-10-12", headers=HEADERS)
        assert before.json["count"] == 120
        assert eid not in {e["id"] for e in before.json["employees"]}
        after = api_client.get("/api/employees?asOf=2026-10-17", headers=HEADERS)
        assert after.json["count"] == 121
        detail = api_client.get(f"/api/employees/{eid}?asOf=2026-10-12", headers=HEADERS)
        assert detail.status_code == 200


class TestAsOfIssueVisibility:
    def test_issue_resolved_later_is_open_when_viewed_earlier(self, api_client):
        r = api_client.post(
            "/api/issues/issue_001/resolve",
            headers=JSON_HEADERS,
            json={"resolution": "add_here", "payload": {"taxId": "12345678903"}, "asOf": "2026-10-13"},
        )
        assert r.status_code == 200
        assert r.json["overview"]["statusLine"]["openActions"] == 1

        earlier = api_client.get("/api/issues?status=open&asOf=2026-10-12", headers=HEADERS)
        assert "issue_001" in {i["id"] for i in earlier.json["issues"]}
        ov12 = api_client.get(
            "/api/cycles/current/overview?asOf=2026-10-12", headers=HEADERS
        )
        assert ov12.json["statusLine"]["openActions"] == 2
        one = api_client.get("/api/issues/issue_001?asOf=2026-10-12", headers=HEADERS)
        assert one.json["status"] == "open"
        assert one.json["resolvedAt"] is None

        later = api_client.get("/api/issues/issue_001?asOf=2026-10-13", headers=HEADERS)
        assert later.json["status"] == "resolved"
        assert later.json["resolvedAt"] == "2026-10-13"

    def test_signoff_requires_line_approvals(self, api_client):
        api_client.post(
            "/api/issues/issue_001/resolve",
            headers=JSON_HEADERS,
            json={"resolution": "add_here", "payload": {"taxId": "12345678903"}, "asOf": "2026-10-22"},
        )
        gated = api_client.post(
            "/api/review/signoff", headers=JSON_HEADERS, json={"asOf": "2026-10-22"}
        )
        assert gated.status_code == 409


def test_chloe_profile_shows_maternity_deductible(api_client):
    res = api_client.get("/api/employees/emp_chloe?asOf=2026-10-17", headers=HEADERS)
    assert res.status_code == 200, res.json
    cut = res.json["payAdjustment"]
    assert cut["whyFlagged"] == "Maternity leave: statutory pay"
    assert cut["matchingSource"] == "HMRC rate table"
    assert cut["changeSummary"] == "£3,600 → £2,150"
    assert cut["amount"] == 1450
    assert cut["llmDecision"]["reason"]
