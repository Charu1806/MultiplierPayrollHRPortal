"""Submission Service — lock cycle after approve; engine handoff stub."""

from __future__ import annotations

from typing import Any, Dict

from domain.calendar_rules import cycle_dates, short_date

from server.db.repositories import Store


def submit_approved(store: Store, customer_id: str, as_of: str) -> Dict[str, Any]:
    cycle = store.get_current_cycle(customer_id)
    if not cycle:
        raise LookupError("cycle_not_found")
    store.set_cycle_approved(cycle["id"], 1)
    due = cycle_dates(as_of).get("fundingDue") or cycle["funding_due"]
    return {
        "approved": True,
        "approvedAt": as_of,
        "engineHandoff": "stub",
        "message": f"Payroll approved. Funding due {short_date(due)} (finance).",
        "next": {
            "fundingDue": due,
            "owner": "Finance",
        },
    }
