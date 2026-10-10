"""Submission Service — lock cycle after approve; engine handoff stub."""

from __future__ import annotations

from typing import Any, Dict

from server.db.repositories import Store


def submit_approved(store: Store, customer_id: str, as_of: str) -> Dict[str, Any]:
    cycle = store.get_current_cycle(customer_id)
    if not cycle:
        raise LookupError("cycle_not_found")
    store.set_cycle_approved(cycle["id"], 1)
    return {
        "approved": True,
        "approvedAt": as_of,
        "engineHandoff": "stub",
        "message": "Payroll approved. Funding due Oct 23 (finance).",
        "next": {
            "fundingDue": cycle["funding_due"],
            "owner": "Finance",
        },
    }
