"""Edge cases: severity sort, resolve, owners, hold scope (round 1)."""

from __future__ import annotations

from domain.issues import (
    can_approve,
    held_employee_ids,
    open_issues,
    resolve_issue,
    severity_rank,
    sort_issues,
)


class TestSeverityRank:
    def test_blocking_before_deadline_risk(self):
        assert severity_rank("blocking") < severity_rank("deadline_risk")

    def test_deadline_before_confirmation(self):
        assert severity_rank("deadline_risk") < severity_rank("needs_confirmation")

    def test_unknown_severity_last(self):
        assert severity_rank("weird") > severity_rank("next_cycle")


class TestSortIssues:
    def test_blocking_first_even_if_later_deadline(self, baseline_issues):
        shuffled = list(reversed(baseline_issues))
        ordered = sort_issues(shuffled)
        assert ordered[0]["severity"] == "blocking"
        assert ordered[0]["id"] in ("issue_001", "issue_003")

    def test_same_severity_sorted_by_deadline_then_title(self):
        issues = [
            {
                "id": "b",
                "severity": "deadline_risk",
                "deadline": "2026-10-15",
                "title": "Zulu",
                "status": "open",
            },
            {
                "id": "a",
                "severity": "deadline_risk",
                "deadline": "2026-10-14",
                "title": "Alpha",
                "status": "open",
            },
            {
                "id": "c",
                "severity": "deadline_risk",
                "deadline": "2026-10-15",
                "title": "Alpha",
                "status": "open",
            },
        ]
        ordered = sort_issues(issues)
        assert [i["id"] for i in ordered] == ["a", "c", "b"]

    def test_sort_stable_on_empty(self):
        assert sort_issues([]) == []


class TestOpenAndResolve:
    def test_open_issues_filters_resolved(self, baseline_issues):
        mutated = resolve_issue(baseline_issues, "issue_001")
        assert len(open_issues(mutated)) == 2
        assert all(i["id"] != "issue_001" or i["status"] == "resolved" for i in mutated)

    def test_resolve_unknown_id_noop(self, baseline_issues):
        out = resolve_issue(baseline_issues, "issue_999")
        assert len(open_issues(out)) == 3

    def test_resolve_already_resolved_idempotent(self, baseline_issues):
        once = resolve_issue(baseline_issues, "issue_001", log="first")
        twice = resolve_issue(once, "issue_001", log="second")
        row = next(i for i in twice if i["id"] == "issue_001")
        assert row["status"] == "resolved"
        assert row["resolution_log"] == "first"

    def test_confirmation_log_for_james(self, baseline_issues):
        out = resolve_issue(
            baseline_issues,
            "issue_002",
            resolved_by="HR admin",
            resolved_at="2026-10-12",
            log="Confirmed by HR admin, Oct 12",
        )
        row = next(i for i in out if i["id"] == "issue_002")
        assert "Confirmed by HR admin" in row["resolution_log"]


class TestOwners:
    def test_one_owner_per_baseline_issue(self, baseline_issues):
        for i in baseline_issues:
            assert i["owner"] in {"HR admin", "Finance"}

    def test_beatriz_cpf_owned_by_hr_admin(self, baseline_issues):
        brazil = next(i for i in baseline_issues if i["id"] == "issue_003")
        assert brazil["owner"] == "HR admin"


class TestHoldScope:
    def test_lena_and_beatriz_held_by_blocking(self, baseline_issues):
        held = held_employee_ids(baseline_issues)
        assert held == {"emp_lena", "emp_beatriz"}

    def test_resolving_lena_leaves_beatriz_held(self, baseline_issues):
        after = resolve_issue(baseline_issues, "issue_001")
        assert held_employee_ids(after) == {"emp_beatriz"}

    def test_resolving_both_blocking_clears_hold(self, baseline_issues):
        after = resolve_issue(baseline_issues, "issue_001")
        after = resolve_issue(after, "issue_003")
        assert held_employee_ids(after) == set()

    def test_non_blocking_never_adds_to_held(self, baseline_issues):
        held = held_employee_ids(baseline_issues)
        assert "emp_james" not in held

    def test_named_employees_only_never_hold_all(self, baseline_issues):
        held = held_employee_ids(baseline_issues)
        assert None not in held
        assert "" not in held
        assert len(held) == 2


class TestApproveGate:
    def test_cannot_approve_with_blocking_open(self, baseline_issues):
        assert can_approve(baseline_issues) is False

    def test_can_approve_after_both_blocking_resolved_even_if_others_open(
        self, baseline_issues
    ):
        after = resolve_issue(baseline_issues, "issue_001")
        after = resolve_issue(after, "issue_003")
        assert can_approve(after) is True

    def test_empty_issues_can_approve(self):
        assert can_approve([]) is True

    def test_only_needs_confirmation_open_can_approve(self):
        issues = [
            {
                "id": "x",
                "severity": "needs_confirmation",
                "status": "open",
                "employee_id": "emp_james",
            }
        ]
        assert can_approve(issues) is True
