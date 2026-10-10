"""Edge cases: stage mapping and countdown text (context.md §5, round 3)."""

from __future__ import annotations

from datetime import date

import pytest

from domain.calendar_rules import (
    APPROVAL,
    CALCULATION,
    CALC_STAGE,
    CUTOFF,
    FUNDING_DUE,
    PAY_DATE,
    PROTOTYPE_DATES,
    REVIEW_CLOSE,
    REVIEW_OPEN,
    SUBMITTED,
    countdown_text,
    days_until_cutoff,
    parse_date,
    review_window_state,
    stage_for_date,
)


class TestPrototypeDateTable:
    @pytest.mark.parametrize(
        "d,stage,countdown",
        [
            ("2026-10-12", "Input finalisation", "3 days left"),
            ("2026-10-13", "Input finalisation", "2 days left"),
            ("2026-10-14", "Input finalisation", "1 day left"),
            ("2026-10-15", "Input finalisation", "Cutoff today"),
            ("2026-10-16", CALC_STAGE, "Input finalisation closed"),
            ("2026-10-17", "Review", "Input finalisation closed"),
            ("2026-10-22", "Review", "Input finalisation closed"),
            ("2026-10-23", "Funding", "Input finalisation closed"),
            ("2026-10-25", "Submitted", "Input finalisation closed"),
            ("2026-10-28", "Paid", "Input finalisation closed"),
        ],
    )
    def test_documented_prototype_dates(self, d, stage, countdown):
        assert stage_for_date(d) == stage
        assert countdown_text(d) == countdown


class TestCountdownEdges:
    def test_due_today_on_cutoff(self):
        assert countdown_text("2026-10-15") == "Cutoff today"
        assert days_until_cutoff("2026-10-15") == 0

    def test_day_before_cutoff(self):
        assert countdown_text("2026-10-14") == "1 day left"

    def test_closed_day_after_cutoff(self):
        assert countdown_text("2026-10-16") == "Input finalisation closed"

    def test_far_before_cutoff(self):
        assert countdown_text("2026-10-01") == "14 days left"

    def test_far_after_still_closed(self):
        assert countdown_text("2026-10-28") == "Input finalisation closed"


class TestStageTransitions:
    def test_last_day_of_input_finalisation(self):
        assert stage_for_date(CUTOFF) == "Input finalisation"

    def test_calculation_day(self):
        assert stage_for_date(CALCULATION) == CALC_STAGE
        assert stage_for_date(date(2026, 10, 16)) == CALC_STAGE

    def test_review_opens(self):
        assert stage_for_date(REVIEW_OPEN) == "Review"
        assert review_window_state(REVIEW_OPEN) == "open"

    def test_review_on_close_day(self):
        assert stage_for_date(APPROVAL) == "Review"
        assert stage_for_date(REVIEW_CLOSE) == "Review"
        assert review_window_state(REVIEW_CLOSE) == "open"

    def test_before_review(self):
        assert review_window_state("2026-10-14") == "before"
        assert review_window_state("2026-10-16") == "before"

    def test_after_review(self):
        assert review_window_state("2026-10-23") == "closed"

    def test_funding_on_funding_due(self):
        assert stage_for_date(FUNDING_DUE) == "Funding"

    def test_submitted_on_submitted_date(self):
        assert stage_for_date(SUBMITTED) == "Submitted"

    def test_paid_on_pay_date(self):
        assert stage_for_date(PAY_DATE) == "Paid"

    def test_paid_after_pay_date(self):
        assert stage_for_date(date(2026, 10, 29)) == "Paid"


class TestParseDateEdges:
    def test_iso(self):
        assert parse_date("2026-10-12") == date(2026, 10, 12)

    def test_date_object_passthrough(self):
        assert parse_date(date(2026, 10, 12)) == date(2026, 10, 12)

    def test_month_day_assumes_2026(self):
        assert parse_date("Oct 12") == date(2026, 10, 12)

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            parse_date("not-a-date")


class TestPrototypeDateSet:
    def test_control_dates_include_new_round3(self):
        assert len(PROTOTYPE_DATES) >= 10
        assert date(2026, 10, 16) in PROTOTYPE_DATES
        assert date(2026, 10, 20) in PROTOTYPE_DATES

    def test_all_prototype_dates_parse(self):
        for d in PROTOTYPE_DATES:
            assert isinstance(stage_for_date(d), str)
            assert countdown_text(d)
