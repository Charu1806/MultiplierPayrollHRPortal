"""Connector Service — simulated HRIS upsert (no live Workday). Delegates to inputs pipeline."""

from __future__ import annotations

from typing import Any, Dict, Tuple

from server.db.repositories import Store
from server.services import inputs as inputs_svc
from server.services.validation import CURRENCY, get_employee_detail

COUNTRY_NET_DEFAULT = {"India": 100000, "UK": 4000, "Germany": 4200, "Brazil": 15000}


def create_employee(
    store: Store,
    customer_id: str,
    body: Dict[str, Any],
    *,
    as_of: str,
) -> Tuple[Dict[str, Any], bool]:
    return inputs_svc.create_employee(store, customer_id, body, as_of=as_of)


def add_one_time_payment(
    store: Store, employee_id: str, body: Dict[str, Any], *, as_of: str, customer_id: str
) -> Dict[str, Any]:
    return inputs_svc.add_one_time_payment(store, employee_id, body, as_of=as_of, customer_id=customer_id)


def record_exit(
    store: Store, employee_id: str, body: Dict[str, Any], *, as_of: str, customer_id: str
) -> Dict[str, Any]:
    return inputs_svc.record_exit(store, employee_id, body, as_of=as_of, customer_id=customer_id)


def undo_exit(store: Store, employee_id: str, *, as_of: str, customer_id: str) -> Dict[str, Any]:
    return inputs_svc.undo_exit(store, employee_id, as_of=as_of, customer_id=customer_id)
