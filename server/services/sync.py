"""Workday sync. HR source stays in hr_employees. The payroll snapshot updates here."""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from domain.calendar_rules import cycle_dates, parse_date, previous_cycle_dates, short_date
from domain.config import company_config, cycle_config

from server.db.repositories import Store
from server.services import clock as clock_svc
from server.services import funding as funding_svc

STEPS = [
    "Fetching changes from the connector",
    "Updating the payroll snapshot",
    "Calculating new employees, bonuses, and hikes",
    "Validating inputs",
    "Updating Action needed and Review",
]


class SyncLimitError(PermissionError):
    pass


class SyncFailed(RuntimeError):
    pass


def _actor(trigger: str) -> str:
    if trigger == "Final":
        return "System"
    admin = (company_config().get("admin") or {}).get("name") or "HR admin"
    return str(admin)


def _assignment(updated_at: str, as_of: str) -> str:
    """Current only when both the HR change and this sync are on or before the deadline."""
    cd = cycle_dates(as_of)
    deadline = parse_date(cd.get("inputDeadline") or cd["inputFinalisation"])
    received = parse_date(as_of)
    authored = parse_date(str(updated_at)[:10])
    if received <= deadline and authored <= deadline:
        return "current"
    return "next"


def _diff(store: Store, customer_id: str) -> List[Dict[str, Any]]:
    employees = {e["id"]: e for e in store.list_employees(customer_id)}
    changes: List[Dict[str, Any]] = []
    for hr in store.list_hr_employees():
        emp = employees.get(hr["employee_id"])
        if emp is None:
            continue
        base = float(emp["base_salary"])
        allowances = float(emp.get("allowances") or 0)
        unpaid = int(emp.get("unpaid_leave_days") or 0)
        kind = None
        summary = None
        if hr.get("status") and hr["status"] != emp.get("status") and hr["status"] == "Exited":
            kind, summary = "exited", "Exit recorded in HR"
        elif int(hr.get("unpaid_leave_days") or 0) != unpaid:
            kind, summary = "leave", "Unpaid leave changed in HR"
        elif abs(float(hr["base_salary"]) - base) > 0.5 or abs(float(hr.get("allowances") or 0) - allowances) > 0.5:
            kind, summary = "hike", "Compensation changed in HR"
        elif (hr.get("manager_name") or "") != (emp.get("manager_name") or ""):
            kind, summary = "other", "Manager changed in HR"
        if kind:
            changes.append({"employee_id": hr["employee_id"], "kind": kind, "summary": summary, "hr": hr})
    return changes


def _run_row(row: Dict[str, Any], *, idempotent: bool = False) -> Dict[str, Any]:
    return {
        "id": row["id"],
        "status": row["status"],
        "trigger": row["trigger"],
        "syncedAt": row["synced_at"],
        "actor": row["actor"],
        "added": row.get("added") or 0,
        "changed": row.get("changed") or 0,
        "exited": row.get("exited") or 0,
        "summary": row.get("summary"),
        "userInitiated": row.get("id") != "sync_seed",
        "steps": STEPS,
        "idempotent": idempotent,
    }


def _hikes_from_sync(store: Store, sync_id: str) -> List[Dict[str, Any]]:
    return [
        {
            "employee_id": change["employee_id"],
            "kind": change["kind"],
            "summary": change.get("summary"),
            "queue": "review",
        }
        for change in store.sync_changes_for(sync_id)
        if change.get("kind") == "hike"
    ]


