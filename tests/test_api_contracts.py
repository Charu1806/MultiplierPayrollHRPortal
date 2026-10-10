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
        assert body["cycle"]["stage"] == "Input finalisation"
        assert body["asOf"] == "2026-10-12"
        assert body["statusLine"]["openActions"] == 3
        assert body["statusLine"]["countdown"] == "3 days left"
        countries = {c["country"]: c for c in body["countries"]}
        assert countries["India"]["employeeCount"] == 50
        assert countries["UK"]["employeeCount"] == 30
        assert countries["Germany"]["employeeCount"] == 22
        assert countries["Brazil"]["employeeCount"] == 18
        assert countries["Germany"]["status"] == "Action needed"
        assert countries["Brazil"]["status"] == "Action needed"
        assert countries["UK"]["status"] == "Action needed"
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
        assert set(ids) == {"issue_001", "issue_002", "issue_003"}
        assert ids[0] in ("issue_001", "issue_003")  # blocking first
        assert len(ids) == 3

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
        assert r.json["overview"]["statusLine"]["openActions"] == 2
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
        assert r.json["windowState"] == "before"
        assert r.json["available"] is False
        assert r.json["lines"] == []

    def test_review_open_with_totals(self, api_client):
        r = api_client.get("/api/review?asOf=2026-10-17", headers=HEADERS)
        assert r.status_code == 200
        assert r.json["windowState"] == "open"
        assert r.json["available"] is True
        assert r.json["changedLines"] == 38
        assert r.json["matchedLines"] == 32
        assert r.json["needsHumanCheck"] == 6
        assert len(r.json["lines"]) == 6

    def test_employees_count_120(self, api_client):
        r = api_client.get("/api/employees?asOf=2026-10-12", headers=HEADERS)
        assert r.status_code == 200
        assert r.json["count"] == 120


class TestNotificationsAndDocuments:
    def test_oct12_one_email_three_actions(self, api_client):
        r = api_client.get(
            "/api/notifications?asOf=2026-10-12", headers=HEADERS
        )
        assert r.status_code == 200
        assert len(r.json["notifications"]) == 1
        n = r.json["notifications"][0]
        assert n["actionCount"] == 3
        assert "3 actions" in n["subject"]
        detail = api_client.get(
            f"/api/notifications/{n['id']}", headers=HEADERS
        )
        assert detail.status_code == 200
        assert detail.json["cta"]["href"] in ("/payroll/overview", "/payroll/actions")

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
        assert r.json["overview"]["statusLine"]["openActions"] == 2

        earlier = api_client.get("/api/issues?status=open&asOf=2026-10-12", headers=HEADERS)
        assert "issue_001" in {i["id"] for i in earlier.json["issues"]}
        ov12 = api_client.get(
            "/api/cycles/current/overview?asOf=2026-10-12", headers=HEADERS
        )
        assert ov12.json["statusLine"]["openActions"] == 3
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
