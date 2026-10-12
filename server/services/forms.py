"""Employee form GET/POST via signed token."""

from __future__ import annotations

from typing import Any, Dict

from domain.calendar_rules import short_date
from server.db.repositories import Store
from server.services import clock as clock_svc
from server.services import form_tokens
from server.services import rules as rules_svc
from server.services import validation as validation_svc


def _pronoun(first: str) -> str:
    f = first.lower()
    if f in {"priya", "lena", "beatriz", "chloe", "ananya"} or first.endswith("a"):
        return "her"
    return "their"


def _submit_label(fields: list[str]) -> str:
    s = set(fields)
    if "PAN" in s and ("Bank account" in s or "IFSC" in s):
        return "PAN and bank details"
    if "Tax ID" in s:
        return "Tax ID"
    if "CPF" in s:
        return "CPF"
    if "NI number" in s:
        return "NI number"
    return rules_svc.sentence_fields(fields) or "details"


def get_form(store: Store, token: str, *, as_of: str, customer_id: str) -> Dict[str, Any]:
    from domain.config import rules_config

    resolved = form_tokens.resolve_token(store, token, as_of=as_of)
    emp = validation_svc.get_employee_detail(store, resolved["employeeId"], as_of, customer_id)
    split = rules_svc.split_owned(emp["missingFields"])
    fields = split["employee"]
    return {
        "employee": {"id": emp["id"], "name": emp["name"], "country": emp["country"]},
        "fields": fields,
        "demoValues": rules_svc.demo_values(emp["id"], fields),
        "formats": rules_config()["fieldFormats"],
        "cutoffLabel": resolved["cutoffLabel"],
        "token": token,
    }


def submit_form(
    store: Store,
    token: str,
    fields: Dict[str, Any],
    *,
    as_of: str,
    customer_id: str,
) -> Dict[str, Any]:
    clock_svc.set_as_of(as_of)
    resolved = form_tokens.resolve_token(store, token, as_of=as_of)
    employee_id = resolved["employeeId"]

    owned_keys = [str(k) for k in (fields or {}) if rules_svc.is_employee_owned(str(k))]
    label = _submit_label(owned_keys)

    emp = validation_svc.apply_missing_fields(
        store, employee_id, fields, as_of=as_of, source="Employee form"
    )
    store.add_journey_events(
        employee_id,
        [
            {
                "key": "received",
                "label": "Received from employee form",
                "at": clock_svc.now(),
                "source": "Employee form",
            }
        ],
    )
    form_tokens.mark_used(store, resolved["jti"])

    first = emp["name"].split()[0]
    on_track = (emp.get("payTiming") or {}).get("level") == "green"
    if on_track:
        return {
            "employee": emp,
            "message": "Thanks for adding your details. Payment is on track.",
        }
    cycle = store.get_current_cycle(customer_id)
    if cycle:
        store.add_notification(
            cycle["id"],
            send_date=as_of,
            recipient="HR admin",
            subject=f"{first} added {_pronoun(first)} {label}",
            body_summary=f"{emp['name']} submitted {label} via the employee form on {short_date(as_of)}.",
            actions=[
                {
                    "action_text": f"Review {first}'s details",
                    "deadline": as_of,
                    "issue_id": resolved.get("issueId"),
                }
            ],
            cta_label="Open Action needed",
            cta_href="/payroll/actions",
            kind="employee_form_submitted",
        )

    msg = (
        f"{first} submitted her details."
        if first.endswith("a")
        else f"{first} submitted their details."
    )
    return {"employee": emp, "message": msg}
