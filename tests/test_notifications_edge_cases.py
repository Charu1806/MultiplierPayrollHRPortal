"""Edge cases: email visibility by prototype date and grouping rules (round 1)."""

from __future__ import annotations

from domain.notifications import (
    emails_visible_on,
    filter_channel,
    groups_issues_not_per_item_buttons,
)


class TestVisibilityByDate:
    def test_oct12_shows_only_first_email(self, baseline_emails):
        visible = emails_visible_on(baseline_emails, "2026-10-12")
        assert len(visible) == 1
        assert visible[0]["send_date"] == "2026-10-12"

    def test_oct14_shows_two(self, baseline_emails):
        visible = emails_visible_on(baseline_emails, "2026-10-14")
        assert len(visible) == 2
        assert visible[0]["send_date"] == "2026-10-14"

    def test_oct15_shows_three(self, baseline_emails):
        assert len(emails_visible_on(baseline_emails, "2026-10-15")) == 3

    def test_oct17_includes_review_open_email(self, baseline_emails):
        visible = emails_visible_on(baseline_emails, "2026-10-17")
        assert len(visible) == 4
        assert any(e["send_date"] == "2026-10-17" for e in visible)

    def test_oct22_shows_through_finance(self, baseline_emails):
        visible = emails_visible_on(baseline_emails, "2026-10-22")
        assert len(visible) == 6
        dates = [e["send_date"] for e in visible]
        assert dates[0] == "2026-10-22"
        assert "2026-10-20" in dates
        assert "2026-10-17" in dates
        assert "2026-10-12" in dates

    def test_before_any_email_empty(self, baseline_emails):
        assert emails_visible_on(baseline_emails, "2026-10-01") == []

    def test_future_date_includes_equality_boundary(self, baseline_emails):
        visible = emails_visible_on(baseline_emails, "2026-10-20")
        assert any(e["send_date"] == "2026-10-20" for e in visible)
        assert not any(e["send_date"] == "2026-10-21" for e in visible)


class TestChannelAndGrouping:
    def test_email_channel_only(self, baseline_emails):
        slack = [
            *baseline_emails,
            {"id": "s1", "send_date": "2026-10-12", "channel": "slack", "subject": "x"},
        ]
        assert len(filter_channel(slack, "email")) == 6
        assert len(filter_channel(slack, "slack")) == 1

    def test_action_count_matches_actions_list(self):
        email = {
            "action_count": 3,
            "actions": ["a", "b", "c"],
        }
        assert groups_issues_not_per_item_buttons(email) is True

    def test_mismatched_action_count_fails_invariant(self):
        email = {"action_count": 4, "actions": ["a", "b"]}
        assert groups_issues_not_per_item_buttons(email) is False


class TestComputedNotificationsViaApi:
    """Round 1 emails are computed — assert via API, not DB rows."""

    def test_oct12_subject_three_actions(self, tmp_path):
        import subprocess
        import sys
        from pathlib import Path

        root = Path(__file__).resolve().parents[1]
        db = tmp_path / "payroll_clarity.db"
        subprocess.check_call(
            [sys.executable, str(root / "data" / "seed_db.py"), "--db", str(db), "--seed", "42"],
            cwd=str(root),
        )
        sys.path.insert(0, str(root))
        from server.db.connection import set_db_path
        from server.app import create_app

        set_db_path(db)
        app = create_app()
        app.config["TESTING"] = True
        client = app.test_client()
        r = client.get(
            "/api/notifications?asOf=2026-10-12",
            headers={"X-Customer-Id": "cust_acme"},
        )
        assert r.status_code == 200
        assert len(r.json["notifications"]) == 1
        assert "3 actions" in r.json["notifications"][0]["subject"]
        assert r.json["notifications"][0]["actionCount"] == 3

    def test_finance_funding_email_not_to_hr(self, tmp_path):
        import subprocess
        import sys
        from pathlib import Path

        root = Path(__file__).resolve().parents[1]
        db = tmp_path / "payroll_clarity.db"
        subprocess.check_call(
            [sys.executable, str(root / "data" / "seed_db.py"), "--db", str(db), "--seed", "42"],
            cwd=str(root),
        )
        sys.path.insert(0, str(root))
        from server.db.connection import set_db_path
        from server.app import create_app

        set_db_path(db)
        app = create_app()
        app.config["TESTING"] = True
        client = app.test_client()
        r = client.get(
            "/api/notifications?asOf=2026-10-22",
            headers={"X-Customer-Id": "cust_acme"},
        )
        finance = [n for n in r.json["notifications"] if n.get("recipient") == "Finance"]
        assert finance
        assert "Funding" in finance[0]["subject"]
