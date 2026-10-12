"""End-to-end inputs pipeline tests — no Priya/James seed names."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / "data" / "seed_db.py"


@pytest.fixture()
def store(tmp_path):
    from server.db.connection import connect
    from server.db.repositories import Store

    db = tmp_path / "dyn.db"
    subprocess.check_call(
        [sys.executable, str(SEED), "--db", str(db), "--seed", "42"],
        cwd=str(ROOT),
    )
    conn = connect(str(db))
    yield Store(conn)
    conn.close()


def test_create_employee_oct14_prorated_october(store):
    from server.services import inputs as inputs_svc

    dto, created = inputs_svc.create_employee(
        store,
        "cust_acme",
        {
            "name": "Aisha Khan",
            "country": "India",
            "hireDate": "2026-10-20",
            "monthlyNet": 100000,
            "manager": "Ravi Kumar",
            "fields": {"PAN": "ABCDE1234F", "Bank account": "123456789012", "IFSC": "HDFC0000123"},
        },
        as_of="2026-10-14",
    )
    assert created
    meta = dto.get("_inputMeta") or {}
    assert meta["cycle"]["key"] == "october"
    assert meta["prorate"]["daysWorked"] == 12


def test_bonus_after_nov_cutoff_lands_december(store):
    from server.services import inputs as inputs_svc

    dto, _ = inputs_svc.create_employee(
        store,
        "cust_acme",
        {"name": "Tom Wright", "country": "UK", "hireDate": "2026-01-01", "monthlyNet": 4000, "manager": "Sam"},
        as_of="2026-11-01",
    )
    out = inputs_svc.add_one_time_payment(
        store,
        dto["id"],
        {"type": "Bonus", "amount": 2000, "label": "Spot bonus"},
        as_of="2026-11-23",
        customer_id="cust_acme",
    )
    assert out["_inputMeta"]["cycle"]["key"] == "december"


def test_late_bonus_letter_flag(store):
    from server.services import inputs as inputs_svc

    preview = inputs_svc.preview_one_time(
        {"type": "Bonus", "amount": 1000, "payMonth": "2026-10-01"},
        as_of="2026-12-02",
    )
    assert "late_input" in preview["flags"]
    assert preview["cycle"]["key"] == "december"


def test_exit_lwd_nov30_added_nov20(store):
    from server.services import inputs as inputs_svc

    dto, _ = inputs_svc.create_employee(
        store,
        "cust_acme",
        {"name": "Nina Costa", "country": "Brazil", "hireDate": "2025-01-01", "monthlyNet": 15000, "manager": "Luis"},
        as_of="2026-11-01",
    )
    out = inputs_svc.record_exit(
        store,
        dto["id"],
        {"lastWorkingDay": "2026-11-30"},
        as_of="2026-11-23",
        customer_id="cust_acme",
    )
    assert out["_inputMeta"]["cycle"]["key"] == "december"
    assert out["_inputMeta"]["flags"] == ["late_exit"]
    assert out["exit"]["onHold"] is True
    assert out["exit"]["daysWorked"] == 30
    assert out["exit"]["payMonth"] == "December"
    assert "On hold for November" in out["exit"]["message"]


def test_exit_before_lock_in_pays_prorated_days_this_month(store):
    from server.services import inputs as inputs_svc

    dto, _ = inputs_svc.create_employee(
        store,
        "cust_acme",
        {"name": "Noah Berg", "country": "Germany", "hireDate": "2024-03-01", "monthlyNet": 4200, "manager": "Anja"},
        as_of="2026-11-01",
    )
    out = inputs_svc.record_exit(
        store,
        dto["id"],
        {"lastWorkingDay": "2026-11-10"},
        as_of="2026-11-10",
        customer_id="cust_acme",
    )
    assert out["_inputMeta"]["cycle"]["key"] == "november"
    assert out["_inputMeta"]["flags"] == []
    assert out["exit"]["onHold"] is False
    assert out["exit"]["daysWorked"] == 10
    assert out["exit"]["payMonth"] == "November"
    assert out["exit"]["fnf"]["net"] < out["salary"]["net"]
    assert "10 of 30 days" in out["exit"]["message"]
    assert "On hold" not in out["exit"]["message"]


def test_added_journey_uses_demo_date_not_today(store):
    from datetime import date

    from server.services import inputs as inputs_svc

    as_of = "2026-11-18"
    dto, created = inputs_svc.create_employee(
        store,
        "cust_acme",
        {
            "name": "Sofia Mendes",
            "country": "Brazil",
            "hireDate": "2026-11-18",
            "monthlyNet": 15000,
            "manager": "Ana",
        },
        as_of=as_of,
    )
    assert created
    steps = dto["journeySteps"]
    assert steps
    assert all(step["at"].startswith(as_of) for step in steps)
    if date.today().isoformat() != as_of:
        assert all(not step["at"].startswith(date.today().isoformat()) for step in steps)


def test_november_hire_after_cutoff_is_prorated_not_full_month(store):
    from domain.calendar_rules import prorate

    from server.services import inputs as inputs_svc

    monthly = 18000
    dto, created = inputs_svc.create_employee(
        store,
        "cust_acme",
        {
            "name": "Neel Kapoor",
            "country": "India",
            "hireDate": "2026-11-10",
            "monthlyNet": monthly,
            "manager": "Ravi",
        },
        as_of="2026-11-23",
    )
    assert created
    expected = prorate(monthly, "2026-11-10")["amount"]
    arrears = [o for o in dto["oneOffs"] if "prorat" in (o.get("label") or "").lower()]
    assert len(arrears) == 1
    assert arrears[0]["amount"] == expected
    assert arrears[0]["amount"] != monthly
    assert "November" in arrears[0]["label"]
    assert arrears[0]["cycleMonth"] == "December"
    assert dto.get("payExplanation")
    assert "prorat" in dto["payExplanation"].lower()
    assert "16,200" in dto["payExplanation"] or "16200" in dto["payExplanation"].replace(",", "")


def test_duplicate_bonus_warns(store):
    from server.services import inputs as inputs_svc
    from server.services import rules as rules_svc

    dto, _ = inputs_svc.create_employee(
        store,
        "cust_acme",
        {"name": "Omar Ali", "country": "UK", "hireDate": "2026-01-01", "monthlyNet": 4000, "manager": "Sam"},
        as_of="2026-10-12",
    )
    inputs_svc.add_one_time_payment(
        store,
        dto["id"],
        {"type": "Bonus", "amount": 1500, "label": "Bonus A"},
        as_of="2026-10-12",
        customer_id="cust_acme",
    )
    with pytest.raises(rules_svc.DuplicatePaymentWarning):
        inputs_svc.add_one_time_payment(
            store,
            dto["id"],
            {"type": "Bonus", "amount": 1500, "label": "Bonus B"},
            as_of="2026-10-13",
            customer_id="cust_acme",
        )


def test_record_exit_removes_employee_and_pays_fnf(store):
    from server.services import inputs as inputs_svc
    from server.services import review as review_svc
    from server.services.validation import list_employees

    as_of = "2026-11-23"
    dto, _ = inputs_svc.create_employee(
        store,
        "cust_acme",
        {"name": "Leah Okonkwo", "country": "UK", "hireDate": "2025-06-01", "monthlyNet": 5000, "manager": "Sam"},
        as_of="2026-11-01",
    )
    exited = inputs_svc.record_exit(store, dto["id"], {}, as_of=as_of, customer_id="cust_acme")
    assert exited["status"] == "Removed"
    assert exited["exit"]["daysWorked"] == 23
    assert exited["exit"]["onHold"] is True
    assert exited["exit"]["payMonth"] == "December"
    assert exited["exit"]["fnf"]["net"] < exited["salary"]["net"]
    assert "On hold for November" in exited["exit"]["message"]
    assert "23 of 30 days" in exited["exit"]["message"]
    assert exited["payOutlook"]["status"] == "held"
    assert "prorated" in exited["payOutlook"]["note"]
    assert "December" in exited["payOutlook"]["display"]

    review = review_svc.get_review(store, "cust_acme", as_of)
    line = next(
        row
        for row in review["lines"]
        if row["employeeId"] == dto["id"] and row.get("origin") == "exit"
    )
    assert line["changeSummary"].startswith("Exit · prorated 23 days")
    assert "On hold for November" in line["whyFlagged"]
    assert "December" in line["whyFlagged"]

    listed = list_employees(store, "cust_acme", as_of, page=1, page_size=100)
    assert dto["id"] not in {e["id"] for e in listed["employees"]}
    assert dto["id"] in {e["id"] for e in listed["removed"]}

    restored = inputs_svc.undo_exit(store, dto["id"], as_of=as_of, customer_id="cust_acme")
    assert restored["status"] == "Active"
    assert restored["exit"] is None
    review_after = review_svc.get_review(store, "cust_acme", as_of)
    assert not any(
        row["employeeId"] == dto["id"] and row.get("origin") == "exit" for row in review_after["lines"]
    )


def test_exit_is_dynamic_for_every_employee(store):
    """Exit, full-and-final, and the review line follow each employee's own pay."""
    from domain.salary import fnf

    from server.services import inputs as inputs_svc
    from server.services import rules as rules_svc
    from server.services.review import exit_review_line_id
    from server.services.validation import list_employees

    as_of = "2026-11-18"
    employees = store.list_employees("cust_acme", as_of=as_of)
    assert len(employees) >= 100
    countries = set()
    for emp in employees:
        countries.add(emp["country"])
        lwd = as_of
        hire = emp.get("hire_date")
        when = as_of
        if hire and hire > as_of:
            lwd = hire
            when = hire
        exited = inputs_svc.record_exit(
            store, emp["id"], {"lastWorkingDay": lwd}, as_of=when, customer_id="cust_acme"
        )
        expected = fnf(base=float(emp["base_salary"]), country=emp["country"], last_working_day=lwd)
        assert exited["status"] == "Removed"
        assert exited["id"] == emp["id"]
        assert exited["exit"]["fnf"]["net"] == expected.net
        assert exited["exit"]["fnf"]["gross"] == expected.gross
        money = rules_svc.fmt_money(emp["currency"], expected.net)
        assert money in exited["exit"]["message"]
        from domain.calendar_rules import cycle_dates

        line = store.get_review_line(exit_review_line_id(cycle_dates(when)["key"], emp["id"]))
        assert line is not None
        assert line["employee_id"] == emp["id"]
        assert line["employee_name"] == emp["name"]
        assert line["change_summary"] == f"Exit · prorated {expected.days_worked} days · {money}"
        assert exited["exit"]["daysWorked"] == expected.days_worked
        if expected.days_worked < 30:
            assert exited["exit"]["fnf"]["net"] < exited["salary"]["net"]
        assert line["origin"] == "exit"

        restored = inputs_svc.undo_exit(store, emp["id"], as_of=when, customer_id="cust_acme")
        assert restored["status"] == "Active"
        assert restored["exit"] is None
        assert store.get_review_line(line["id"]) is None
        fresh = store.get_employee(emp["id"])
        assert (fresh.get("status") or "Active") == "Active"
    assert countries == {"India", "UK", "Germany", "Brazil"}

    sample = []
    seen = set()
    for emp in employees:
        if emp["country"] in seen:
            continue
        if emp.get("hire_date") and emp["hire_date"] > as_of:
            continue
        seen.add(emp["country"])
        sample.append(emp)
    for emp in sample:
        inputs_svc.record_exit(store, emp["id"], {}, as_of=as_of, customer_id="cust_acme")
    listed = list_employees(store, "cust_acme", as_of, page=1, page_size=200)
    removed_ids = {row["id"] for row in listed["removed"]}
    active_ids = {row["id"] for row in listed["employees"]}
    for emp in sample:
        assert emp["id"] in removed_ids
        assert emp["id"] not in active_ids
        inputs_svc.undo_exit(store, emp["id"], as_of=as_of, customer_id="cust_acme")


