"""Validation Service — employee DTOs, pay timing, missing fields, documents."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "data"))

from domain.calendar_rules import stage_for_date  # noqa: E402

from server.db.repositories import Store  # noqa: E402
from server.services import findings as findings_svc  # noqa: E402
from server.services import rules as rules_svc  # noqa: E402

CURRENCY = {"India": "₹", "UK": "£", "Germany": "€", "Brazil": "R$"}


def findings_for_new_hire(**kwargs: Any) -> List[Dict[str, Any]]:
    return findings_svc.findings_for_new_hire(**kwargs)


def validate_employee(store: Store, emp: Dict[str, Any], as_of: str) -> List[Dict[str, Any]]:
    values = {k: v["value"] for k, v in store.field_values(emp["id"], as_of).items()}
    missing = store.required_missing_fields(emp["id"])
    exit_row = store.get_exit(emp["id"], as_of)
    return findings_svc.validate_employee_dict(
        emp,
        field_values=values,
        missing_required=missing,
        as_of=as_of,
        matched_source=emp.get("matched_source"),
        exit_lwd=(exit_row or {}).get("last_working_day"),
    )


def _is_featured(emp: Dict[str, Any]) -> bool:
    return bool(emp.get("is_new")) or not str(emp["id"]).startswith("emp_gen_")


def _action_needed(store: Store, emp: Dict[str, Any], open_issues: List[Dict]) -> bool:
    eid = emp["id"]
    if store.missing_fields(eid):
        return True
    return any(i.get("status") == "open" and i.get("employee_id") == eid for i in open_issues)


def enrich_employee(
    store: Store,
    emp: Dict[str, Any],
    as_of: str,
    open_issues: Optional[List[Dict]] = None,
) -> Dict[str, Any]:
    from server.services.pay_outlook import pay_outlook

    open_issues = open_issues or []
    missing = store.missing_fields(emp["id"], as_of)
    flag = rules_svc.pay_flag(store, emp, as_of)
    salary = rules_svc.salary_structure(store, emp, as_of).to_dict()
    otps = rules_svc.one_time_payments(store, emp["id"], as_of)
    exit_row = store.get_exit(emp["id"], as_of)
    status = rules_svc.employee_status(emp, exit_row, as_of)
    action = _action_needed(store, emp, open_issues)
    outlook = pay_outlook(store, emp, as_of)
    will = outlook["display"] + (f" · {outlook['note']}" if outlook.get("note") else "")
    return {
        "id": emp["id"],
        "name": emp["name"],
        "role": emp["role"],
        "country": emp["country"],
        "currency": emp["currency"],
        "septemberPay": emp["september_pay"],
        "monthlyNet": salary["net"],
        "salary": salary,
        "dateAdded": emp.get("date_added"),
        "isNew": bool(emp.get("is_new")),
        "status": status,
        "stage": stage_for_date(as_of),
        "source": emp.get("source"),
        "workEmail": emp.get("work_email"),
        "hireDate": emp.get("hire_date"),
        "managerName": emp.get("manager_name"),
        "missingFields": missing,
        "fieldValues": {k: v["value"] for k, v in store.field_values(emp["id"], as_of).items()},
        "oneOffs": [
            {"label": p.label, "amount": p.amount, "cycleMonth": p.cycle, "type": p.type, "recordedOn": p.recorded_on}
            for p in otps
        ],
        "changedThisCycle": bool(emp.get("changed_this_cycle")),
        "matchedSource": emp.get("matched_source"),
        "editedByYou": bool(emp.get("edited_by_you")),
        "actionNeeded": action,
        "payTiming": {
            "level": flag.level,
            "message": flag.message,
            "run": flag.run,
            "reason": flag.reason,
            "showOffCycleStub": flag.instant_payment_disabled,
            "instantPaymentDisabled": flag.instant_payment_disabled,
        },
        "payOutlook": outlook,
        "ifNoActionWillBePaid": will,
        "exit": rules_svc.exit_dto(emp, exit_row),
        "notes": emp.get("notes"),
        "featured": _is_featured(emp),
        "demoValues": rules_svc.demo_values(emp["id"]),
    }


def list_employees(
    store: Store,
    customer_id: str,
    as_of: str,
    country: Optional[str] = None,
    action_needed: Optional[bool] = None,
    *,
    q: Optional[str] = None,
    status: Optional[str] = None,
    filter_key: Optional[str] = None,
    page: Optional[int] = None,
    page_size: Optional[int] = None,
) -> Dict[str, Any]:
    cycle = store.get_current_cycle(customer_id)
    open_rows = store.list_issues(cycle["id"], status="open", as_of=as_of) if cycle else []
    out = [
        enrich_employee(store, e, as_of, open_rows)
        for e in store.list_employees(customer_id, country=country, as_of=as_of)
    ]
    if action_needed is not None:
        out = [e for e in out if e["actionNeeded"] is action_needed]
    if status and status != "all":
        out = [e for e in out if (e.get("status") or "Active") == status]
    if filter_key == "changed":
        out = [e for e in out if e.get("changedThisCycle")]
    elif filter_key == "reconciled":
        out = [e for e in out if e.get("matchedSource")]
    elif filter_key == "edited":
        out = [e for e in out if e.get("editedByYou")]
    elif filter_key == "paid_october":
        out = [e for e in out if (e.get("payTiming") or {}).get("run") == "October"]
    if q:
        ql = q.strip().lower()
        out = [
            e
            for e in out
            if ql in (e.get("name") or "").lower()
            or ql in (e.get("id") or "").lower()
            or ql in (e.get("role") or "").lower()
        ]
    # New joiners first, then name
    out.sort(key=lambda e: ((e.get("name") or "").lower()))
    out.sort(key=lambda e: 0 if e.get("isNew") else 1)

    total = len(out)
    if page is not None and page_size is not None:
        page = max(1, int(page))
        page_size = max(1, min(100, int(page_size)))
        start = (page - 1) * page_size
        slice_ = out[start : start + page_size]
        return {
            "employees": slice_,
            "count": len(slice_),
            "total": total,
            "page": page,
            "pageSize": page_size,
            "asOf": as_of,
        }
    return {"employees": out, "count": total, "total": total, "asOf": as_of}


def get_employee_detail(
    store: Store, employee_id: str, as_of: str, customer_id: str
) -> Dict[str, Any]:
    emp = store.get_employee(employee_id)
    if not emp or emp["customer_id"] != customer_id:
        raise LookupError("employee_not_found")
    from server.services.inputs import reconcile_prorated_arrears

    reconcile_prorated_arrears(store, emp)
    cycle = store.get_current_cycle(customer_id)
    open_rows = store.list_issues(cycle["id"], status="open", as_of=as_of) if cycle else []
    base = enrich_employee(store, emp, as_of, open_rows)

    mappings: List[Dict[str, Any]] = []
    docs = store.documents(employee_id, as_of)
    if docs:
        mappings = docs[-1].get("mappings") or []
    elif emp.get("is_new") or emp.get("source") in ("Offer letter", "Bonus letter", "Google Drive"):
        for fix in store.list_fixtures():
            if fix["target_name"] == emp["name"]:
                mappings = [
                    {
                        "sourceSystem": m.get("source_system"),
                        "sourceField": m.get("source_field"),
                        "multiplierField": m["multiplier_field"],
                        "value": m["value"],
                        "status": m["status"],
                        "confidence": m.get("confidence"),
                    }
                    for m in store.fixture_mappings(fix["id"])
                ]
                break

    events = store.journey_events(employee_id)
    journey = (
        [{"key": e["step_key"], "label": e["label"], "at": e["at"]} for e in events]
        if events
        else None
    )
    explanation = _hire_pay_explanation(emp, base)
    return {**base, "journeySteps": journey, "mappings": mappings, "payExplanation": explanation}


def _hire_pay_explanation(emp: Dict[str, Any], dto: Dict[str, Any]) -> Optional[str]:
    """Ask the LLM to explain a prorated first month. Returns None when nothing is prorated."""
    from domain.calendar_rules import prorate, short_date

    from server.services import llm as llm_svc
    from server.services import rules as rules_svc

    prorated = [o for o in (dto.get("oneOffs") or []) if "prorated" in (o.get("label") or "").lower()]
    if not prorated:
        return None
    hire = emp.get("hire_date")
    if not hire:
        return None
    info = prorate(float(emp.get("base_salary") or 0), hire)
    currency = emp.get("currency") or ""
    months = []
    for row in prorated:
        months.append(
            {
                "month": row["label"].replace(" salary · prorated", ""),
                "daysWorked": info["daysWorked"],
                "daysInMonth": info["daysInMonth"],
                "formula": info["formula"],
                "amount": rules_svc.fmt_money(currency, row["amount"]),
                "paidIn": row.get("cycleMonth"),
            }
        )
    paid_in = next((m["paidIn"] for m in months if m.get("paidIn")), None)
    facts = {
        "hired": short_date(hire),
        "added": short_date(emp["date_added"]) if emp.get("date_added") else None,
        "paidIn": paid_in,
        "monthlySalary": rules_svc.fmt_money(currency, float(emp.get("base_salary") or 0)),
        "monthlyNet": rules_svc.fmt_money(currency, float(dto.get("monthlyNet") or 0)),
        "proratedMonths": months,
    }
    return llm_svc.explain_hire_pay(facts)


def list_document_fixtures(store: Store) -> List[Dict[str, Any]]:
    return [
        {
            "id": f["id"],
            "filename": f["filename"],
            "docType": f["doc_type"],
            "targetName": f["target_name"],
            "country": f.get("country"),
            "allFieldsOk": bool(f.get("all_fields_ok")),
            "notes": f.get("notes"),
        }
        for f in store.list_fixtures()
    ]


def apply_missing_fields(
    store: Store,
    employee_id: str,
    fields: Dict[str, Any],
    *,
    as_of: str,
    source: str = "Edited by HR admin",
) -> Dict[str, Any]:
    emp = store.get_employee(employee_id)
    if not emp:
        raise LookupError("employee_not_found")

    aliases = {
        "taxid": "Tax ID",
        "tax_id": "Tax ID",
        "taxId": "Tax ID",
        "pan": "PAN",
        "cpf": "CPF",
        "bankaccount": "Bank account",
        "bank_account": "Bank account",
        "ifsc": "IFSC",
        "manager": "Manager",
        "ninumber": "NI number",
    }
    cleaned: Dict[str, str] = {}
    for key, val in (fields or {}).items():
        if key in ("asOf", "fillSample", "source"):
            continue
        name = aliases.get(key) or aliases.get(key.lower().replace(" ", "")) or key
        if val is None or str(val).strip() == "":
            continue
        norm = rules_svc.normalize_field_value(name, str(val))
        if not norm["ok"]:
            raise ValueError(norm["error"])
        cleaned[name] = norm["normalised"] or str(val).strip()

    if not cleaned:
        raise ValueError("No field values provided")

    for name, value in cleaned.items():
        store.add_field_value(employee_id, name, value, source=source, as_of=as_of)
        store.log_change(employee_id, name, None, value, source=source, as_of=as_of)
        if name == "Manager":
            store.update_employee_fields(employee_id, manager_name=value)

    _maybe_resolve_missing_issue(store, employee_id, as_of, source)
    cycle = store.get_current_cycle(emp["customer_id"])
    if cycle:
        rules_svc.after_input_change(store, cycle, employee_id, as_of=as_of, what="missing fields filled")
    return get_employee_detail(store, employee_id, as_of, emp["customer_id"])


def _maybe_resolve_missing_issue(store: Store, employee_id: str, as_of: str, actor: str) -> None:
    still = store.missing_fields(employee_id, as_of)
    issue = store.open_issue_for_employee(employee_id, "missing_fields") or store.open_issue_for_employee(
        employee_id, "missing_data"
    )
    if issue and not still:
        store.resolve_issue(
            issue["id"],
            resolved_by=actor,
            resolved_at=as_of,
            resolution_log=f"Required fields added by {actor}, {as_of}",
        )
    # Also revalidate so findings stay in sync

def attach_document(
    store: Store,
    employee_id: str,
    fixture_filename: str,
    *,
    as_of: str,
    customer_id: str,
) -> Dict[str, Any]:
    from server.services import extraction as extraction_svc

    extraction_svc.extract(
        store,
        customer_id=customer_id,
        as_of=as_of,
        file_name=fixture_filename,
        employee_id=employee_id,
    )
    return get_employee_detail(store, employee_id, as_of, customer_id)
