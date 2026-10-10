"""Calendar Service — stage, countdown, prototype dates from /config."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, Optional

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "data"))

from domain.calendar_rules import (  # noqa: E402
    APPROVAL,
    CALCULATION,
    CUTOFF,
    FUNDING_DUE,
    NOV_APPROVAL,
    NOV_CUTOFF,
    NOV_OPEN,
    NOV_PAY_DATE,
    PAY_DATE,
    REVIEW_CLOSE,
    REVIEW_OPEN,
    SUBMITTED,
    approval_countdown,
    backdated_arrears_months,
    countdown_text,
    cycle_containing_date,
    cycle_dates,
    cycle_for_new_input,
    first_pay_cycle,
    next_cycle_dates,
    november_open,
    parse_date,
    payment_apply_cycle,
    prorate,
    review_countdown,
    review_window_state,
    stage_for_date,
)
from domain.config import cycle_config  # noqa: E402

from server.db.repositories import Store  # noqa: E402

CYCLE = cycle_config()


def resolve_date(raw: Optional[str]) -> str:
    """Accept any ISO date in the prototype range, or 'Oct 12' labels. Default from config."""
    default = CYCLE["defaultPrototypeDate"]
    if not raw:
        return default
    text = str(raw).strip()
    for p in CYCLE.get("prototypeDates") or []:
        if text == p["value"] or text.lower() == p["label"].lower():
            return p["value"]
    iso = parse_date(text).isoformat()
    rng = CYCLE.get("dateRange") or {}
    lo = rng.get("min", "2026-10-01")
    hi = rng.get("max", "2027-01-31")
    if iso < lo:
        return lo
    if iso > hi:
        return hi
    return iso


def prototype_dates() -> Dict[str, Any]:
    dates = CYCLE["prototypeDates"]
    rng = CYCLE.get("dateRange") or {"min": "2026-10-01", "max": "2027-01-31"}
    return {
        "dates": [p["value"] for p in dates],
        "labels": [p["label"] for p in dates],
        "options": dates,
        "default": CYCLE["defaultPrototypeDate"],
        "min": rng["min"],
        "max": rng["max"],
        "keyDates": CYCLE.get("keyDates") or [],
    }


def cycle_counts(store: Store, customer_id: str, as_of: str) -> Dict[str, int]:
    emps = store.list_employees(customer_id, as_of=as_of)
    changed = sum(1 for e in emps if e.get("changed_this_cycle"))
    matched = sum(1 for e in emps if e.get("matched_source"))
    cycle = store.get_current_cycle(customer_id)
    lines = store.review_lines(cycle["id"], as_of=as_of) if cycle else []
    return {
        "changedLines": changed,
        "matchedLines": matched,
        "needsHumanCheck": len(lines),
        "employeeCount": len(emps),
    }


def cycle_view(store: Store, customer_id: str, as_of: str) -> Dict[str, Any]:
    customer = store.get_customer(customer_id)
    cycle = store.get_current_cycle(customer_id)
    if not customer or not cycle:
        raise LookupError("customer_or_cycle_not_found")
    stage = stage_for_date(as_of)
    if cycle.get("current_stage") != stage:
        store.set_cycle_stage(cycle["id"], stage)
        cycle["current_stage"] = stage
    counts = cycle_counts(store, customer_id, as_of)
    oct_ = CYCLE["cycles"]["october"]
    nov = CYCLE["cycles"]["november"]
    cd = cycle_dates(as_of)
    # Visibility flags: October funding/submitted only when still in October month
    in_nov = parse_date(as_of) >= NOV_OPEN
    return {
        "customer": {
            "id": customer["id"],
            "name": customer["name"],
            "hrTool": customer["hr_tool"],
        },
        "cycle": {
            "id": cd.get("id") or cycle["id"],
            "label": cd["label"],
            "stage": stage,
            "inputFinalisation": cd["inputFinalisation"],
            "calculation": cd.get("calculation"),
            "reviewOpen": cd.get("reviewOpen"),
            "reviewClose": cd.get("reviewClose"),
            "approval": cd.get("approval"),
            "fundingDue": cd.get("fundingDue"),
            "submitted": cd.get("submitted"),
            "payDate": cd["payDate"],
            "changedLines": counts["changedLines"],
            "matchedLines": counts["matchedLines"],
            "needsHumanCheck": counts["needsHumanCheck"],
            "approved": bool(cycle["approved"]),
            "employeeCount": counts["employeeCount"],
            "key": cd["key"],
        },
        "november": {
            "open": november_open(as_of),
            "label": nov["label"],
            "inputFinalisation": nov["inputFinalisation"],
            "approval": nov.get("reviewClose") or nov["approval"],
            "payDate": nov["payDate"],
            "calculation": nov.get("calculation"),
            "reviewOpen": nov.get("reviewOpen"),
            "reviewClose": nov.get("reviewClose"),
            "fundingDue": nov.get("fundingDue"),
            "submitted": nov.get("submitted"),
        },
        "asOf": parse_date(as_of).isoformat(),
        "countdown": countdown_text(as_of),
        "approvalCountdown": approval_countdown(as_of),
        "reviewCountdown": review_countdown(as_of),
        "reviewWindow": review_window_state(as_of),
        "cutoffPassed": parse_date(as_of) > parse_date(cd["inputFinalisation"]),
        "inputsOpen": parse_date(as_of) <= parse_date(cd["inputFinalisation"]),
        "payDatePassed": parse_date(as_of) >= parse_date(cd["payDate"]),
        "fundingVisible": (not in_nov) and parse_date(as_of) >= FUNDING_DUE,
        "submittedVisible": (not in_nov) and parse_date(as_of) >= SUBMITTED,
        "dates": {
            "cutoff": cd["inputFinalisation"],
            "calculation": cd.get("calculation"),
            "reviewOpen": cd.get("reviewOpen"),
            "reviewClose": cd.get("reviewClose"),
            "approval": cd.get("approval"),
            "fundingDue": cd.get("fundingDue"),
            "submitted": cd.get("submitted"),
            "payDate": cd["payDate"],
            "novCutoff": NOV_CUTOFF.isoformat(),
            "novApproval": NOV_APPROVAL.isoformat(),
            "novPayDate": NOV_PAY_DATE.isoformat(),
            "octCutoff": CUTOFF.isoformat(),
            "octPayDate": PAY_DATE.isoformat(),
        },
    }


def input_cycle(created_at: str) -> Dict[str, Any]:
    return cycle_for_new_input(created_at)


def containing_cycle(on: str) -> Dict[str, Any]:
    return cycle_containing_date(on)


def first_pay(start_date: str, input_cycle_key_or_dict: Any) -> Dict[str, Any]:
    return first_pay_cycle(start_date, input_cycle_key_or_dict)


def prorate_salary(monthly: float, start_date: str) -> Dict[str, Any]:
    return prorate(monthly, start_date)


def arrears_months(start_date: str, first_pay_cycle_dict: Dict[str, Any]) -> list[Dict[str, Any]]:
    return backdated_arrears_months(start_date, first_pay_cycle_dict)


def payment_cycle(recorded_on: str) -> str:
    return payment_apply_cycle(recorded_on)


def following_cycle(as_of: str) -> Dict[str, Any]:
    return next_cycle_dates(as_of)
