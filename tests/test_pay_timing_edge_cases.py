"""Extensive edge cases for pay timing rule (context.md §8, round 1)."""

from __future__ import annotations

import pytest

from domain.pay_timing import pay_timing


class TestOnboardedUnchanged:
    def test_null_date_added_no_missing_is_green(self):
        flag = pay_timing(date_added=None, missing_fields=[], prototype_date="2026-10-12")
        assert flag.level == "green"
        assert flag.message == "Payment on track for October"
        assert flag.show_off_cycle_stub is False

    def test_null_date_added_with_missing_before_cutoff_held(self):
        """Lena: existing employee held on tax ID (context.md wording)."""
        flag = pay_timing(
            date_added=None,
            missing_fields=["Tax ID"],
            prototype_date="2026-10-12",
        )
        assert flag.level == "red"
        assert flag.message == "Held until tax ID is added – fix by Oct 22"
        assert flag.show_off_cycle_stub is False

    def test_held_wording_keeps_acronyms(self):
        flag = pay_timing(
            date_added=None,
            missing_fields=["PAN"],
            prototype_date="2026-10-22",
        )
        assert flag.message == "Held until PAN is added – fix by Oct 22"

    def test_null_date_added_with_missing_after_cutoff_moved(self):
        flag = pay_timing(
            date_added=None,
            missing_fields=["Tax ID"],
            prototype_date="2026-10-23",
        )
        assert flag.level == "amber"
        assert flag.message == "Moved to November · fix by Nov 22"


class TestBeforeOrOnCutoffComplete:
    @pytest.mark.parametrize("added", ["2026-10-13", "2026-10-15", "2026-10-01"])
    def test_complete_data_green_october(self, added):
        flag = pay_timing(
            date_added=added,
            missing_fields=[],
            prototype_date="2026-10-14",
        )
        assert flag.level == "green"
        assert "October" in flag.message


class TestBeforeCutoffMissing:
    def test_single_missing_field_wording(self):
        flag = pay_timing(
            date_added="2026-10-13",
            missing_fields=["PAN"],
            prototype_date="2026-10-13",
        )
        assert flag.level == "amber"
        assert flag.message == "Missing PAN – fix by Oct 22 for October pay"

    def test_two_missing_fields_and_wording(self):
        flag = pay_timing(
            date_added="2026-10-13",
            missing_fields=["PAN", "Bank account"],
            prototype_date="2026-10-13",
        )
        assert flag.level == "amber"
        assert "PAN and bank account" in flag.message

    def test_three_missing_fields_list(self):
        flag = pay_timing(
            date_added="2026-10-12",
            missing_fields=["PAN", "Bank account", "Tax ID"],
            prototype_date="2026-10-12",
        )
        assert "PAN, bank account and tax ID" in flag.message

    def test_empty_string_missing_ignored(self):
        flag = pay_timing(
            date_added="2026-10-13",
            missing_fields=["", "PAN", ""],
            prototype_date="2026-10-13",
        )
        assert flag.level == "amber"
        assert "PAN" in flag.message


class TestPastCutoffStillMissing:
    def test_amber_becomes_moved_to_november(self):
        flag = pay_timing(
            date_added="2026-10-13",
            missing_fields=["PAN", "Bank account"],
            prototype_date="2026-10-23",
        )
        assert flag.level == "amber"
        assert flag.message == "Moved to November · fix by Nov 22"
        assert flag.show_off_cycle_stub is True

    def test_on_cutoff_day_still_amber_not_moved(self):
        flag = pay_timing(
            date_added="2026-10-13",
            missing_fields=["PAN"],
            prototype_date="2026-10-22",
        )
        assert flag.level == "amber"

    def test_after_pay_date_still_missing_is_red(self):
        """Still missing after the Oct 28 pay date → red (Nov 2 onwards in the demo)."""
        flag = pay_timing(
            date_added="2026-10-13",
            missing_fields=["PAN"],
            prototype_date="2026-11-02",
        )
        assert flag.level == "red"
        assert "Missed October pay" in flag.message


class TestAfterCutoff:
    @pytest.mark.parametrize("added", ["2026-10-23", "2026-10-24", "2026-10-27"])
    def test_after_cutoff_red_with_off_cycle(self, added):
        flag = pay_timing(
            date_added=added,
            missing_fields=[],
            prototype_date="2026-10-23",
        )
        assert flag.level == "red"
        assert "November" in flag.message
        assert flag.show_off_cycle_stub is True

    def test_november_add_after_nov_cutoff_points_to_december(self):
        """Hired/added in November after Nov 15 — no October wording."""
        flag = pay_timing(
            date_added="2026-11-23",
            missing_fields=[],
            prototype_date="2026-11-23",
        )
        assert flag.level == "red"
        assert flag.message == "Added after Nov 22 cutoff → paid in December"
        assert "Oct" not in flag.message
        assert flag.show_off_cycle_stub is True

    def test_after_cutoff_even_with_missing_still_november_off_cycle(self):
        """Cutoff miss dominates; off-cycle stub still shown."""
        flag = pay_timing(
            date_added="2026-10-23",
            missing_fields=["PAN"],
            prototype_date="2026-10-23",
        )
        assert flag.level == "red"
        assert flag.show_off_cycle_stub is True
        assert "cutoff" in flag.message.lower()


class TestDemoPersonas:
    def test_priya_oct13_missing_pan_bank(self):
        flag = pay_timing(
            date_added="2026-10-13",
            missing_fields=["PAN", "Bank account"],
            prototype_date="2026-10-13",
        )
        assert flag.level == "amber"

    def test_priya_still_missing_on_oct17(self):
        flag = pay_timing(
            date_added="2026-10-13",
            missing_fields=["PAN", "Bank account"],
            prototype_date="2026-10-23",
        )
        assert flag.message == "Moved to November · fix by Nov 22"

    def test_priya_after_fill_details(self):
        flag = pay_timing(
            date_added="2026-10-13",
            missing_fields=[],
            prototype_date="2026-10-13",
        )
        assert flag.level == "green"

    def test_arjun_oct17_complete(self):
        flag = pay_timing(
            date_added="2026-10-23",
            missing_fields=[],
            prototype_date="2026-10-23",
        )
        assert flag.show_off_cycle_stub is True


class TestBoundaryEquality:
    def test_added_exactly_on_cutoff_counts_as_october_eligible(self):
        flag = pay_timing(
            date_added="2026-10-22",
            missing_fields=[],
            prototype_date="2026-10-22",
        )
        assert flag.level == "green"

    def test_added_day_after_cutoff(self):
        flag = pay_timing(
            date_added="2026-10-23",
            missing_fields=[],
            prototype_date="2026-10-23",
        )
        assert flag.level == "red"
