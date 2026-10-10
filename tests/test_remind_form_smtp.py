"""Remind employee + signed form token (round 2 §8 / §14.7)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "data" / "seed_db.py"

sys.path.insert(0, str(ROOT))


@pytest.fixture()
def api_client(tmp_path, monkeypatch):
    db = tmp_path / "payroll_clarity.db"
    subprocess.check_call(
        [sys.executable, str(SEED), "--db", str(db), "--seed", "42"],
        cwd=str(ROOT),
    )
    monkeypatch.delenv("SMTP_USER", raising=False)
    monkeypatch.delenv("SMTP_PASS", raising=False)
    monkeypatch.delenv("DEMO_INBOX", raising=False)
    monkeypatch.setenv("APP_BASE_URL", "http://localhost:5173")
    monkeypatch.setenv("FORM_TOKEN_SECRET", "test-secret")

    from server.db.connection import set_db_path
    from server.app import create_app
    from server.services import env_config

    env_config._LOADED = False  # noqa: SLF001 — re-read env after monkeypatch
    set_db_path(db)
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


HEADERS = {"X-Customer-Id": "cust_acme", "Content-Type": "application/json"}


class TestRemindWithoutSmtp:
    def test_lena_remind_saves_notification_and_form_link(self, api_client):
        r = api_client.post(
            "/api/issues/issue_001/remind",
            headers=HEADERS,
            json={"asOf": "2026-10-12"},
        )
        assert r.status_code == 200
        body = r.json
        assert body["emailSent"] is False
        assert "SMTP not set up" in body["message"]
        assert body["formPath"].startswith("/form/f-")
        assert body["issue"]["reminderLabel"].startswith("Reminder emailed Oct 12")
        assert "waiting for Lena" in body["issue"]["reminderLabel"]

        n = api_client.get(
            f"/api/notifications/{body['notificationId']}?asOf=2026-10-12",
            headers={"X-Customer-Id": "cust_acme"},
        )
        assert n.status_code == 200
        assert n.json["cta"]["label"] in ("Add my details", "Add my details →")
        assert n.json["cta"]["href"].startswith("/people/")
        assert n.json["cta"]["href"].endswith("?panel=missing")
        # SMTP status is not inside the employee-facing email body
        assert "SMTP not set up" not in (n.json.get("bodySummary") or "")
        assert "add your details here" in (n.json.get("bodySummary") or "").lower()
        assert n.json.get("kind") == "employee_reminder_undelivered"

    def test_form_submit_resolves_and_notifies_hr(self, api_client):
        remind = api_client.post(
            "/api/issues/issue_001/remind",
            headers=HEADERS,
            json={"asOf": "2026-10-12"},
        )
        token = remind.json["formPath"].split("/form/", 1)[1]
        got = api_client.get(
            f"/api/forms/{token}",
            headers={"X-Customer-Id": "cust_acme"},
            query_string={"asOf": "2026-10-12"},
        )
        assert got.status_code == 200
        assert got.json["fields"] == ["Tax ID"]

        submitted = api_client.post(
            f"/api/forms/{token}",
            headers=HEADERS,
            json={"asOf": "2026-10-12", "fields": {"Tax ID": "12345678903"}},
        )
        assert submitted.status_code == 200
        assert "Lena submitted" in submitted.json["message"]

        issue = api_client.get(
            "/api/issues/issue_001?asOf=2026-10-12",
            headers={"X-Customer-Id": "cust_acme"},
        )
        assert issue.json["status"] == "resolved"

        reused = api_client.get(
            f"/api/forms/{token}",
            headers={"X-Customer-Id": "cust_acme"},
            query_string={"asOf": "2026-10-12"},
        )
        assert reused.status_code == 410

        inbox = api_client.get(
            "/api/notifications?asOf=2026-10-12",
            headers={"X-Customer-Id": "cust_acme"},
        )
        subjects = [n["subject"] for n in inbox.json["notifications"]]
        assert any("Lena added" in s and "Tax ID" in s for s in subjects)
