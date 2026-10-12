"""
End-to-end domain scenarios for the demo script (context.md, round 1).
"""

from __future__ import annotations

from domain.calendar_rules import countdown_text, stage_for_date
from domain.country_status import country_status
from domain.issues import can_approve, open_issues, resolve_issue
from domain.notifications import emails_visible_on
from domain.pay_timing import pay_timing


def test_scene1_oct12_email_then_overview_count(baseline_issues, baseline_emails):
    visible = emails_visible_on(baseline_emails, "2026-10-12")
    assert len(visible) == 1
    assert visible[0]["action_count"] == 3
    assert len(open_issues(baseline_issues)) == 3
    assert countdown_text("2026-10-12") == "10 days left"
    assert stage_for_date("2026-10-12") == "Inputs & review"


def test_scene2_fix_lena_drops_count_germany_on_track(baseline_issues):
    after = resolve_issue(baseline_issues, "issue_001")
    assert len(open_issues(after)) == 2
    assert country_status("Germany", after) == "On track"
    # Never held whole payroll: Brazil still Action needed (Beatriz CPF)
    assert country_status("Brazil", after) == "Action needed"


def test_scene3_confirm_james_leaves_beatriz(baseline_issues):
    after_lena = resolve_issue(baseline_issues, "issue_001")
    after_james = resolve_issue(
        after_lena,
        "issue_002",
        log="Confirmed by HR admin, Oct 12",
    )
    assert len(open_issues(after_james)) == 1
    assert country_status("UK", after_james) == "On track"
    assert country_status("Brazil", after_james) == "Action needed"


def test_scene4_priya_oct13_amber_missing_pan_bank():
    flag = pay_timing(
        date_added="2026-10-13",
        missing_fields=["PAN", "Bank account"],
        prototype_date="2026-10-13",
    )
    assert flag.level == "amber"
    assert "PAN" in flag.message and "bank account" in flag.message


def test_scene5_bonus_letter_fixture_amount(conn):
    sept = conn.execute(
        "SELECT september_pay, base_salary FROM employees WHERE id = 'emp_james'"
    ).fetchone()
    assert sept["september_pay"] == 4000
    assert sept["base_salary"] == 12000
    bonus = conn.execute(
        "SELECT bonus_amount FROM document_fixtures WHERE id = 'doc_james_bonus'"
    ).fetchone()[0]
    assert bonus == 8000


def test_scene6_arjun_after_cutoff_and_priya_moved():
    arjun = pay_timing(
        date_added="2026-10-23",
        missing_fields=[],
        prototype_date="2026-10-23",
    )
    assert arjun.level == "red"
    assert arjun.show_off_cycle_stub is True

    priya = pay_timing(
        date_added="2026-10-13",
        missing_fields=["PAN", "Bank account"],
        prototype_date="2026-10-23",
    )
    assert priya.message == "Moved to November · fix by Nov 22"


def test_scene7_review_totals_and_blocking_gate(conn, baseline_issues):
    n = conn.execute("SELECT COUNT(*) FROM review_lines").fetchone()[0]
    assert n == 6
    assert can_approve(baseline_issues) is False
    after = resolve_issue(baseline_issues, "issue_001")
    after = resolve_issue(after, "issue_003")
    assert can_approve(after) is True


def test_scene8_stub_invariants_documented_in_meta(conn):
    sources = conn.execute(
        "SELECT value FROM meta WHERE key = 'sources'"
    ).fetchone()[0]
    assert "context.md" in sources
    assert (
        conn.execute("SELECT value FROM meta WHERE key = 'illustrative'").fetchone()[0]
        == "true"
    )


def test_session_persistence_resolutions_survive_date_change(baseline_issues):
    """User fixes persist across prototype date changes within a session."""
    after = resolve_issue(baseline_issues, "issue_001")
    assert len(open_issues(after)) == 2
    assert stage_for_date("2026-10-22") == "Inputs & review"