def test_inputs_after_cutoff_show_on_next_review(store):
    from server.services import inputs as inputs_svc
    from server.services.review import get_review, patch_employee

    hire, _ = inputs_svc.create_employee(
        store,
        "cust_acme",
        {"name": "Nora Late", "country": "UK", "hireDate": "2026-11-01", "monthlyNet": 5000, "manager": "Sam"},
        as_of="2026-10-23",
    )
    bonus_emp = inputs_svc.add_one_time_payment(
        store,
        "emp_gen_001",
        {"type": "Bonus", "amount": 1000, "label": "Bonus"},
        as_of="2026-10-23",
        customer_id="cust_acme",
    )
    assert bonus_emp["_inputMeta"]["cycle"]["key"] == "november"
    before_hike = float(store.get_employee("emp_gen_002")["base_salary"])
    patch_employee(
        store,
        "emp_gen_002",
        {"baseSalary": 9000},
        as_of="2026-10-23",
        customer_id="cust_acme",
        confirm_ai=True,
    )
    assert float(store.get_employee("emp_gen_002")["base_salary"]) == before_hike
    from server.services.sync import run_sync

    late = run_sync(store, "cust_acme", "2026-10-23", trigger="Manual")
    assert late["changed"] == 0
    assert float(store.get_employee("emp_gen_002")["base_salary"]) == before_hike
    applied = run_sync(store, "cust_acme", "2026-11-01", trigger="Manual")
    assert applied["changed"] >= 1
    october = get_review(store, "cust_acme", "2026-10-20")
    october_ids = {line["employeeId"] for line in october["lines"]}
    assert hire["id"] not in october_ids
    assert "emp_gen_001" not in october_ids
    assert "emp_gen_002" not in october_ids

    november = get_review(store, "cust_acme", "2026-11-17")
    by_id = {line["employeeId"]: line for line in november["lines"]}
    assert hire["id"] in by_id
    assert "New employee" in by_id[hire["id"]]["changeSummary"]
    assert "emp_gen_001" in by_id
    assert "Bonus" in by_id["emp_gen_001"]["changeSummary"]
    assert "emp_gen_002" in by_id
    synced_emp = store.get_employee("emp_gen_002")
    assert float(synced_emp["base_salary"]) == 9000

    from server.services.validation import get_employee_detail

    nora = get_employee_detail(store, hire["id"], "2026-10-23", "cust_acme")
    assert "Added after inputs closed" in nora["payOutlook"]["banner"]["text"]
    assert "November 2026" in nora["payOutlook"]["banner"]["text"]
    rohan = get_employee_detail(store, "emp_gen_001", "2026-10-23", "cust_acme")
    assert "Bonus of" in rohan["payOutlook"]["banner"]["text"]
    assert "after inputs closed" in rohan["payOutlook"]["banner"]["text"]
    ishaan = get_employee_detail(store, "emp_gen_002", "2026-10-23", "cust_acme")
    assert ishaan["salary"]["base"] == 9000
    assert ishaan["payrollSnapshot"]["baseSalary"] == 9000
    assert ishaan["payrollSnapshot"]["readOnly"] is True


def test_parse_document_text_generic():
    from server.services.extraction import parse_document_text

    text = "Offer letter\nEmployee: Aisha Khan\nStart date: 2026-10-20\nAmount: ₹1,200,000\nPAN: ABCDE1234F"
    extracted = parse_document_text(text)
    assert extracted.get("employeeName") == "Aisha Khan"
    assert extracted.get("documentType") == "offer"
    assert extracted.get("pan") == "ABCDE1234F"
    assert extracted.get("annualSalary") == 1200000
