"""Funding Service — stub status for messaging (V1 email to finance)."""

from __future__ import annotations

from typing import Any, Dict

from server.db.repositories import Store


def status(store: Store, customer_id: str) -> Dict[str, Any]:
    cycle = store.get_current_cycle(customer_id)
    if not cycle:
        raise LookupError("cycle_not_found")
    return {
        "fundingDue": cycle["funding_due"],
        "fundsReceived": False,
        "owner": "Finance",
        "note": "Funding breakdown charts out of scope for V1 prototype",
    }
