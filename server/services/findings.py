"""Config-driven validation findings — no hard-coded person or file names."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from domain.config import rules_config

RULES = rules_config()


def required_specs(country: str) -> List[Dict[str, str]]:
    by = RULES.get("requiredFieldsByCountry") or {}
    if country in by:
        return list(by[country])
    # Legacy fallback
    return [{"field": f, "owner": "employee"} for f in (RULES.get("requiredFields") or {}).get(country, [])]


def required_field_names(country: str) -> List[str]:
    return [s["field"] for s in required_specs(country)]


def findings_for_new_hire(
    *,
    country: str,
    manager: Optional[str],
    hire_date: Optional[str],
    salary: Optional[float],
    field_values: Optional[Dict[str, str]] = None,
) -> List[Dict[str, Any]]:
    values = dict(field_values or {})
    if manager:
        values.setdefault("Manager", manager)
    if hire_date:
        values.setdefault("Start date", hire_date)
    if salary is not None:
        values.setdefault("Salary", str(salary))
    return _check_required_and_formats(country, values)


def _check_required_and_formats(country: str, values: Dict[str, str]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    formats = RULES.get("fieldFormats") or {}
    for spec in required_specs(country):
        field = spec["field"]
        owner = spec.get("owner") or "employee"
        # Salary / Start date satisfied by presence in values
        raw = values.get(field)
        if field == "Salary" and raw is not None and str(raw).strip():
            continue
        if field == "Start date" and raw is not None and str(raw).strip():
            continue
        if raw is None or not str(raw).strip():
            # Don't require IFSC/Sort code/IBAN/PIX/Tax class if not in legacy seed path —
            # still flag them for new hires when listed
            out.append(
                {
                    "rule": "required_missing",
                    "severity": "blocking",
                    "field": field,
                    "owner": owner,
                    "message": f"{field} is required",
                }
            )
            continue
        fmt = formats.get(field)
        if fmt:
            strip = fmt.get("strip") or ""
            cleaned = re.sub(strip, "", str(raw)) if strip else str(raw).strip()
            if not re.match(fmt["pattern"], cleaned, re.I):
                out.append(
                    {
                        "rule": "format_invalid",
                        "severity": "blocking",
                        "field": field,
                        "owner": owner,
                        "message": f"{field} format invalid ({fmt.get('hint') or 'check format'})",
                    }
                )
    return out


def validate_employee_dict(
    emp: Dict[str, Any],
    *,
    field_values: Dict[str, str],
    missing_required: List[str],
    as_of: str,
    september_pay: Optional[float] = None,
    base_salary: Optional[float] = None,
    matched_source: Optional[str] = None,
    exit_lwd: Optional[str] = None,
) -> List[Dict[str, Any]]:
    from domain.calendar_rules import parse_date

    values = dict(field_values)
    if emp.get("manager_name"):
        values.setdefault("Manager", emp["manager_name"])
    if emp.get("hire_date"):
        values.setdefault("Start date", emp["hire_date"])
    if base_salary is not None or emp.get("base_salary") is not None:
        values.setdefault("Salary", str(base_salary if base_salary is not None else emp["base_salary"]))

    # Merge explicit missing list into empty values
    for f in missing_required:
        values.setdefault(f, "")

    # New joiners: full country checklist. Existing: only fields already tracked + formats for filled values.
    if emp.get("is_new"):
        out = _check_required_and_formats(emp["country"], values)
    else:
        out = []
        formats = RULES.get("fieldFormats") or {}
        owners = {s["field"]: s.get("owner", "employee") for s in required_specs(emp["country"])}
        for field in missing_required:
            raw = values.get(field)
            if raw is None or not str(raw).strip():
                out.append(
                    {
                        "rule": "required_missing",
                        "severity": "blocking",
                        "field": field,
                        "owner": owners.get(field, "employee"),
                        "message": f"{field} is required",
                    }
                )
            else:
                fmt = formats.get(field)
                if fmt:
                    strip = fmt.get("strip") or ""
                    cleaned = re.sub(strip, "", str(raw)) if strip else str(raw).strip()
                    if not re.match(fmt["pattern"], cleaned, re.I):
                        out.append(
                            {
                                "rule": "format_invalid",
                                "severity": "blocking",
                                "field": field,
                                "owner": owners.get(field, "employee"),
                                "message": f"{field} format invalid ({fmt.get('hint') or 'check format'})",
                            }
                        )
        # Format-check any filled requiredFields values
        for field, raw in values.items():
            if field in missing_required or not raw:
                continue
            fmt = formats.get(field)
            if not fmt:
                continue
            strip = fmt.get("strip") or ""
            cleaned = re.sub(strip, "", str(raw)) if strip else str(raw).strip()
            if not re.match(fmt["pattern"], cleaned, re.I):
                out.append(
                    {
                        "rule": "format_invalid",
                        "severity": "blocking",
                        "field": field,
                        "owner": owners.get(field, "employee"),
                        "message": f"{field} format invalid ({fmt.get('hint') or 'check format'})",
                    }
                )

    # Spike / drop vs last approved (september)
    sept = float(september_pay if september_pay is not None else emp.get("september_pay") or 0)
    base = float(base_salary if base_salary is not None else emp.get("base_salary") or 0)
    ai = RULES.get("aiCheck") or {}
    up = float(ai.get("upThreshold") or 0.5)
    down = float(ai.get("downThreshold") or 0.3)
    if sept > 0 and base > 0:
        ratio = base / sept
        if ratio >= 1 + up:
            out.append(
                {
                    "rule": "salary_spike",
                    "severity": "needs_confirmation",
                    "field": "Salary",
                    "owner": "hr",
                    "message": f"Salary up {ratio:.1f}x vs last approved — confirm or split bonus",
                }
            )
        elif ratio <= 1 - down:
            out.append(
                {
                    "rule": "salary_drop",
                    "severity": "needs_confirmation",
                    "field": "Salary",
                    "owner": "hr",
                    "message": f"Salary down significantly vs last approved — confirm",
                }
            )
        raise_thr = float(RULES.get("raiseWithoutSourceThreshold") or 0.1)
        if ratio >= 1 + raise_thr and ratio < 1 + up and not matched_source and not emp.get("matched_source"):
            out.append(
                {
                    "rule": "raise_without_source",
                    "severity": "info",
                    "field": "Salary",
                    "owner": "hr",
                    "message": f"Raise over {int(raise_thr * 100)}% without a matching source document",
                }
            )

    if exit_lwd and emp.get("hire_date"):
        try:
            if parse_date(exit_lwd) < parse_date(emp["hire_date"]):
                out.append(
                    {
                        "rule": "exit_before_start",
                        "severity": "blocking",
                        "field": "lastWorkingDay",
                        "owner": "hr",
                        "message": "Exit date cannot be before start date",
                    }
                )
        except ValueError:
            pass

    return out
