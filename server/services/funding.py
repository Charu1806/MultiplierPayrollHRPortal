"""Funding estimates from persisted payroll and configured rates.

Rates and exchange rates are illustrative demo figures from config/cycle.json.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from domain.config import cycle_config

from server.db.repositories import Store

_SYMBOL = {"₹": "INR", "£": "GBP", "€": "EUR", "R$": "BRL"}


def status(store: Store, customer_id: str) -> Dict[str, Any]:
    from domain.calendar_rules import cycle_dates

    cycle = store.get_current_cycle(customer_id)
    if not cycle:
        raise LookupError("cycle_not_found")
    as_of = store.meta("prototype_date") or "2026-10-12"
    due = cycle_dates(as_of).get("fundingDue") or cycle["funding_due"]
    return {
        "fundingDue": due,
        "fundsReceived": False,
        "owner": "Finance",
        "note": "Illustrative funding estimate. Fees are not included.",
    }


def _cfg() -> Dict[str, Any]:
    return cycle_config().get("funding") or {}


def _rates(final: bool) -> Dict[str, float]:
    cfg = _cfg()
    raw = cfg.get("employerContributionRatesFinal") if final else cfg.get("employerContributionRates")
    raw = raw or cfg.get("employerContributionRates") or {}
    return {str(k): float(v) for k, v in raw.items()}


def _fx(final: bool) -> Dict[str, float]:
    cfg = _cfg()
    raw = cfg.get("fxToFundingCurrencyFinal") if final else cfg.get("fxToFundingCurrency")
    raw = raw or cfg.get("fxToFundingCurrency") or {}
    return {str(k): float(v) for k, v in raw.items()}


def _eligible(store: Store, customer_id: str, as_of: str) -> List[Dict[str, Any]]:
    from server.services.rules import payment_missing_fields

    rows = []
    for emp in store.list_employees(customer_id, as_of=as_of):
        if emp.get("status") == "Exited":
            continue
        if payment_missing_fields(store, emp, as_of):
            continue
        rows.append(emp)
    return rows


def _required(employees: List[Dict[str, Any]], *, final: bool) -> float:
    rates = _rates(final)
    fx = _fx(final)
    total = 0.0
    for emp in employees:
        gross = float(emp.get("base_salary") or 0) + float(emp.get("allowances") or 0)
        rate = rates.get(emp.get("country") or "", 0.0)
        code = _SYMBOL.get(emp.get("currency") or "", "")
        total += (gross * (1.0 + rate)) * fx.get(code, 0.0)
    return round(total, 2)


def _components(baseline_employees: List[Dict[str, Any]], final_employees: List[Dict[str, Any]]) -> Dict[str, float]:
    """Forex, rate changes, and other changes add up to the total variance."""
    base_required = _required(baseline_employees, final=False)
    at_base_fx_base_rate = _required(final_employees, final=False)
    # Rate component: final population, baseline FX, final employer rates, minus the same at baseline rates.
    rates = _rates(True)
    base_rates = _rates(False)
    fx = _fx(False)
    at_base_fx_final_rate = 0.0
    for emp in final_employees:
        gross = float(emp.get("base_salary") or 0) + float(emp.get("allowances") or 0)
        code = _SYMBOL.get(emp.get("currency") or "", "")
        at_base_fx_final_rate += (gross * (1.0 + rates.get(emp.get("country") or "", 0.0))) * fx.get(code, 0.0)
    at_base_fx_final_rate = round(at_base_fx_final_rate, 2)
    at_final = _required(final_employees, final=True)
    other = round(at_base_fx_base_rate - base_required, 2)
    rate_delta = round(at_base_fx_final_rate - at_base_fx_base_rate, 2)
    forex = round(at_final - at_base_fx_final_rate, 2)
    # base_rates is unused in the arithmetic above because _required(..., final=False) already uses them.
    del base_rates
    return {
        "baseline": base_required,
        "final": at_final,
        "forex": forex,
        "employerRates": rate_delta,
        "other": other,
        "total": round(at_final - base_required, 2),
    }


def estimate(store: Store, customer_id: str, as_of: str, *, employees: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    cfg = _cfg()
    cycle = store.get_current_cycle(customer_id)
    people = employees if employees is not None else _eligible(store, customer_id, as_of)
    required = _required(people, final=False)
    available = float(cfg.get("availableBalance") or 0)
    return {
        "currency": cfg.get("currency") or "USD",
        "illustrative": bool(cfg.get("illustrative", True)),
        "note": cfg.get("note") or "Illustrative demo rates, not live market data.",
        "required": required,
        "available": available,
        "toTransfer": round(max(0.0, required - available), 2),
        "eligibleEmployees": len(people),
        "cycleId": cycle["id"] if cycle else None,
        "asOf": as_of,
    }


def store_snapshot(store: Store, customer_id: str, cycle_id: str, kind: str, as_of: str, payload: Dict[str, Any]) -> None:
    existing = store.funding_snapshot(cycle_id, kind)
    if existing:
        return
    from server.services.clock import stamp

    store.conn.execute(
        """
        INSERT INTO funding_snapshots (id, customer_id, cycle_id, kind, taken_at, payload_json)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (f"fund_{kind}_{cycle_id}", customer_id, cycle_id, kind, stamp(as_of), json.dumps(payload)),
    )
    store.conn.commit()


def variance(store: Store, customer_id: str, as_of: str) -> Optional[Dict[str, Any]]:
    cycle = store.get_current_cycle(customer_id)
    if not cycle:
        return None
    base = store.funding_snapshot(cycle["id"], "baseline")
    final = store.funding_snapshot(cycle["id"], "final")
    if not base or not final:
        return None
    base_payload = json.loads(base["payload_json"])
    final_payload = json.loads(final["payload_json"])
    parts = _components(base_payload.get("employees") or [], final_payload.get("employees") or [])
    parts["reconciles"] = abs(parts["forex"] + parts["employerRates"] + parts["other"] - parts["total"]) < 0.02
    parts["currency"] = (_cfg().get("currency") or "USD")
    parts["illustrative"] = True
    return parts


def employee_rows_for_snapshot(store: Store, customer_id: str, as_of: str) -> List[Dict[str, Any]]:
    return [
        {
            "id": e["id"],
            "country": e["country"],
            "currency": e["currency"],
            "base_salary": e["base_salary"],
            "allowances": e.get("allowances") or 0,
        }
        for e in _eligible(store, customer_id, as_of)
    ]
