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
        as_of="2026-11-17",
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
        as_of="2026-11-20",
        customer_id="cust_acme",
    )
    assert out["_inputMeta"]["cycle"]["key"] == "november"


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
        as_of="2026-11-18",
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


def test_parse_document_text_generic():
    from server.services.extraction import parse_document_text

    text = "Offer letter\nEmployee: Aisha Khan\nStart date: 2026-10-20\nAmount: ₹1,200,000\nPAN: ABCDE1234F"
    extracted = parse_document_text(text)
    assert extracted.get("employeeName") == "Aisha Khan"
    assert extracted.get("documentType") == "offer"
    assert extracted.get("pan") == "ABCDE1234F"
    assert extracted.get("annualSalary") == 1200000
