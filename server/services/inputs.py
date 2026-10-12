"""Unified dynamic inputs pipeline — any employee, any date, no seed-name special cases.

Stages: Received → Read document → Mapped → Validated → Cycle assigned → Stored → Issues updated
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "data"))

from domain.calendar_rules import (  # noqa: E402
    backdated_arrears_months,
    cycle_containing_date,
    cycle_dates,
    cycle_for_new_input,
    first_pay_cycle,
    next_cycle_dates,
    parse_date,
    prorate,
    review_window_state,
    short_date,
)
from domain.config import rules_config  # noqa: E402

from server.db.repositories import Store  # noqa: E402
from server.services import clock as clock_svc  # noqa: E402
from server.services import rules as rules_svc  # noqa: E402
from server.services import validation as validation_svc  # noqa: E402

RULES = rules_config()
CURRENCY = {"India": "₹", "UK": "£", "Germany": "€", "Brazil": "R$"}
COUNTRY_NET_DEFAULT = {"India": 100000, "UK": 4000, "Germany": 4200, "Brazil": 15000}


def _slug(store: Store, name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    candidate = f"emp_{base}"
    n = 2
    while store.get_employee(candidate):
        candidate = f"emp_{base}_{n}"
        n += 1
    return candidate


def confirmation_message(cycle: Dict[str, Any], *, prior_cutoff: Optional[str] = None) -> str:
    pay = short_date(cycle["payDate"])
    label = cycle["label"]
    msg = f"Will be paid in **{label}** ({pay})"
    if prior_cutoff:
        active = cycle_for_new_input(prior_cutoff)
        # If landing cycle is next, mention prior cutoff
        if active["key"] != cycle["key"]:
            cut = short_date(active["inputFinalisation"])
            month = active["label"].split()[0]
            msg += f" · inputs for {month} closed {cut}"
    return msg


def arrears_lines(monthly: float, hire: str, pay_cycle: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Backdated months before first pay. The hire month is prorated when they start mid-month."""
    hd = parse_date(hire)
    lines: List[Dict[str, Any]] = []
    for row in backdated_arrears_months(hire, pay_cycle):
        year_s, month_s = str(row["monthKey"]).split("-")
        year, month = int(year_s), int(month_s)
        prorated = hd.year == year and hd.month == month and hd.day > 1
        if prorated:
            info = prorate(monthly, hire)
            lines.append(
                {
                    "label": f"{row['label']} salary · prorated",
                    "amount": float(info["amount"]),
                    "prorated": True,
                    "month": row["label"],
                    "daysWorked": info["daysWorked"],
                    "daysInMonth": info["daysInMonth"],
                    "formula": info["formula"],
                }
            )
        else:
            lines.append(
                {
                    "label": f"Backdated pay · {row['label']}",
                    "amount": float(monthly),
                    "prorated": False,
                    "month": row["label"],
                }
            )
    return lines


def reconcile_prorated_arrears(store: Store, emp: Dict[str, Any]) -> None:
    """Rewrite hire-month arrears that were stored as a full month."""
    hire = emp.get("hire_date")
    monthly = float(emp.get("base_salary") or 0)
    if not hire or monthly <= 0:
        return
    try:
        hd = parse_date(hire)
    except ValueError:
        return
    if hd.day <= 1:
        return
    info = prorate(monthly, hire)
    month_label = hd.strftime("%B %Y")
    target_label = f"{month_label} salary · prorated"
    target = float(info["amount"])
    for row in store.one_time_payments(emp["id"]):
        if (row.get("source") or "") != "Inputs pipeline" or (row.get("type") or "") != "Arrears":
            continue
        label = row.get("label") or ""
        if month_label not in label:
            continue
        if label == target_label and abs(float(row["amount"]) - target) < 0.01:
            continue
        store.update_one_time_payment(row["id"], amount=target, label=target_label)


