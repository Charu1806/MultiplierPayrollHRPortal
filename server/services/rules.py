"""Rules engine — pay timing, salary/tax, FnF, AI-check, outcome, field ownership.

Everything the UI shows for a prototype date is derived here from the store +
/config. The LLM does not set pay timing, deadlines, or routing. It only decides
which missing fields are required to pay someone.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "data") not in sys.path:
    sys.path.insert(0, str(ROOT / "data"))

from domain.calendar_rules import (  # noqa: E402
    CUTOFF,
    NOV_CUTOFF,
    PAY_DATE,
    cycle_dates,
    next_cycle_dates,
    parse_date,
    payment_apply_cycle,
    short_date,
    unsigned_outcome_rows,
)
from domain.config import cycle_config, rules_config, seed_config  # noqa: E402
from domain.pay_timing import PayFlag, pay_timing  # noqa: E402
from domain.salary import OneTimePayment, SalaryStructure, ai_check, fnf, tax_rate  # noqa: E402

from server.db.repositories import Store  # noqa: E402

RULES = rules_config()
CYCLE = cycle_config()
SEED = seed_config()

CURRENCY: Dict[str, str] = CYCLE["currencies"]
COUNTRY_ORDER = tuple(CYCLE["countries"])
EMPLOYEE_OWNED = set(RULES["employeeOwnedFields"])
def live_employee_count(store: Any, customer_id: str, as_of: Optional[str] = None) -> int:
    return len(store.list_employees(customer_id, as_of=as_of))


# ----------------------------------------------------------------------------- fields
def required_fields_for(country: str) -> List[str]:
    """Employee-actionable required fields (compat). Prefer requiredFieldsByCountry for owners."""
    by = RULES.get("requiredFieldsByCountry") or {}
    if country in by:
        # Keep seed-compat list tighter: only classic payroll IDs for missing-field seed issues
        legacy = RULES.get("requiredFields") or {}
        if country in legacy:
            return list(legacy[country])
        return [s["field"] for s in by[country] if s.get("owner") == "employee"]
    return list(RULES.get("requiredFields", {}).get(country, []))


def is_employee_owned(field: str) -> bool:
    return field in EMPLOYEE_OWNED


def split_owned(fields: List[str]) -> Dict[str, List[str]]:
    return {
        "employee": [f for f in fields if is_employee_owned(f)],
        "hr": [f for f in fields if not is_employee_owned(f)],
    }


def normalize_field_value(field: str, value: str) -> Dict[str, Any]:
    """Strip per fieldFormats then validate. Returns {ok, normalised, error}."""
    if value is None or not str(value).strip():
        return {"ok": False, "normalised": None, "error": f"{field} is required"}
    spec = RULES["fieldFormats"].get(field)
    raw = str(value).strip()
    if not spec:
        return {"ok": True, "normalised": raw, "error": None}
    strip_pat = spec.get("strip") or ""
    cleaned = re.sub(strip_pat, "", raw) if strip_pat else raw
    if not re.match(spec["pattern"], cleaned):
        return {"ok": False, "normalised": None, "error": f"{field}: expected {spec['hint']}"}
    return {"ok": True, "normalised": cleaned, "error": None}


def validate_field_format(field: str, value: str) -> Optional[str]:
    """Return an error message when `value` is not in the right format for `field`; None if OK."""
    result = normalize_field_value(field, value)
    return result["error"]


# Samples for people who are not in the seed map, so "Use demo value" works on any hire.
_GENERIC_DEMO = {
    "PAN": "ABCDE1234F",
    "Bank account": "123456789012",
    "IFSC": "HDFC0000123",
    "Manager": "Ravi Kumar",
    "Tax ID": "12345678901",
    "CPF": "12345678909",
    "NI number": "AB123456C",
    "Sort code": "123456",
    "IBAN": "DE89370400440532013000",
    "PIX key": "sofia@example.com",
    "Tax class": "1",
}


def demo_values(employee_id: str, fields: Optional[List[str]] = None) -> Dict[str, str]:
    vals = dict(SEED.get("demoValues", {}).get(employee_id, {}))
    if fields is not None:
        for field in fields:
            if field not in vals and field in _GENERIC_DEMO:
                vals[field] = _GENERIC_DEMO[field]
        vals = {k: v for k, v in vals.items() if k in fields}
    return vals


def lower_field(field: str) -> str:
    """'Bank account' → 'bank account'; acronyms (PAN, CPF, IFSC, 'Tax ID' → 'tax ID') keep their caps."""
    if len(field) > 1 and field[1].islower():
        return field[0].lower() + field[1:]
    return field


def sentence_fields(fields: List[str]) -> str:
    """'PAN, bank account, manager' — used in issue titles ("Missing PAN, bank account, manager")."""
    return ", ".join(lower_field(f) for f in fields)


# ----------------------------------------------------------------------------- salary
def one_time_payments(store: Store, employee_id: str, as_of: Optional[str]) -> List[OneTimePayment]:
    return [
        OneTimePayment(
            id=p["id"],
            type=p["type"],
            label=p["label"],
            amount=float(p["amount"]),
            recorded_on=p["recorded_on"],
            document_name=p.get("document_name"),
            source=p.get("source"),
        )
        for p in store.one_time_payments(employee_id, as_of)
    ]


def salary_structure(store: Store, emp: Dict[str, Any], as_of: Optional[str], cycle: str = "October") -> SalaryStructure:
    return SalaryStructure(
        base=float(emp["base_salary"]),
        allowances=float(emp.get("allowances") or 0),
        unpaid_leave_days=int(emp.get("unpaid_leave_days") or 0),
        one_time_payments=one_time_payments(store, emp["id"], as_of),
        tax_rate=tax_rate(emp["country"]),
        cycle=cycle,
    )


def ai_check_payload(emp: Dict[str, Any], new_gross: float) -> Optional[Dict[str, Any]]:
    """LLM judges whether a pay edit needs a second confirmation (no fixed % threshold)."""
    from server.services import llm as llm_svc

    decision = llm_svc.decide_pay_edit(
        employee_name=emp["name"],
        country=emp["country"],
        currency=emp["currency"],
        september_pay=float(emp["september_pay"]),
        new_base=float(new_gross),
    )
    if not decision.get("needsConfirm"):
        return None
    return {
        "label": decision.get("label") or "AI check",
        "message": decision.get("message") or "Please confirm this pay change.",
        "direction": decision.get("direction"),
        "multiple": decision.get("multiple"),
        "source": decision.get("source"),
        "recommend": decision.get("recommend"),
        "confidence": decision.get("confidence"),
    }


# ----------------------------------------------------------------------------- formatting
def fmt_money(currency: str, amount: float) -> str:
    amount = float(amount)
    whole = int(round(amount))
    if abs(amount - whole) > 0.004:
        txt = f"{amount:,.2f}"
    else:
        txt = f"{whole:,}"
    if currency == "₹":
        txt = _indian_grouping(whole if abs(amount - whole) <= 0.004 else amount)
    return f"{currency}{txt}"


def _indian_grouping(amount: float) -> str:
    neg = amount < 0
    amount = abs(amount)
    whole = int(amount)
    frac = amount - whole
    s = str(whole)
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        s = ",".join(groups + [tail])
    if frac > 0.004:
        s += f"{frac:.2f}"[1:]
    return ("-" if neg else "") + s


# ----------------------------------------------------------------------------- employee state
def employee_status(emp: Dict[str, Any], exit_row: Optional[Dict[str, Any]], as_of: str) -> str:
    if not exit_row:
        return "Active"
    return "Removed" if parse_date(as_of) >= parse_date(exit_row["last_working_day"]) else "Exiting"


def payment_missing_fields(store: Store, emp: Dict[str, Any], as_of: str) -> List[str]:
    """Missing fields the model says are required to pay this person. Manager is not one of them."""
    from server.services import llm as llm_svc

    missing = store.missing_fields(emp["id"], as_of)
    required = set(llm_svc.payment_required_fields(emp.get("country") or "", missing))
    return [f for f in missing if f in required]


def _payment_completed_on(store: Store, emp: Dict[str, Any], as_of: str) -> Optional[str]:
    """Date the last payment-required field was filled. A missing manager does not count."""
    from server.services import llm as llm_svc

    tracked = store.required_missing_fields(emp["id"])
    required = set(llm_svc.payment_required_fields(emp.get("country") or "", tracked))
    if not required:
        return None
    values = store.field_values(emp["id"], as_of)
    if any(f not in values for f in required):
        return None
    return max(values[f]["as_of"] for f in required)


def pay_flag(store: Store, emp: Dict[str, Any], as_of: str) -> PayFlag:
    exit_row = store.get_exit(emp["id"], as_of)
    return pay_timing(
        date_added=emp.get("date_added"),
        missing_fields=payment_missing_fields(store, emp, as_of),
        prototype_date=as_of,
        fixed_on=_payment_completed_on(store, emp, as_of),
        exit_recorded_on=exit_row["recorded_on"] if exit_row else None,
    )


def fnf_for(emp: Dict[str, Any], exit_row: Dict[str, Any]) -> Dict[str, Any]:
    return fnf(
        base=float(emp["base_salary"]),
        country=emp["country"],
        last_working_day=exit_row["last_working_day"],
        notice_pay=float(exit_row.get("notice_pay") or 0),
        severance=float(exit_row.get("severance") or 0),
        leave_encashment_days=int(exit_row.get("leave_encashment_days") or 0),
        recoveries=float(exit_row.get("recoveries") or 0),
    ).to_dict()


def exit_pay_plan(emp: Dict[str, Any], exit_row: Dict[str, Any]) -> Dict[str, Any]:
    """Days worked come from the last working day. After lock-in, that pay waits for next month."""
    from domain.calendar_rules import cycle_containing_date, cycle_dates, cycle_for_new_input
    from domain.salary import DAYS_IN_MONTH

    settlement = fnf_for(emp, exit_row)
    recorded_on = exit_row["recorded_on"]
    held = cycle_containing_date(exit_row["last_working_day"])
    pay = cycle_for_new_input(recorded_on)
    on_hold = pay["key"] != held["key"]
    held_month = str(held.get("label") or "").split()[0]
    pay_month = str(pay.get("label") or "").split()[0]
    days = int(settlement["daysWorked"])
    money = fmt_money(emp["currency"], settlement["net"])
    if on_hold:
        message = (
            f"On hold for {held_month}. "
            f"Prorated pay for {days} of {DAYS_IN_MONTH} days ({money}) will be paid in {pay_month}."
        )
    else:
        message = f"Prorated pay for {days} of {DAYS_IN_MONTH} days ({money}) will be paid in {pay_month}."
    recorded = parse_date(recorded_on)
    return {
        "onHold": on_hold,
        "daysWorked": days,
        "daysInMonth": DAYS_IN_MONTH,
        "payMonth": pay_month,
        "heldMonth": held_month,
        "lockDate": cycle_dates(recorded_on)["inputFinalisation"],
        "payCycleKey": pay["key"],
        "message": message,
        "settlementCycle": "October" if recorded <= CUTOFF else pay_month,
        "fnf": settlement,
    }


def exit_dto(emp: Dict[str, Any], exit_row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not exit_row:
        return None
    plan = exit_pay_plan(emp, exit_row)
    return {
        "id": exit_row["id"],
        "lastWorkingDay": exit_row["last_working_day"],
        "reason": exit_row.get("reason"),
        "noticePay": float(exit_row.get("notice_pay") or 0),
        "severance": float(exit_row.get("severance") or 0),
        "leaveEncashmentDays": int(exit_row.get("leave_encashment_days") or 0),
        "recoveries": float(exit_row.get("recoveries") or 0),
        "recordedOn": exit_row["recorded_on"],
        "onHold": plan["onHold"],
        "daysWorked": plan["daysWorked"],
        "daysInMonth": plan["daysInMonth"],
        "payMonth": plan["payMonth"],
        "heldMonth": plan["heldMonth"],
        "lockDate": plan["lockDate"],
        "settlementCycle": plan["settlementCycle"],
        "message": plan["message"],
        "fnf": plan["fnf"],
    }


# ----------------------------------------------------------------------------- outcome / rollups
def _reason_label(flag: PayFlag, otps: List[OneTimePayment]) -> Optional[str]:
    if flag.run in ("November", "At risk", "Held") and flag.reason:
        return flag.reason
    if any(p.cycle == "November" for p in otps):
        return "one-time payment recorded after Oct 15"
    return None


def outcome(store: Store, customer_id: str, as_of: str) -> Optional[Dict[str, Any]]:
    """Outcome card data for Oct 28 and later; None before the pay date."""
    if parse_date(as_of) < PAY_DATE:
        return None
    emps = store.list_employees(customer_id, as_of=as_of)
    paid: List[Dict[str, Any]] = []
    moved: List[Dict[str, Any]] = []
    at_risk: List[Dict[str, Any]] = []
    returned: List[Dict[str, Any]] = []
    cycle = store.get_current_cycle(customer_id)
    returned_ids = set()
    if cycle:
        for issue in store.list_issues(cycle["id"], status="open", as_of=as_of):
            if (issue.get("kind") or "") == "payment_returned" and issue.get("employee_id"):
                returned_ids.add(issue["employee_id"])
    for emp in emps:
        flag = pay_flag(store, emp, as_of)
        otps = one_time_payments(store, emp["id"], as_of)
        reason = _reason_label(flag, otps)
        row = {"id": emp["id"], "name": emp["name"], "country": emp["country"], "reason": reason}
        if emp["id"] in returned_ids:
            returned.append({**row, "reason": "Payment was returned by the bank"})
            paid.append(row)
            continue
        if flag.run == "At risk":
            at_risk.append(row)
            moved.append(row)
        elif flag.run == "November" or (flag.run == "October" and reason):
            moved.append(row)
        else:
            paid.append(row)
    in_run = len(emps) - len(moved)
    result: Dict[str, Any] = {
        "payDate": PAY_DATE.isoformat(),
        "total": len(emps),
        "inRun": in_run,
        "totalLabel": f"{len(emps)}",
        "paidOnTime": {"count": len(paid), "href": "/people?filter=paid_october"},
        "movedToNovember": {"count": len(moved), "employees": moved},
        "stillAtRisk": {
            "count": len(at_risk),
            "employees": at_risk,
            "message": f"Missed October pay date – add by {short_date(NOV_CUTOFF)} or November pay is at risk too",
        },
        "paymentReturned": {
            "count": len(returned),
            "employees": returned,
            "href": "/payroll/actions" if returned else None,
            "message": (
                f"{len(paid)} of {in_run} paid · {len(returned)} payment returned"
                if returned
                else None
            ),
        },
    }
    return result


def not_in_run(store: Store, customer_id: str, as_of: str) -> Dict[str, Any]:
    """Employees held out of the current run because data is missing (Review info line)."""
    emps = store.list_employees(customer_id, as_of=as_of)
    held = []
    for emp in emps:
        if payment_missing_fields(store, emp, as_of):
            held.append({"id": emp["id"], "name": emp["name"], "country": emp["country"]})
    n = len(held)
    cd = cycle_dates(as_of)
    cut = short_date(cd["inputFinalisation"])
    next_label = next_cycle_dates(as_of).get("label") or "the next cycle"
    return {
        "count": n,
        "employees": held,
        "message": (
            f"{n} employee{'s are' if n != 1 else ' is'} not in this run because data is missing. "
            f"They'll be paid in {next_label} unless fixed by {cut}"
            if n
            else "Every employee has complete data for this run."
        ),
        "href": "/payroll/actions",
    }


def input_finalisation_passed(as_of: str) -> bool:
    cd = cycle_dates(as_of)
    return parse_date(as_of) > parse_date(cd["inputFinalisation"])


def review_line_created_on(as_of: str) -> str:
    """Prototype date a new review line should appear (next cycle if after cutoff)."""
    if not input_finalisation_passed(as_of):
        return as_of
    nxt = next_cycle_dates(as_of)
    return str(nxt.get("open") or as_of)


class DuplicatePaymentWarning(Exception):
    def __init__(self, payload: Dict[str, Any]):
        super().__init__("duplicate_payment")
        self.payload = payload


def duplicate_payment_check(
    store: Store,
    employee_id: str,
    *,
    type_: str,
    amount: float,
    as_of: str,
) -> Optional[Dict[str, Any]]:
    """Warn when the same amount+type already exists for this cycle or as unsigned arrears."""
    amount = float(amount)
    apply_cycle = payment_apply_cycle(as_of)
    emp = store.get_employee(employee_id) or {}
    currency = emp.get("currency") or "£"
    for p in store.one_time_payments(employee_id, as_of):
        if p["type"] == type_ and abs(float(p["amount"]) - amount) < 0.01:
            if payment_apply_cycle(p["recorded_on"]) == apply_cycle:
                return {
                    "code": "duplicate_payment",
                    "message": f"Possible duplicate: {type_} {fmt_money(currency, amount)} already recorded for {apply_cycle}.",
                    "existingPaymentId": p["id"],
                }
    for row in unsigned_outcome_rows():
        if row["employeeId"] == employee_id and row.get("kind") == "arrears" and abs(float(row["amount"]) - amount) < 0.01:
            return {
                "code": "duplicate_arrears",
                "message": f"Possible duplicate: {fmt_money(currency, amount)} already scheduled as October arrears in {apply_cycle} review.",
                "arrearsLabel": row.get("label"),
            }
    return None


def carry_overs(store: Store, customer_id: str, as_of: str) -> List[Dict[str, Any]]:
    """Employees whose October pay moved to November (missing data, late joiners, late exits)."""
    out = []
    for emp in store.list_employees(customer_id, as_of=as_of):
        flag = pay_flag(store, emp, as_of)
        if flag.run in ("November", "At risk"):
            out.append({"id": emp["id"], "name": emp["name"], "country": emp["country"], "reason": flag.reason})
    return out


# ----------------------------------------------------------------------------- post-write hooks
def after_input_change(store: Store, cycle: Dict[str, Any], employee_id: Optional[str], *, as_of: str, what: str) -> Dict[str, Any]:
    """Any input change after an active sign-off reopens it and sends the employee's line back to Review."""
    result = {"signoffReopened": False, "lineReopened": None}
    signoff = store.active_signoff(cycle["id"])
    if signoff and not signoff.get("reopened_on"):
        store.reopen_signoff(cycle["id"], reopened_on=as_of, note="Sign-off reopened – 1 line changed")
        result["signoffReopened"] = True
    if employee_id:
        line = store.current_review_line(cycle["id"], employee_id)
        if line and store.line_approval(line["id"]):
            store.revoke_line_approval(line["id"], revoked_on=as_of, reason=what)
            result["lineReopened"] = line["id"]
    return result
