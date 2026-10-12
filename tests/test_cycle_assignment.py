"""Cycle assignment for dynamic inputs — no seed employee names."""

from domain.calendar_rules import (
    backdated_arrears_months,
    cycle_for_new_input,
    first_pay_cycle,
    prorate,
)


def test_joiner_oct14_before_cutoff_october():
    c = cycle_for_new_input("2026-10-14")
    assert c["key"] == "october"
    pay = first_pay_cycle("2026-10-20", c)
    assert pay["key"] == "october"
    pr = prorate(100000, "2026-10-20")
    assert pr["daysInMonth"] == 31
    assert pr["daysWorked"] == 12
    assert abs(pr["amount"] - round(100000 * 12 / 31, 2)) < 0.01


def test_joiner_oct16_after_cutoff_november_with_october_arrears():
    c = cycle_for_new_input("2026-10-23")
    assert c["key"] == "november"
    pay = first_pay_cycle("2026-10-23", c)
    assert pay["key"] == "november"
    arrears = backdated_arrears_months("2026-10-23", pay)
    assert any("October" in a["label"] for a in arrears)


def test_joiner_nov10_start_jan5_scheduled_january():
    c = cycle_for_new_input("2026-11-10")
    assert c["key"] == "november"
    pay = first_pay_cycle("2027-01-05", c)
    assert pay["key"] == "january"


def test_bonus_nov17_december():
    c = cycle_for_new_input("2026-11-23")
    assert c["key"] == "december"


def test_dec16_input_january_2027():
    c = cycle_for_new_input("2026-12-23")
    assert c["key"] == "january"
    assert "2027" in c["label"]