def _journey_steps(
    source: str, *, as_of: Optional[str] = None, extra: Optional[List[Tuple[str, str]]] = None
) -> List[Dict[str, Any]]:
    now = clock_svc.stamp(as_of)
    steps = [
        ("received", f"Received from {source}"),
        ("validated", "Validated"),
        ("cycle", "Cycle assigned"),
        ("stored", "Stored"),
    ]
    if extra:
        # insert after received
        steps = [steps[0]] + list(extra) + steps[1:]
    return [
        {"key": k, "label": lab, "at": now, "source": source}
        for k, lab in steps
    ]


def preview_employee(body: Dict[str, Any], *, as_of: str) -> Dict[str, Any]:
    """Dry-run cycle assignment + findings for Add employee confirmation."""
    country = body.get("country") or "India"
    hire = body.get("hireDate") or body.get("startDate") or as_of
    monthly = float(body.get("monthlyNet") or body.get("baseSalary") or COUNTRY_NET_DEFAULT.get(country, 0))
    input_cycle = cycle_for_new_input(as_of)
    pay_cycle = first_pay_cycle(hire, input_cycle)
    pr = prorate(monthly, hire) if parse_date(hire).day > 1 else None
    arrears = backdated_arrears_months(hire, pay_cycle)
    flags: List[str] = []
    if arrears:
        flags.append("backdated")
    if parse_date(pay_cycle.get("open") or pay_cycle["payDate"]) > parse_date(as_of) and pay_cycle["key"] != input_cycle["key"]:
        if parse_date(hire) > parse_date(as_of):
            flags.append("scheduled")
    findings = validation_svc.findings_for_new_hire(
        country=country,
        manager=body.get("manager") or body.get("managerName"),
        hire_date=hire,
        salary=monthly,
        field_values=body.get("fields") or {},
    )
    prior = None
    if pay_cycle["key"] != input_cycle["key"] or parse_date(as_of) > parse_date(input_cycle["inputFinalisation"]):
        prior = as_of
    return {
        "cycle": pay_cycle,
        "inputCycle": input_cycle,
        "prorate": pr,
        "arrearsMonths": arrears,
        "flags": flags,
        "findings": findings,
        "confirmationMessage": confirmation_message(pay_cycle, prior_cutoff=as_of if pay_cycle["key"] != cycle_for_new_input(as_of)["key"] or parse_date(as_of) > parse_date(cycle_for_new_input(as_of)["inputFinalisation"]) else None),
    }


def _pay_edit_landing_cycle(
    store: Store, emp: Dict[str, Any], as_of: str
) -> Tuple[Dict[str, Any], bool]:
    """Cycle placement for HR pay edits (context.md §HR edits)."""
    current = cycle_dates(as_of)
    if parse_date(as_of) <= parse_date(current["inputFinalisation"]):
        return current, True

    db_cycle = store.get_current_cycle(emp["customer_id"])
    signoff = store.active_signoff(db_cycle["id"], as_of) if db_cycle else None
    reopened = bool(
        signoff and signoff.get("reopened_on") and (not as_of or signoff["reopened_on"] <= as_of)
    )
    payroll_approved = bool(
        (db_cycle and db_cycle.get("approved"))
        or (signoff and not reopened)
    )
    window = review_window_state(as_of)
    if payroll_approved or window == "closed":
        landing = next_cycle_dates(as_of)
        return landing, False
    if window == "open" and db_cycle and store.current_review_line(db_cycle["id"], emp["id"]):
        return current, True
    return next_cycle_dates(as_of), False