def _present_run(
    store: Store,
    customer_id: str,
    as_of: str,
    row: Dict[str, Any],
    applied: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    if applied is None:
        applied = _hikes_from_sync(store, row["id"]) if row.get("id") else []
    activity = _cycle_activity(store, customer_id, as_of, applied)
    payload = _run_row(row)
    payload.update(_summary_from_activity(activity))
    payload["activity"] = activity
    return payload


def status(store: Store, customer_id: str, as_of: str) -> Dict[str, Any]:
    latest = store.latest_successful_sync(customer_id, as_of)
    limit = int((cycle_config().get("sync") or {}).get("maxPerDay") or 1)
    used = store.manual_syncs_on(customer_id, as_of[:10])
    last = _present_run(store, customer_id, as_of, latest) if latest else None
    if last:
        last.pop("activity", None)
    return {
        "lastSync": last,
        "manualUsedToday": used,
        "manualRemaining": max(0, limit - used),
        "maxPerDay": limit,
    }


def run_sync(
    store: Store,
    customer_id: str,
    as_of: str,
    *,
    trigger: str = "Manual",
    fail: bool = False,
) -> Dict[str, Any]:
    trigger = "Final" if str(trigger).lower() == "final" else "Manual"
    cycle = store.get_current_cycle(customer_id)
    if not cycle:
        raise LookupError("cycle_not_found")
    if trigger == "Final":
        existing = store.successful_final_sync(cycle["id"])
        if existing:
            result = _present_run(store, customer_id, as_of, existing)
            result["idempotent"] = True
            return result
    else:
        limit = int((cycle_config().get("sync") or {}).get("maxPerDay") or 1)
        if store.manual_syncs_on(customer_id, as_of[:10]) >= limit:
            raise SyncLimitError("Manual sync already used today")

    clock_svc.set_as_of(as_of)
    pending = _diff(store, customer_id)
    stamped = clock_svc.stamp(as_of)
    sync_id = f"sync_{uuid.uuid4().hex[:8]}"
    actor = _actor(trigger)
    conn = store.conn
    applied: List[Dict[str, Any]] = []
    summary = "+0 added, 0 changed, 0 exited"
    try:
        conn.commit()
        conn.execute("BEGIN")
        added = changed = exited = 0
        for item in pending:
            assignment = _assignment(item["hr"].get("updated_at") or as_of, as_of)
            conn.execute(
                """
                INSERT INTO sync_changes (sync_id, employee_id, kind, summary, cycle_assignment, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (sync_id, item["employee_id"], item["kind"], item["summary"], assignment, stamped),
            )
            if assignment != "current":
                continue
            hr = item["hr"]
            if item["kind"] == "exited":
                exited += 1
                conn.execute(
                    "UPDATE employees SET status = ? WHERE id = ?",
                    (hr.get("status") or "Exited", item["employee_id"]),
                )
            else:
                changed += 1
                conn.execute(
                    """
                    UPDATE employees
                    SET base_salary = ?, allowances = ?, unpaid_leave_days = ?, manager_name = ?,
                        changed_this_cycle = 1
                    WHERE id = ?
                    """,
                    (
                        hr["base_salary"],
                        hr.get("allowances") or 0,
                        hr.get("unpaid_leave_days") or 0,
                        hr.get("manager_name"),
                        item["employee_id"],
                    ),
                )
            applied.append(item)
        if fail:
            raise SyncFailed("simulated sync failure")
        summary = f"+{added} added, {changed} changed, {exited} exited"
        conn.execute(
            """
            INSERT INTO sync_runs (
              id, customer_id, cycle_id, trigger, status, synced_at, actor, added, changed, exited, summary
            ) VALUES (?, ?, ?, ?, 'success', ?, ?, ?, ?, ?, ?)
            """,
            (sync_id, customer_id, cycle["id"], trigger, stamped, actor, added, changed, exited, summary),
        )
        conn.commit()
    except Exception as exc:
        conn.rollback()
        if not isinstance(exc, SyncFailed) and fail:
            exc = SyncFailed(str(exc))
        try:
            conn.execute(
                """
                INSERT INTO sync_runs (
                  id, customer_id, cycle_id, trigger, status, synced_at, actor, added, changed, exited, summary, error
                ) VALUES (?, ?, ?, ?, 'failed', ?, ?, 0, 0, 0, NULL, ?)
                """,
                (sync_id, customer_id, cycle["id"], trigger, stamped, actor, str(exc)),
            )
            conn.commit()
        except Exception:
            conn.rollback()
        raise SyncFailed(str(exc)) from exc

    classified = _refresh_review(store, customer_id, as_of, applied)
    _funding_side_effects(store, customer_id, cycle["id"], as_of, trigger)
    row = store.latest_successful_sync(customer_id, as_of) or {
        "id": sync_id,
        "status": "success",
        "trigger": trigger,
        "synced_at": stamped,
        "actor": actor,
        "added": added,
        "changed": changed,
        "exited": exited,
        "summary": summary,
    }
    result = _present_run(store, customer_id, as_of, row, applied)
    result["classificationSource"] = classified
    store.conn.execute(
        "UPDATE sync_runs SET added = ?, changed = ?, exited = ?, summary = ? WHERE id = ?",
        (result["added"], result["changed"], result["exited"], result["summary"], result["id"]),
    )
    store.conn.commit()
    return result


def refresh_employee(store: Store, customer_id: str, employee_id: str, as_of: str) -> Dict[str, Any]:
    """Targeted refresh. Not a full sync, so it does not use the daily allowance."""
    hr = store.get_hr_employee(employee_id)
    emp = store.get_employee(employee_id)
    if not hr or not emp or emp["customer_id"] != customer_id:
        raise LookupError("employee_not_found")
    assignment = _assignment(hr.get("updated_at") or as_of, as_of)
    if assignment == "current":
        store.update_employee_fields(
            employee_id,
            base_salary=hr["base_salary"],
            allowances=hr.get("allowances") or 0,
            unpaid_leave_days=hr.get("unpaid_leave_days") or 0,
            manager_name=hr.get("manager_name"),
            changed_this_cycle=1,
        )
        _refresh_review(store, customer_id, as_of, [{"employee_id": employee_id, "kind": "hike", "hr": hr}])
    from server.services.validation import get_employee_detail

    detail = get_employee_detail(store, employee_id, as_of, customer_id)
    detail["cycleAssignment"] = assignment
    detail["refreshedAt"] = clock_svc.stamp(as_of)
    return detail


def _refresh_review(store: Store, customer_id: str, as_of: str, applied: List[Dict[str, Any]]) -> str:
    from server.services import llm as llm_svc
    from server.services import rules as rules_svc
    from server.services.review import ensure_edited_line

    source = "rules"
    for item in applied:
        decision = llm_svc.classify_sync_change(item["kind"], item.get("summary") or "")
        source = decision.get("source") or source
        item["queue"] = decision["queue"]
        if decision["queue"] != "review" or item["kind"] not in ("hike", "leave", "other", "bonus", "added"):
            continue
        emp = store.get_employee(item["employee_id"])
        if not emp:
            continue
        try:
            ensure_edited_line(
                store,
                emp,
                as_of=as_of,
                change_summary=item.get("summary") or "Synced from the connector",
                why_flagged=decision.get("reason") or "Synced from the connector – needs approval",
            )
            cycle = store.get_current_cycle(customer_id)
            if cycle:
                rules_svc.after_input_change(store, cycle, emp["id"], as_of=as_of, what="synced from the connector")
        except PermissionError:
            continue
    return source


def _previous_cutoff(as_of: str):
    cd = cycle_dates(as_of)
    opened = parse_date(cd.get("open") or as_of)
    year = opened.year
    month = opened.month - 1
    if month == 0:
        month = 12
        year -= 1
    return parse_date(f"{year:04d}-{month:02d}-22")


def _cycle_activity(store: Store, customer_id: str, as_of: str, applied: List[Dict[str, Any]]) -> Dict[str, Any]:
    """New joiners after the previous 22nd, plus bonuses and hikes to pay this month."""
    cd = cycle_dates(as_of)
    deadline = parse_date(cd.get("inputDeadline") or cd["inputFinalisation"])
    previous = _previous_cutoff(as_of)
    new_employees: List[Dict[str, Any]] = []
    bonuses: List[Dict[str, Any]] = []
    for emp in store.list_employees(customer_id, as_of=as_of):
        added = emp.get("date_added")
        if added:
            ad = parse_date(str(added)[:10])
            if previous < ad <= deadline:
                new_employees.append({"id": emp["id"], "name": emp["name"], "dateAdded": str(added)[:10]})
        for payment in store.one_time_payments(emp["id"], as_of):
            recorded = str(payment.get("recorded_on") or "")[:10]
            if not recorded:
                continue
            if not (previous < parse_date(recorded) <= deadline):
                continue
            label = payment.get("label") or payment.get("type") or "Payment"
            bonuses.append({"id": emp["id"], "name": emp["name"], "label": label})
    hikes = [
        {"id": item["employee_id"], "name": (store.get_employee(item["employee_id"]) or {}).get("name"), "summary": item.get("summary")}
        for item in applied
        if item.get("kind") == "hike" and item.get("queue") == "review"
    ]
    exits: List[Dict[str, Any]] = []
    seen_exits: set = set()
    as_of_day = parse_date(as_of[:10])
    for row in store.conn.execute(
        """
        SELECT e.id, e.name, x.recorded_on
        FROM exits x
        JOIN employees e ON e.id = x.employee_id
        WHERE e.customer_id = ?
        """,
        (customer_id,),
    ).fetchall():
        recorded = str(row["recorded_on"] or "")[:10]
        if not recorded or row["id"] in seen_exits:
            continue
        when = parse_date(recorded)
        if previous < when <= deadline and when <= as_of_day:
            seen_exits.add(row["id"])
            exits.append({"id": row["id"], "name": row["name"], "recordedOn": recorded})
    return {
        "previousCutoff": previous.isoformat(),
        "deadline": deadline.isoformat(),
        "newEmployees": new_employees,
        "bonuses": bonuses,
        "hikes": hikes,
        "exits": exits,
    }


def _summary_from_activity(activity: Dict[str, Any]) -> Dict[str, Any]:
    """Added, changed, and exited from the same cycle lists the sync dialog shows."""
    added_ids = {row["id"] for row in activity.get("newEmployees") or [] if row.get("id")}
    changed_ids = {
        row["id"]
        for row in (activity.get("bonuses") or []) + (activity.get("hikes") or [])
        if row.get("id") and row["id"] not in added_ids
    }
    exited = len({row["id"] for row in activity.get("exits") or [] if row.get("id")})
    added = len(added_ids)
    changed = len(changed_ids)
    summary = f"+{added} added, {changed} changed, {exited} exited"
    return {"added": added, "changed": changed, "exited": exited, "summary": summary}


def _funding_side_effects(store: Store, customer_id: str, cycle_id: str, as_of: str, trigger: str) -> None:
    people = funding_svc.employee_rows_for_snapshot(store, customer_id, as_of)
    payload = {**funding_svc.estimate(store, customer_id, as_of), "employees": people}
    if not store.funding_snapshot(cycle_id, "baseline"):
        funding_svc.store_snapshot(store, customer_id, cycle_id, "baseline", as_of, payload)
    if trigger != "Final":
        return
    funding_svc.store_snapshot(store, customer_id, cycle_id, "final", as_of, payload)
    if store.notification_by_kind(cycle_id, "funding_request"):
        return
    estimate = funding_svc.estimate(store, customer_id, as_of)
    store.add_notification(
        cycle_id,
        send_date=as_of[:10],
        recipient="Finance",
        subject=f"Funding request · {estimate['currency']} {estimate['toTransfer']:,.0f} to transfer",
        body_summary=(
            f"Required {estimate['currency']} {estimate['required']:,.0f}. "
            f"Available {estimate['currency']} {estimate['available']:,.0f}. "
            "Illustrative demo rates. Fees are not included."
        ),
        actions=[],
        cta_label="Open Overview",
        cta_href="/payroll/overview",
        kind="funding_request",
    )


def readiness(store: Store, customer_id: str, as_of: str) -> Dict[str, Any]:
    """Distinct employees. Need action, then need approval, then matched."""
    emps = [e for e in store.list_employees(customer_id, as_of=as_of) if e.get("changed_this_cycle")]
    cycle = store.get_current_cycle(customer_id)
    open_rows = store.list_issues(cycle["id"], status="open", as_of=as_of) if cycle else []
    action_ids = set()
    for row in open_rows:
        kind = row.get("kind") or ""
        if kind in ("missing_fields", "missing_data", "payment_returned"):
            if row.get("employee_id"):
                action_ids.add(row["employee_id"])
    need_action = []
    need_approval = []
    matched = []
    for emp in emps:
        if emp["id"] in action_ids:
            need_action.append(emp["id"])
            continue
        line = store.current_review_line(cycle["id"], emp["id"]) if cycle else None
        if line and not store.line_approval(line["id"], as_of):
            need_approval.append(emp["id"])
            continue
        matched.append(emp["id"])
    changed = len(emps)
    return {
        "changed": changed,
        "needAction": len(need_action),
        "needApproval": len(need_approval),
        "matched": len(matched),
        "reconciles": changed == len(need_action) + len(need_approval) + len(matched),
        "openIssues": len(open_rows),
    }


def change_breakdown(store: Store, customer_id: str, as_of: str) -> Dict[str, int]:
    added = exited = bonus = hike = leave = other = 0
    for emp in store.list_employees(customer_id, as_of=as_of):
        if not emp.get("changed_this_cycle") and not emp.get("date_added"):
            continue
        if emp.get("date_added"):
            added += 1
        if emp.get("status") == "Exited":
            exited += 1
        if int(emp.get("unpaid_leave_days") or 0) > 0:
            leave += 1
        if abs(float(emp.get("base_salary") or 0) - float(emp.get("september_pay") or 0)) > 0.5:
            hike += 1
        if store.one_time_payments(emp["id"], as_of):
            bonus += 1
        if emp.get("changed_this_cycle") and not any(
            (
                emp.get("date_added"),
                emp.get("status") == "Exited",
                int(emp.get("unpaid_leave_days") or 0) > 0,
                abs(float(emp.get("base_salary") or 0) - float(emp.get("september_pay") or 0)) > 0.5,
                store.one_time_payments(emp["id"], as_of),
            )
        ):
            other += 1
    return {"added": added, "exited": exited, "bonus": bonus, "hike": hike, "leave": leave, "other": other}


def payday_outcomes(store: Store, customer_id: str, as_of: str) -> Optional[Dict[str, Any]]:
    from domain.calendar_rules import cycle_dates, parse_date, prorate

    cd = cycle_dates(as_of)
    if parse_date(as_of) < parse_date(cd["payDate"]):
        return None
    from server.services.issue import ensure_david_return_issue

    ensure_david_return_issue(store, as_of)
    deadline = parse_date(cd.get("inputDeadline") or cd["inputFinalisation"])
    cycle = store.get_current_cycle(customer_id)
    paid: List[str] = []
    previous: List[Dict[str, Any]] = []
    missing: List[Dict[str, Any]] = []
    late: List[Dict[str, Any]] = []
    returned = 0
    returned_people: List[Dict[str, Any]] = []
    by_country: Dict[str, Dict[str, int]] = {
        name: {"paid": 0, "previous": 0, "missing": 0, "late": 0, "returned": 0}
        for name in ("India", "UK", "Germany", "Brazil")
    }

    def bump(country: str, key: str) -> None:
        row = by_country.setdefault(
            country or "Unknown",
            {"paid": 0, "previous": 0, "missing": 0, "late": 0, "returned": 0},
        )
        row[key] += 1

    for emp in store.list_employees(customer_id, as_of=as_of):
        if emp["id"] == "emp_david":
            issue = store.get_issue("issue_david_return", as_of=as_of)
            created = str(issue.get("created_on") or "")[:10] if issue else ""
            if issue and issue.get("status") == "open" and (not created or as_of[:10] >= created):
                returned += 1
                returned_people.append(
                    {
                        "id": emp["id"],
                        "name": emp["name"],
                        "country": emp.get("country"),
                        "reason": "payment returned",
                    }
                )
                bump(emp.get("country") or "", "returned")
                continue
        added = emp.get("date_added")
        if added and parse_date(added) > deadline:
            amount = prorate(float(emp.get("base_salary") or 0), added)["amount"]
            late.append({"id": emp["id"], "name": emp["name"], "prorated": amount, "country": emp.get("country")})
            bump(emp.get("country") or "", "late")
            continue
        open_issue = None
        if cycle:
            for row in store.list_issues(cycle["id"], status="open", as_of=as_of):
                if row.get("employee_id") == emp["id"] and (row.get("kind") or "") in (
                    "missing_fields",
                    "missing_data",
                    "payment_returned",
                ):
                    open_issue = row
                    break
        if open_issue:
            missing.append(
                {
                    "id": emp["id"],
                    "name": emp["name"],
                    "field": open_issue.get("title"),
                    "owner": open_issue.get("owner"),
                    "issueId": open_issue.get("id"),
                    "country": emp.get("country"),
                }
            )
            bump(emp.get("country") or "", "missing")
            continue
        line = store.current_review_line(cycle["id"], emp["id"]) if cycle else None
        if line and not store.line_approval(line["id"], as_of):
            previous.append(
                {"id": emp["id"], "name": emp["name"], "reason": "Approval missing", "country": emp.get("country")}
            )
            bump(emp.get("country") or "", "previous")
            continue
        paid.append(emp["id"])
        bump(emp.get("country") or "", "paid")
    eligible = len(paid) + len(previous) + len(missing) + returned
    country_outcomes = {}
    for country, row in by_country.items():
        country_outcomes[country] = {
            "paid": row["paid"],
            "of": row["paid"] + row["previous"] + row["missing"] + row["returned"],
            "paidPreviousSalary": {
                "count": row["previous"],
                "href": "/payroll/review" if row["previous"] else None,
            },
            "missingInputs": {
                "count": row["missing"],
                "href": "/payroll/actions" if row["missing"] else None,
            },
            "addedAfterCutoff": {"count": row["late"], "href": "/people" if row["late"] else None},
            "paymentReturned": {
                "count": row["returned"],
                "href": "/payroll/actions" if row["returned"] else None,
            },
        }
    return {
        "simulated": True,
        "paidSuccessfully": {"count": len(paid), "of": eligible, "employeeIds": paid},
        "paidPreviousSalary": {
            "count": len(previous),
            "employees": previous,
            "href": "/payroll/review" if previous else None,
        },
        "missingInputs": {
            "count": len(missing),
            "employees": missing,
            "href": _missing_inputs_href(missing),
        },
        "addedAfterCutoff": {"count": len(late), "employees": late},
        "paymentReturned": {
            "count": returned,
            "employees": returned_people,
            "href": "/payroll/actions" if returned else None,
        },
        "byCountry": country_outcomes,
    }


def _month_end(day: date) -> date:
    if day.month == 12:
        nxt = date(day.year + 1, 1, 1)
    else:
        nxt = date(day.year, day.month + 1, 1)
    return nxt - timedelta(days=1)


def _cycle_pay_summary(
    store: Store, customer_id: str, cycle: Dict[str, Any], snap: str
) -> Optional[Dict[str, Any]]:
    """Paid, missed, and movement for one cycle, frozen at `snap`."""
    pay = parse_date(cycle["payDate"])
    if parse_date(snap) < pay:
        return None
    outcomes = payday_outcomes(store, customer_id, snap)
    if not outcomes:
        return None
    added, left = _joined_and_left(store, customer_id, _payroll_period_start(pay), pay)
    late = outcomes["addedAfterCutoff"]["employees"]
    previous_salary = outcomes["paidPreviousSalary"]
    missing = outcomes["missingInputs"]
    returned = int(outcomes["paymentReturned"]["count"])
    paid = outcomes["paidSuccessfully"]
    month = str(cycle["label"]).split()[0]
    pay_label = short_date(cycle["payDate"])
    message = (
        f"**{month} payroll** · paid {pay_label} · {paid['count']} of {paid['of']} received pay · "
        f"{previous_salary['count']} at previous salary · {missing['count']} missing inputs · "
        f"{len(late)} added after cutoff · {returned} returned · "
        f"{len(added)} added · {len(left)} left"
    )
    missed = previous_salary["count"] + missing["count"] + len(late) + returned
    by_country = {}
    for country, row in (outcomes.get("byCountry") or {}).items():
        by_country[country] = {
            "paid": row["paid"],
            "of": row["of"],
            "paidPreviousSalary": row["paidPreviousSalary"],
            "missingInputs": row["missingInputs"],
            "addedAfterCutoff": row["addedAfterCutoff"],
            "paymentReturned": row["paymentReturned"],
            "added": {"count": 0, "href": None},
            "left": {"count": 0, "href": None},
        }
    for person in added:
        country = person.get("country") or "Unknown"
        slot = by_country.setdefault(country, _empty_country_summary())
        slot["added"]["count"] += 1
        slot["added"]["href"] = _people_href([p for p in added if p.get("country") == country])
    for person in left:
        country = person.get("country") or "Unknown"
        slot = by_country.setdefault(country, _empty_country_summary())
        slot["left"]["count"] += 1
        slot["left"]["href"] = _people_href([p for p in left if p.get("country") == country])
    return {
        "tone": "warn" if missed else "ok",
        "message": message,
        "month": month,
        "payDateLabel": pay_label,
        "paid": paid["count"],
        "of": paid["of"],
        "paidPreviousSalary": {"count": previous_salary["count"], "href": previous_salary.get("href")},
        "missingInputs": {"count": missing["count"], "href": missing.get("href")},
        "addedAfterCutoff": {"count": len(late), "href": _people_href(late)},
        "paymentReturned": {"count": returned, "href": _returned_href(store, customer_id, snap) if returned else None},
        "added": {"count": len(added), "href": _people_href(added)},
        "left": {"count": len(left), "href": _people_href(left)},
        "byCountry": by_country,
        "href": None,
        "linkLabel": None,
    }


def payroll_close_highlight(store: Store, customer_id: str, as_of: str) -> Optional[Dict[str, Any]]:
    """The just-paid cycle, shown only on the 30th and 31st of its pay month."""
    day = parse_date(as_of)
    if day.day not in (30, 31):
        return None
    cycle = cycle_dates(as_of)
    pay = parse_date(cycle["payDate"])
    if day < pay or (day.year, day.month) != (pay.year, pay.month):
        return None
    return _cycle_pay_summary(store, customer_id, cycle, day.isoformat())


def previous_payrolls(store: Store, customer_id: str, as_of: str) -> List[Dict[str, Any]]:
    """Cycles that closed before this month. Each is frozen at the end of its pay month."""
    day = parse_date(as_of)
    month_start = date(day.year, day.month, 1)
    rows: List[Dict[str, Any]] = []
    cursor = as_of
    seen: set = set()
    while True:
        prev = previous_cycle_dates(cursor)
        active = cycle_dates(cursor)
        if prev["key"] in seen or prev["key"] == active["key"]:
            break
        seen.add(prev["key"])
        pay = parse_date(prev["payDate"])
        if pay < month_start:
            snap = _month_end(pay)
            if snap > day:
                snap = day
            summary = _cycle_pay_summary(store, customer_id, prev, snap.isoformat())
            if summary:
                rows.append(summary)
        cursor = prev.get("open") or prev["payDate"]
    return rows


def _empty_country_summary() -> Dict[str, Any]:
    return {
        "paid": 0,
        "of": 0,
        "paidPreviousSalary": {"count": 0, "href": None},
        "missingInputs": {"count": 0, "href": None},
        "addedAfterCutoff": {"count": 0, "href": None},
        "paymentReturned": {"count": 0, "href": None},
        "added": {"count": 0, "href": None},
        "left": {"count": 0, "href": None},
    }


def _payroll_period_start(pay: date) -> date:
    """The 30th of the month before pay date. October's period opens Sep 30 and closes Oct 29."""
    month = pay.month - 1
    year = pay.year
    if month == 0:
        month = 12
        year -= 1
    day = 30
    while day > 27:
        try:
            return date(year, month, day)
        except ValueError:
            day -= 1
    return date(year, month, day)


def _joined_and_left(store: Store, customer_id: str, start: date, end: date) -> tuple:
    """Joiners and leavers from the 30th through this cycle's pay date."""
    added: List[Dict[str, Any]] = []
    for emp in store.list_employees(customer_id, as_of=end.isoformat()):
        raw = emp.get("date_added")
        if not raw:
            continue
        when = parse_date(str(raw)[:10])
        if start <= when <= end:
            added.append({"id": emp["id"], "name": emp["name"], "country": emp.get("country")})
    left: List[Dict[str, Any]] = []
    seen: set = set()
    for row in store.conn.execute(
        """
        SELECT e.id, e.name, e.country, x.recorded_on
        FROM exits x
        JOIN employees e ON e.id = x.employee_id
        WHERE e.customer_id = ?
        """,
        (customer_id,),
    ).fetchall():
        recorded = str(row["recorded_on"] or "")[:10]
        if not recorded or row["id"] in seen:
            continue
        when = parse_date(recorded)
        if start <= when <= end:
            seen.add(row["id"])
            left.append({"id": row["id"], "name": row["name"], "country": row["country"]})
    return added, left


def _people_href(rows: List[Dict[str, Any]]) -> Optional[str]:
    if not rows:
        return None
    if len(rows) == 1 and rows[0].get("id"):
        return f"/people/{rows[0]['id']}"
    return "/people"


def _returned_href(store: Store, customer_id: str, as_of: str) -> Optional[str]:
    cycle = store.get_current_cycle(customer_id)
    if not cycle:
        return "/payroll/actions"
    hits = [
        row
        for row in store.list_issues(cycle["id"], status="open", as_of=as_of)
        if (row.get("kind") or "") == "payment_returned"
    ]
    if len(hits) == 1 and hits[0].get("id"):
        return f"/payroll/actions?issue={hits[0]['id']}"
    return "/payroll/actions" if hits else None


def _missing_inputs_href(missing: List[Dict[str, Any]]) -> Optional[str]:
    """One person opens their missing-details fix. Several open Action needed."""
    if not missing:
        return None
    if len(missing) == 1 and missing[0].get("id"):
        return f"/people/{missing[0]['id']}?panel=missing#missing-details"
    return "/payroll/actions"
