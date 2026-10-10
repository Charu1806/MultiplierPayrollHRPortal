"""pay_outlook — one rule for seed and generated employees."""

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

    db = tmp_path / "pay.db"
    subprocess.check_call([sys.executable, str(SEED), "--db", str(db), "--seed", "42"], cwd=str(ROOT))
    conn = connect(str(db))
    yield Store(conn)
    conn.close()


def test_before_payday_never_says_paid_in_october(store):
    from server.services.pay_outlook import pay_outlook

    for emp in store.list_employees("cust_acme", as_of="2026-10-12")[:15]:
        out = pay_outlook(store, emp, "2026-10-12")
        assert "Paid in October" not in out["display"]
        assert out["status"] in ("scheduled", "held", "moves")
        if out["status"] == "scheduled":
            assert "October" in out["display"] or "·" in out["display"]


def test_after_payday_paid_or_not(store):
    from server.services.pay_outlook import pay_outlook

    emps = store.list_employees("cust_acme", as_of="2026-10-28")
    gen = next(e for e in emps if str(e["id"]).startswith("emp_gen_"))
    out = pay_outlook(store, gen, "2026-10-28")
    assert out["status"] in ("paid", "not_paid", "returned", "held", "moves")
    if out["status"] == "paid":
        assert out["display"].startswith("Paid")


def test_enrich_includes_pay_outlook(store):
    from server.services.validation import enrich_employee

    emp = store.list_employees("cust_acme", as_of="2026-10-12")[0]
    dto = enrich_employee(store, emp, "2026-10-12")
    assert "payOutlook" in dto
    assert dto["payOutlook"]["display"]


def test_october_baseline_is_september(store):
    from server.services.pay_outlook import pay_outlook

    # Unchanged gen employee on Oct 12
    emps = store.list_employees("cust_acme", as_of="2026-10-12")
    gen = next(
        e
        for e in emps
        if str(e["id"]).startswith("emp_gen_")
        and abs(float(e["base_salary"]) - float(e["september_pay"])) < 0.5
        and not store.missing_fields(e["id"], "2026-10-12")
    )
    out = pay_outlook(store, gen, "2026-10-12")
    assert out["status"] == "scheduled"
    assert "same as September" in (out.get("note") or "")


def test_november_baseline_is_october_even_after_oct_raise(store):
    from server.services.pay_outlook import pay_outlook

    # Ananya: raised in October (base > september); on Nov 1 with no new change → same as October
    emp = store.get_employee("emp_ananya")
    assert emp
    assert float(emp["base_salary"]) > float(emp["september_pay"])
    out = pay_outlook(store, emp, "2026-11-01")
    assert out["month"] == "November"
    assert out.get("note") == "same as October"
    assert "September" not in (out.get("note") or "")
    assert "raise" not in (out.get("note") or "")


def test_missed_october_combines_oct_nov_when_fixed(store):
    from server.services.pay_outlook import pay_outlook

    emp = store.get_employee("emp_lena")
    assert emp
    # Still missing on Nov 3 → shows combined amount + December caveat
    out = pay_outlook(store, emp, "2026-11-03")
    assert out["amount"] >= float(emp["base_salary"]) * 1.5  # Oct+Nov
    assert "Oct" in (out.get("note") or "") and "Nov" in (out.get("note") or "")
    assert "December" in (out.get("note") or "") or "December" in out["display"]


def test_mid_october_joiner_prorated_amount(store):
    from server.services.pay_outlook import pay_outlook
    from domain.calendar_rules import prorate

    store.insert_employee(
        {
            "id": "emp_mid_join",
            "customer_id": "cust_acme",
            "name": "Mid Joiner",
            "role": "Engineer",
            "country": "India",
            "currency": "₹",
            "september_pay": 100000,
            "base_salary": 100000,
            "date_added": "2026-10-14",
            "is_new": 1,
            "status": "Active",
            "source": "HR tool",
            "hire_date": "2026-10-20",
            "manager_name": "Boss",
        }
    )
    emp = store.get_employee("emp_mid_join")
    out = pay_outlook(store, emp, "2026-10-14")
    expected = prorate(100000, "2026-10-20")["amount"]
    # net may be after tax — compare note/proration path
    assert "prorated from" in (out.get("note") or "")
    assert "20" in (out.get("note") or "") or out["amount"] <= expected * 1.01