def preview_pay_edit(
    store: Store, employee_id: str, body: Dict[str, Any], *, as_of: str
) -> Dict[str, Any]:
    emp = store.get_employee(employee_id)
    if not emp:
        raise LookupError("employee_not_found")
    try:
        new_base = float(body.get("baseSalary", emp["base_salary"]))
        allowances = float(body.get("allowances", emp.get("allowances") or 0))
        unpaid = int(body.get("unpaidLeaveDays", emp.get("unpaid_leave_days") or 0))
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid salary values") from exc

    landing, included = _pay_edit_landing_cycle(store, emp, as_of)
    pay_month = str(landing.get("label") or "October").split()[0]

    salary = rules_svc.SalaryStructure(
        base=new_base,
        allowances=allowances,
        unpaid_leave_days=unpaid,
        one_time_payments=rules_svc.one_time_payments(store, employee_id, as_of),
        tax_rate=rules_svc.tax_rate(emp["country"]),
        cycle=pay_month,
    )
    check = rules_svc.ai_check_payload(emp, salary.gross)
    month = pay_month if included else (landing.get("label") or pay_month).split()[0]
    confirmation = f"Included in {month} pay" if included else f"Moves to {month}"

    out: Dict[str, Any] = {
        "net": salary.net,
        "gross": salary.gross,
        "tax": salary.tax,
        "cycle": landing,
        "confirmationMessage": confirmation,
        "includedInCurrent": included,
    }
    if check:
        out["aiCheck"] = check
    return out


