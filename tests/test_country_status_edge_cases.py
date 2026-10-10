"""Edge cases: country chip derivation from open issues."""

from __future__ import annotations

from domain.country_status import country_status, country_statuses
from domain.issues import resolve_issue


class TestBaselineOct12:
    def test_germany_action_needed_from_blocking(self, baseline_issues):
        assert country_status("Germany", baseline_issues) == "Action needed"

    def test_uk_action_needed_from_confirmation(self, baseline_issues):
        assert country_status("UK", baseline_issues) == "Action needed"

    def test_brazil_action_needed_from_beatriz_cpf(self, baseline_issues):
        assert country_status("Brazil", baseline_issues) == "Action needed"

    def test_india_on_track_before_priya(self, baseline_issues):
        """Priya's issue only appears after she is added on Oct 13."""
        assert country_status("India", baseline_issues) == "On track"

    def test_all_four_countries_present(self, baseline_issues):
        statuses = country_statuses(baseline_issues)
        assert set(statuses) == {"India", "UK", "Germany", "Brazil"}


class TestTransitions:
    def test_fix_lena_turns_germany_on_track(self, baseline_issues):
        after = resolve_issue(baseline_issues, "issue_001")
        assert country_status("Germany", after) == "On track"

    def test_fix_james_turns_uk_on_track(self, baseline_issues):
        after = resolve_issue(baseline_issues, "issue_002")
        assert country_status("UK", after) == "On track"

    def test_deadline_risk_beats_blocking_same_country(self):
        issues = [
            {
                "id": "1",
                "country": "Germany",
                "severity": "blocking",
                "status": "open",
            },
            {
                "id": "2",
                "country": "Germany",
                "severity": "deadline_risk",
                "status": "open",
            },
        ]
        assert country_status("Germany", issues) == "Deadline risk"

    def test_resolved_issues_ignored(self):
        issues = [
            {
                "id": "1",
                "country": "Germany",
                "severity": "blocking",
                "status": "resolved",
            }
        ]
        assert country_status("Germany", issues) == "On track"

    def test_other_country_issue_does_not_pollute(self, baseline_issues):
        # UK issues must not change Germany after Lena fixed
        after = resolve_issue(baseline_issues, "issue_001")
        assert country_status("Germany", after) == "On track"
        assert country_status("UK", after) == "Action needed"


class TestEmptyAndUnknown:
    def test_no_issues_all_on_track(self):
        assert country_statuses([]) == {
            "India": "On track",
            "UK": "On track",
            "Germany": "On track",
            "Brazil": "On track",
        }

    def test_unknown_country_with_no_issues_on_track(self):
        assert country_status("Philippines", []) == "On track"