def preview_one_time(body: Dict[str, Any], *, as_of: str, employee: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    cycle = cycle_for_new_input(as_of)
    flags: List[str] = []
    letter_month = body.get("payMonth") or body.get("letterPayMonth")
    if letter_month:
        try:
            letter_cycle = cycle_containing_date(letter_month) if "-" in str(letter_month) else None
            if letter_cycle and parse_date(letter_cycle["payDate"]) < parse_date(cycle["payDate"]):
                flags.append("late_input")
        except (ValueError, TypeError):
            pass
    findings: List[Dict[str, Any]] = []
    if flags and "late_input" in flags:
        findings.append(
            {
                "rule": "late_input",
                "severity": "info",
                "field": "payMonth",
                "owner": "hr",
                "message": f"Late input: letter says earlier month, paid in {cycle['label']} as arrears",
            }
        )
    active = cycle_for_new_input(as_of)
    # Show closed prior if we're already past cutoff into next
    prior_note = as_of
    return {
        "cycle": cycle,
        "flags": flags,
        "findings": findings,
        "confirmationMessage": confirmation_message(cycle, prior_cutoff=prior_note),
        "employeeName": (employee or {}).get("name"),
    }


def sync_issues_from_findings(
    store: Store,
    emp: Dict[str, Any],
    findings: List[Dict[str, Any]],
    *,
    as_of: str,
    deadline: str,
) -> None:
    """Upsert/resolve missing-data and validation issues from findings."""
    cycle = store.get_current_cycle(emp["customer_id"])
    if not cycle:
        return
    missing_fields = [
        f["field"]
        for f in findings
        if f.get("rule") == "required_missing" and f.get("field")
    ]
    # Don't wipe seed-tracked fields for existing employees — only update from findings
    existing_tracked = store.required_missing_fields(emp["id"])
    if emp.get("is_new"):
        to_flag = list(dict.fromkeys(missing_fields))
    else:
        # Keep intersection: still-missing among already tracked + any new finding fields
        to_flag = [f for f in existing_tracked if f in missing_fields or f not in {x["field"] for x in findings if x.get("rule") == "required_missing"}]
        # Simpler: fields that were tracked and still missing in findings
        still = set(missing_fields)
        to_flag = [f for f in existing_tracked if f in still]
        for f in missing_fields:
            if f not in to_flag:
                to_flag.append(f)
    store.set_required_missing_fields(emp["id"], to_flag)

    # Build / refresh a single blocking issue for missing fields
    open_issues = store.list_issues(cycle["id"], status="open", as_of=as_of)
    existing = next(
        (
            i
            for i in open_issues
            if i.get("employee_id") == emp["id"] and i.get("kind") in ("missing_data", "missing_fields")
        ),
        None,
    )
    if to_flag:
        emp_owned = set(RULES.get("employeeOwnedFields") or [])
        emp_fields = [f for f in to_flag if f in emp_owned]
        hr_fields = [f for f in to_flag if f not in emp_owned]
        title_bits = []
        if emp_fields:
            title_bits.append(", ".join(emp_fields))
        if hr_fields:
            title_bits.append(", ".join(hr_fields))
        title = "Missing " + " and ".join(title_bits) if title_bits else "Missing required fields"
        owner = "Employee" if emp_fields and not hr_fields else ("HR admin" if hr_fields and not emp_fields else "HR admin")
        pay_missing = rules_svc.payment_missing_fields(store, emp, as_of)
        blocks_pay = bool(pay_missing)
        severity = "blocking" if blocks_pay else "needs_confirmation"
        if blocks_pay:
            impact = f"{emp['name']} cannot be paid until {', '.join(pay_missing)} are added."
        else:
            impact = f"{', '.join(to_flag)} still needed. This does not hold {emp['name']}'s pay."
        payload = {
            "kind": "missing_data",
            "title": title,
            "severity": severity,
            "employee_id": emp["id"],
            "country": emp["country"],
            "owner": owner,
            "deadline": deadline,
            "source": "Validation",
            "impact": impact,
            "detail": title,
            "status": "open",
            "created_on": as_of,
        }
        if existing:
            store.update_issue(existing["id"], **{k: v for k, v in payload.items() if k != "created_on"})
        elif emp.get("is_new"):
            # Prefer issue_004 for first India joiner slot (seed/demo contract); else stable miss id
            iid = "issue_004" if not store.get_issue("issue_004") else f"issue_miss_{emp['id']}"
            if iid.startswith("issue_miss_") and store.get_issue(iid):
                iid = f"issue_miss_{emp['id']}"
            prior = store.get_issue(iid)
            if prior:
                store.update_issue(iid, **{k: v for k, v in payload.items() if k != "created_on"})
                if prior.get("status") != "open":
                    store.reopen_issue(iid)
            else:
                # Use missing_fields kind for demo contract compatibility with Action needed
                payload["kind"] = "missing_fields"
                store.insert_issue({"id": iid, "cycle_id": cycle["id"], **payload})
        # Existing seeded employees keep their seed issues; don't invent issue_miss_* duplicates
    elif existing:
        store.resolve_issue(
            existing["id"],
            resolved_by="system",
            resolved_at=as_of,
            resolution_log=f"All required fields present, {as_of}",
        )


def revalidate(store: Store, employee_id: str, *, as_of: str, customer_id: str) -> Dict[str, Any]:
    from server.services.validation import get_employee_detail

    emp = store.get_employee(employee_id)
    if not emp or emp["customer_id"] != customer_id:
        raise LookupError("employee_not_found")
    findings = validation_svc.validate_employee(store, emp, as_of)
    input_cycle = cycle_for_new_input(as_of)
    hire = emp.get("hire_date") or as_of
    pay_cycle = first_pay_cycle(hire, input_cycle)
    sync_issues_from_findings(store, emp, findings, as_of=as_of, deadline=pay_cycle["inputFinalisation"])
    return get_employee_detail(store, employee_id, as_of, customer_id)


def create_employee(
    store: Store,
    customer_id: str,
    body: Dict[str, Any],
    *,
    as_of: str,
) -> Tuple[Dict[str, Any], bool]:
    from server.services.validation import get_employee_detail

    name = body.get("name") or body.get("legalName")
    if not name:
        raise ValueError("name_required")
    country = body.get("country") or body.get("workLocation") or "India"
    if country not in CURRENCY:
        raise ValueError("unsupported_country")

    email = (body.get("workEmail") or body.get("email") or "").strip() or None
    existing = store.get_employee_by_email(customer_id, email) if email else None
    if existing is None and body.get("id"):
        existing = store.get_employee(body["id"])
        if existing and existing["customer_id"] != customer_id:
            existing = None
    if existing:
        updates: Dict[str, Any] = {"name": name}
        role = body.get("role") or body.get("jobTitle")
        if role:
            updates["role"] = role
        if body.get("hireDate"):
            updates["hire_date"] = body["hireDate"]
        manager = body.get("manager") or body.get("managerName")
        if manager:
            updates["manager_name"] = manager
        store.update_employee_fields(existing["id"], **updates)
        dto = revalidate(store, existing["id"], as_of=as_of, customer_id=customer_id)
        return dto, False

    hire = body.get("hireDate") or body.get("startDate") or as_of
    monthly = float(body.get("monthlyNet") or body.get("baseSalary") or COUNTRY_NET_DEFAULT[country])
    input_cycle = cycle_for_new_input(as_of)
    pay_cycle = first_pay_cycle(hire, input_cycle)
    pr = prorate(monthly, hire)
    manager = body.get("manager") or body.get("managerName")
    emp_id = body.get("id") or _slug(store, name)

    store.insert_employee(
        {
            "id": emp_id,
            "customer_id": customer_id,
            "name": name,
            "role": body.get("role") or body.get("jobTitle") or "Team Member",
            "country": country,
            "currency": CURRENCY[country],
            "september_pay": monthly,
            "base_salary": monthly,
            "date_added": as_of,
            "is_new": 1,
            "status": "Active",
            "source": "HR tool",
            "work_email": email,
            "hire_date": hire,
            "manager_name": manager,
            "notes": body.get("notes") or "Added via inputs pipeline",
            "changed_this_cycle": 1,
        }
    )

    # Field values from body
    fields = dict(body.get("fields") or {})
    if manager:
        fields.setdefault("Manager", manager)
    fields.setdefault("Start date", hire)
    fields.setdefault("Salary", str(monthly))
    for k, v in fields.items():
        if v is not None and str(v).strip():
            store.add_field_value(emp_id, k, str(v), source="HR tool", as_of=as_of)

    emp = store.get_employee(emp_id)
    findings = validation_svc.validate_employee(store, emp, as_of)
    sync_issues_from_findings(
        store, emp, findings, as_of=as_of, deadline=pay_cycle["inputFinalisation"]
    )

    steps = _journey_steps("HR tool", as_of=as_of)
    store.add_journey_events(emp_id, steps)

    # Missed months before first pay. The start month is prorated; later missed months stay full.
    for row in arrears_lines(monthly, hire, pay_cycle):
        store.add_one_time_payment(
            emp_id,
            type_="Arrears",
            label=row["label"],
            amount=row["amount"],
            recorded_on=as_of,
            source="Inputs pipeline",
            document_name=None,
        )

    dto = get_employee_detail(store, emp_id, as_of, customer_id)
    dto["_inputMeta"] = {
        "cycle": pay_cycle,
        "inputCycle": input_cycle,
        "prorate": pr,
        "findings": findings,
        "confirmationMessage": confirmation_message(pay_cycle, prior_cutoff=as_of),
        "flags": (["backdated"] if backdated_arrears_months(hire, pay_cycle) else [])
        + (["scheduled"] if pay_cycle["key"] != input_cycle["key"] and parse_date(hire) > parse_date(as_of) else []),
    }
    return dto, True


def add_one_time_payment(
    store: Store,
    employee_id: str,
    body: Dict[str, Any],
    *,
    as_of: str,
    customer_id: str,
) -> Dict[str, Any]:
    from server.services.validation import get_employee_detail

    emp = store.get_employee(employee_id)
    if not emp or emp["customer_id"] != customer_id:
        raise LookupError("employee_not_found")
    type_ = body.get("type") or "Bonus"
    amount = float(body.get("amount") or 0)
    if amount <= 0:
        raise ValueError("amount must be > 0")
    label = body.get("label") or type_
    cycle = cycle_for_new_input(as_of)
    flags: List[str] = []
    letter_month = body.get("payMonth") or body.get("letterPayMonth")
    if letter_month:
        try:
            lc = cycle_containing_date(letter_month) if re.match(r"\d{4}-\d{2}", str(letter_month)) else None
            if lc and parse_date(lc["payDate"]) < parse_date(cycle["payDate"]):
                flags.append("late_input")
        except (ValueError, TypeError):
            pass

    dup = rules_svc.duplicate_payment_check(store, employee_id, type_=type_, amount=amount, as_of=as_of)
    if dup and not body.get("force"):
        raise rules_svc.DuplicatePaymentWarning(dup)

    store.add_one_time_payment(
        employee_id,
        type_=type_,
        label=label,
        amount=amount,
        recorded_on=as_of,
        source=body.get("source") or "Edited by HR admin",
        document_name=body.get("documentName"),
    )
    store.update_employee_fields(employee_id, edited_by_you=1, changed_this_cycle=1)

    # Review line only once calculation has started for the landing cycle
    calc = cycle.get("calculation") or cycle["inputFinalisation"]
    if parse_date(as_of) >= parse_date(calc):
        from server.services.review import ensure_edited_line

        why = "One-time payment – needs approval"
        if "late_input" in flags:
            why = "Late input – needs approval"
        if dup and body.get("force"):
            why = f"Possible duplicate – {dup.get('message', '')}"
        ensure_edited_line(
            store,
            emp,
            as_of=as_of,
            change_summary=f"{type_} {rules_svc.fmt_money(emp['currency'], amount)}",
            why_flagged=why,
            matching_source=body.get("documentName") or "No supporting document",
        )
    else:
        # Defer: mark for next review build via changed_this_cycle; line created at calculation
        pass

    # Generic: resolve open pay_confirmation if base already matches september (bonus split done)
    _maybe_resolve_pay_confirmation(store, emp, as_of)

    db_cycle = store.get_current_cycle(customer_id)
    rules_svc.after_input_change(store, db_cycle, employee_id, as_of=as_of, what="one-time payment")

    dto = get_employee_detail(store, employee_id, as_of, customer_id)
    dto["_inputMeta"] = {
        "cycle": cycle,
        "flags": flags,
        "confirmationMessage": confirmation_message(cycle, prior_cutoff=as_of),
    }
    return dto


def resolve_open_pay_confirmation(
    store: Store,
    emp: Dict[str, Any],
    as_of: str,
    *,
    resolution_log: str,
    matching_source: str,
    change_summary: Optional[str] = None,
) -> bool:
    """Close an open salary-spike issue and record what proved the new pay."""
    cycle = store.get_current_cycle(emp["customer_id"])
    if not cycle:
        return False
    issues = store.list_issues(cycle["id"], status="open", as_of=as_of)
    pc = next(
        (
            i
            for i in issues
            if i.get("employee_id") == emp["id"] and i.get("kind") == "pay_confirmation"
        ),
        None,
    )
    if not pc:
        return False
    store.resolve_issue(
        pc["id"],
        resolved_by="HR admin",
        resolved_at=as_of,
        resolution_log=resolution_log,
    )
    line = store.current_review_line(cycle["id"], emp["id"])
    if line:
        fields: Dict[str, Any] = {"matching_source": matching_source}
        if change_summary:
            fields["change_summary"] = change_summary
        store.update_review_line(line["id"], **fields)
    return True


def _maybe_resolve_pay_confirmation(store: Store, emp: Dict[str, Any], as_of: str) -> None:
    """If employee has open pay_confirmation and base≈september with a bonus OTP, resolve it."""
    sept = float(emp.get("september_pay") or 0)
    base = float(emp.get("base_salary") or 0)
    otps = store.one_time_payments(emp["id"], as_of)
    has_bonus = any((p.get("type") == "Bonus") or ("bonus" in (p.get("label") or "").lower()) for p in otps)
    if not (has_bonus and abs(base - sept) < 0.5):
        return
    bonus = next((p for p in otps if p.get("type") == "Bonus" or "bonus" in (p.get("label") or "").lower()), None)
    amt = rules_svc.fmt_money(emp["currency"], float(bonus["amount"])) if bonus else ""
    resolve_open_pay_confirmation(
        store,
        emp,
        as_of,
        resolution_log=f"Salary structure split (base + bonus) by HR admin, {as_of}",
        matching_source=f"Bonus letter, one-off {amt}".strip(),
        change_summary=f"{rules_svc.fmt_money(emp['currency'], sept)} + {amt} bonus".strip(),
    )


def record_exit(
    store: Store,
    employee_id: str,
    body: Dict[str, Any],
    *,
    as_of: str,
    customer_id: str,
) -> Dict[str, Any]:
    from server.services.validation import get_employee_detail

    emp = store.get_employee(employee_id)
    if not emp or emp["customer_id"] != customer_id:
        raise LookupError("employee_not_found")
    lwd = body.get("lastWorkingDay") or body.get("last_working_day") or as_of
    if not lwd:
        raise ValueError("lastWorkingDay is required")
    lwd_cycle = cycle_containing_date(lwd)
    # An exit is an input. After that month's lock-in date, this month is on hold and pay lands next month.
    fnf_cycle = cycle_for_new_input(as_of)
    flags = ["late_exit"] if fnf_cycle["key"] != lwd_cycle["key"] else []

    hire = emp.get("hire_date")
    if hire and parse_date(lwd) < parse_date(hire):
        raise ValueError("Exit date cannot be before start date")

    store.add_exit(
        employee_id,
        {
            "last_working_day": lwd,
            "reason": body.get("reason"),
            "notice_pay": float(body.get("noticePay") or 0),
            "severance": float(body.get("severance") or 0),
            "leave_encashment_days": int(body.get("leaveEncashmentDays") or 0),
            "recoveries": float(body.get("recoveries") or 0),
        },
        recorded_on=as_of,
        source="Edited by HR admin",
    )
    exit_row = store.get_exit(employee_id, as_of)
    status = rules_svc.employee_status(emp, exit_row, as_of)
    # The employees.status check allows Exited; the API still says Removed once the last day has passed.
    stored_status = "Exited" if status == "Removed" else status
    store.update_employee_fields(employee_id, status=stored_status, edited_by_you=1, changed_this_cycle=1)
    if exit_row:
        from server.services.review import upsert_exit_review_line

        upsert_exit_review_line(store, emp, exit_row, as_of)
    db_cycle = store.get_current_cycle(customer_id)
    rules_svc.after_input_change(store, db_cycle, employee_id, as_of=as_of, what="exit recorded")

    dto = get_employee_detail(store, employee_id, as_of, customer_id)
    dto["_inputMeta"] = {
        "cycle": fnf_cycle,
        "flags": flags,
        "confirmationMessage": confirmation_message(fnf_cycle, prior_cutoff=as_of),
    }
    return dto


def undo_exit(
    store: Store,
    employee_id: str,
    *,
    as_of: str,
    customer_id: str,
) -> Dict[str, Any]:
    from server.services.review import delete_exit_review_line
    from server.services.validation import get_employee_detail

    emp = store.get_employee(employee_id)
    if not emp or emp["customer_id"] != customer_id:
        raise LookupError("employee_not_found")
    if not store.get_exit(employee_id, as_of):
        raise ValueError("This employee has no exit to undo")
    delete_exit_review_line(store, emp, as_of)
    store.delete_exits(employee_id)
    other_edits = abs(float(emp.get("base_salary") or 0) - float(emp.get("september_pay") or 0)) > 0.5
    other_edits = other_edits or bool(store.one_time_payments(employee_id, as_of))
    updates: Dict[str, Any] = {"status": "Active"}
    if not other_edits:
        updates["edited_by_you"] = 0
        updates["changed_this_cycle"] = 0
    store.update_employee_fields(employee_id, **updates)
    return get_employee_detail(store, employee_id, as_of, customer_id)
