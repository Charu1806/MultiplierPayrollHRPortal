"""Issue Service — query, resolve, remind, overview rollups."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "data"))

from domain.calendar_rules import (  # noqa: E402
    CALCULATION,
    CUTOFF,
    NOV_CUTOFF,
    PAY_DATE,
    REVIEW_CLOSE,
    REVIEW_OPEN,
    parse_date,
    review_countdown,
    review_window_state,
    short_date,
)

DAVID_RETURN_DATE = parse_date("2026-10-29")
from domain.country_status import country_statuses  # noqa: E402
from domain.issues import can_approve, open_issues, sort_issues  # noqa: E402
from domain.config import cycle_config  # noqa: E402

from server.db.repositories import Store  # noqa: E402
from server.services import calendar as calendar_svc  # noqa: E402
from server.services import ai_explain  # noqa: E402
from server.services import rules as rules_svc  # noqa: E402
from server.services import validation as validation_svc  # noqa: E402

CYCLE = cycle_config()
COUNTRY_ORDER = tuple(CYCLE["countries"])


def _reminder_clock() -> str:
    from datetime import datetime

    return datetime.now().strftime("%H:%M")


def _reminder_label(as_of: str, clock: str, first: str) -> str:
    return f"Reminder emailed {short_date(as_of)}, {clock} · waiting for {first}"


def _issue_dto(store: Store, row: Dict[str, Any], as_of: Optional[str], include_ai: bool = False) -> Dict[str, Any]:
    emp = store.get_employee(row["employee_id"]) if row.get("employee_id") else None
    missing = store.missing_fields(row["employee_id"], as_of) if emp else []
    owned = rules_svc.split_owned(missing)
    deadline = row["deadline"]
    detail = row.get("detail")
    if emp and missing and as_of and parse_date(as_of) > CUTOFF:
        deadline = NOV_CUTOFF.isoformat()
        if parse_date(as_of) > PAY_DATE:
            detail = "Missed October pay. November pay at risk."
        else:
            detail = f"Moved to November · fix by {short_date(NOV_CUTOFF)}"
    # Owner label: employee-owned fields → employee name; else HR admin
    owner_label = row["owner"]
    if emp and owned["employee"] and not owned["hr"]:
        owner_label = f"{emp['name']} (employee)"
    elif emp and owned["employee"] and owned["hr"]:
        owner_label = f"{emp['name']} (employee) + HR admin"
    elif owned["hr"] or row.get("kind") == "pay_confirmation":
        owner_label = "HR admin"

    carried = bool(as_of and parse_date(as_of) > CUTOFF and missing)

    dto: Dict[str, Any] = {
        "id": row["id"],
        "title": row["title"],
        "severity": row["severity"],
        "kind": row.get("kind") or "missing_fields",
        "employeeId": row.get("employee_id"),
        "employeeName": emp["name"] if emp else None,
        "country": row["country"],
        "owner": owner_label,
        "carriedOver": carried,
        "deadline": deadline,
        "source": row["source"],
        "impact": row["impact"],
        "detail": detail,
        "status": row["status"],
        "resolvedAt": row.get("resolved_at"),
        "resolvedBy": row.get("resolved_by"),
        "resolutionLog": row.get("resolution_log"),
        "reminderSentOn": row.get("reminder_sent_on"),
        "reminderSentAt": row.get("reminder_sent_at"),
        "employeeOwnedFields": owned["employee"],
        "hrOwnedFields": owned["hr"],
        "missingFields": missing,
        "demoValues": rules_svc.demo_values(emp["id"], missing) if emp else {},
    }
    if row.get("reminder_sent_on") and emp:
        first = emp["name"].split()[0]
        clock = row.get("reminder_sent_at") or "00:00"
        dto["reminderLabel"] = _reminder_label(row["reminder_sent_on"], clock, first)
    else:
        dto["reminderLabel"] = None
    if include_ai:
        dto["aiNote"] = ai_explain.note_for_issue(row)
        if emp:
            dto["facts"] = _facts(store, emp, row)
    return dto


def _facts(store: Store, emp: Dict[str, Any], row: Dict[str, Any]) -> Dict[str, Any]:
    if row.get("kind") != "pay_confirmation":
        return {}
    sept = rules_svc.fmt_money(emp["currency"], emp["september_pay"])
    now = rules_svc.fmt_money(emp["currency"], emp["base_salary"])
    return {
        "submitted": f"{sept} → {now}",
        "payHistory": f"Last 12 months: flat at {sept}",
        "openSalaryHref": f"/people/{emp['id']}?panel=salary",
    }


def list_issues(
    store: Store,
    customer_id: str,
    status: Optional[str] = "open",
    as_of: Optional[str] = None,
) -> List[Dict[str, Any]]:
    cycle = store.get_current_cycle(customer_id)
    if not cycle:
        raise LookupError("cycle_not_found")
    if as_of:
        ensure_david_return_issue(store, as_of)
    rows = store.list_issues(cycle["id"], status=status, as_of=as_of)
    # James "Salary up 3x" is October Action needed only (deadline Oct 15). After cutoff it
    # belongs on Review (or November arrears if unsigned) — never November Action needed.
    if as_of and parse_date(as_of) > CUTOFF:
        rows = [
            r
            for r in rows
            if not (
                r.get("kind") == "pay_confirmation"
                or r.get("id") == "issue_002"
                or (r.get("title") or "").startswith("Salary up")
            )
        ]
    ordered = sort_issues(rows)
    return [_issue_dto(store, r, as_of, include_ai=False) for r in ordered]


def get_issue(store: Store, issue_id: str, as_of: Optional[str] = None) -> Dict[str, Any]:
    row = store.get_issue(issue_id, as_of=as_of)
    if not row:
        raise LookupError("issue_not_found")
    return _issue_dto(store, row, as_of, include_ai=True)


def changes_reminder(as_of: str) -> Optional[Dict[str, Any]]:
    from domain.calendar_rules import NOV_OPEN, cycle_dates

    d = parse_date(as_of)
    cd = cycle_dates(as_of)
    cut = parse_date(cd["inputFinalisation"])
    if d > cut:
        return None
    label = "November" if d >= NOV_OPEN else "October"
    return {
        "title": f"Any {label} changes?",
        "body": (
            f"Add new joiners, exits, one-time payments and salary changes by "
            f"**{short_date(cut)}** to include them in {label} pay. After that they move to the next cycle."
        ),
        "actions": [
            {"label": "Add employee", "href": "/people/add"},
            {"label": "Record exit", "href": "/people?hint=exit"},
            {"label": "Add one-time payment", "href": "/people?hint=one-time"},
        ],
    }


def ensure_david_return_issue(store: Store, as_of: str) -> None:
    """From Oct 29: bank returned David's October payment → Action needed."""
    if parse_date(as_of) < DAVID_RETURN_DATE:
        return
    if store.get_issue("issue_david_return"):
        return
    emp = store.get_employee("emp_david")
    if not emp:
        return
    cycle = store.get_current_cycle(emp["customer_id"])
    if not cycle:
        return
    # Mark bank as needing update
    existing = store.required_missing_fields("emp_david")
    if "Bank account" not in existing:
        store.conn.execute(
            "INSERT INTO employee_missing_fields (employee_id, field_name) VALUES (?, ?)",
            ("emp_david", "Bank account"),
        )
        store.conn.commit()
    store.insert_issue(
        {
            "id": "issue_david_return",
            "cycle_id": cycle["id"],
            "kind": "payment_returned",
            "title": "Payment returned – update bank details",
            "severity": "blocking",
            "employee_id": "emp_david",
            "country": "Germany",
            "owner": "HR admin",
            "deadline": NOV_CUTOFF.isoformat(),
            "source": "Bank return Oct 29",
            "impact": "Only David is held. The other employees were paid on time.",
            "detail": "Bank returned David's October payment on Oct 29 (Account closed). Update bank details to re-send.",
            "status": "open",
            "created_on": "2026-10-29",
        }
    )


def _badge_open_issues(store: Store, open_list: List[Any], as_of: str) -> List[Any]:
    """Before cutoff: all open actions. After: only November-deadline items."""
    if parse_date(as_of) <= CUTOFF:
        return list(open_list)
    nov = []
    for issue in open_list:
        deadline = issue.get("deadline")
        # DTO may already remap deadline; also treat post-cutoff open missing-data as Nov
        if deadline and parse_date(deadline) >= NOV_CUTOFF:
            nov.append(issue)
            continue
        emp_id = issue.get("employee_id") or issue.get("employeeId")
        if emp_id and store.missing_fields(emp_id, as_of):
            nov.append(issue)
    return nov


def _status_line(
    *,
    as_of: str,
    open_count: int,
    need_check: int,
    signed: bool,
    countdown: str,
    closed_without: bool = False,
    unapplied_n: int = 0,
) -> Dict[str, Any]:
    from domain.calendar_rules import NOV_OPEN, active_cycle_key, cycle_dates, review_bounds

    d = parse_date(as_of)
    cd = cycle_dates(as_of)
    cut_d = parse_date(cd["inputFinalisation"])
    open_d, close_d = review_bounds(as_of)
    cut = short_date(cut_d)
    open_lbl = short_date(open_d)
    close_lbl = short_date(close_d)
    fund = short_date(cd["fundingDue"]) if cd.get("fundingDue") else None
    base = {
        "openActions": open_count,
        "countdown": countdown,
        "signedOff": signed,
        "actionsHref": "/payroll/actions",
        "reviewHref": "/payroll/review",
        "kind": "info",
        "message": "",
        "href": "/payroll/actions",
    }

    # November (and later months): input-finalisation style status while before review
    if d >= NOV_OPEN:
        if signed:
            return {
                **base,
                "kind": "signed",
                "message": f"Payroll approved" + (f" · funding {fund}" if fund else ""),
                "href": "/payroll/overview",
            }
        if d <= cut_d:
            verb = "action needs you" if open_count == 1 else "actions need you"
            return {
                **base,
                "kind": "actions",
                "message": f"**{open_count} {verb}** before input finalisation on {cut} · {countdown}",
                "href": "/payroll/actions",
            }
        if d < open_d:
            return {
                **base,
                "kind": "calculating",
                "message": f"Inputs locked. Multiplier is calculating pay. **Review opens {open_lbl}.**",
                "href": "/payroll/overview",
            }
        if open_d <= d <= close_d:
            left = review_countdown(as_of)
            return {
                **base,
                "kind": "review",
                "message": (
                    f"**Review open · {need_check} line{'s' if need_check != 1 else ''} need your check** "
                    f"· closes {close_lbl} · {left}"
                ),
                "href": "/payroll/review",
            }
        return {
            **base,
            "kind": "info",
            "message": f"Review closed" + (f" · funding {fund}" if fund else ""),
            "href": "/payroll/overview",
        }

    # October
    if signed:
        return {
            **base,
            "kind": "signed",
            "message": f"Payroll approved · funding {fund}",
            "href": "/payroll/overview",
        }
    if d <= cut_d:
        verb = "action needs you" if open_count == 1 else "actions need you"
        return {
            **base,
            "kind": "actions",
            "message": f"**{open_count} {verb}** before input finalisation on {cut} · {countdown}",
            "href": "/payroll/actions",
        }
    if d < open_d:
        return {
            **base,
            "kind": "calculating",
            "message": f"Inputs locked. Multiplier is calculating pay. **Review opens {open_lbl}.**",
            "href": "/payroll/overview",
        }
    if open_d <= d <= close_d:
        left = review_countdown(as_of)
        return {
            **base,
            "kind": "review",
            "message": (
                f"**Review open · {need_check} line{'s' if need_check != 1 else ''} need your check** "
                f"· closes {close_lbl} · {left}"
            ),
            "href": "/payroll/review",
        }
    if closed_without:
        return {
            **base,
            "kind": "closed_unsigned",
            "message": (
                f"Review closed without sign-off · {unapplied_n} changes moved to November"
            ),
            "href": "/payroll/review",
        }
    return {
        **base,
        "kind": "info",
        "message": f"Review closed · funding {fund}",
        "href": "/payroll/overview",
    }


def overview(store: Store, customer_id: str, as_of: str) -> Dict[str, Any]:
    base = calendar_svc.cycle_view(store, customer_id, as_of)
    cycle = store.get_current_cycle(customer_id)
    assert cycle
    issues = store.list_issues(cycle["id"], as_of=as_of)
    if parse_date(as_of) > CUTOFF:
        issues = [
            r
            for r in issues
            if not (
                r.get("kind") == "pay_confirmation"
                or r.get("id") == "issue_002"
                or (r.get("title") or "").startswith("Salary up")
            )
        ]
    # Remap deadlines via DTO for post-cutoff November items
    open_raw = open_issues(issues)
    open_dtos = [_issue_dto(store, dict(r), as_of, include_ai=False) for r in open_raw]
    badge_list = _badge_open_issues(
        store,
        [
            {
                "deadline": d["deadline"],
                "employee_id": d.get("employeeId"),
                "country": d["country"],
                "status": d["status"],
                "severity": d.get("severity"),
            }
            for d in open_dtos
        ],
        as_of,
    )
    # Prefer matching by employee for country rollup of badge-counted issues
    if parse_date(as_of) <= CUTOFF:
        open_for_countries = open_raw
        open_count = len(open_raw)
    else:
        # After Oct cutoff: only November Action needed (not review-only lines like James)
        open_for_countries = badge_list
        open_count = len(badge_list)

    counts = store.count_by_country(customer_id, as_of=as_of)
    statuses = country_statuses(open_for_countries, COUNTRY_ORDER)

    open_by_country: Dict[str, int] = {c: 0 for c in COUNTRY_ORDER}
    for i in open_for_countries:
        c = i.get("country")
        if c in open_by_country:
            open_by_country[c] += 1

    country_codes = {"India": "IN", "UK": "UK", "Germany": "DE", "Brazil": "BR"}
    countries = [
        {
            "country": c,
            "code": country_codes.get(c, c[:2].upper()),
            "employeeCount": counts.get(c, 0),
            "status": statuses[c],
            "actionNeededCount": open_by_country[c],
            "href": f"/payroll/actions?country={country_codes.get(c, c)}"
            if open_by_country[c]
            else None,
        }
        for c in COUNTRY_ORDER
    ]

    from domain.calendar_rules import (
        NOV_OPEN,
        active_cycle_key,
        cycle_dates,
        unsigned_outcome_rows,
    )

    review_lines = store.review_lines(cycle["id"], as_of=as_of)
    need_check = len(review_lines)
    remaining = sum(1 for r in review_lines if not store.line_approval(r["id"], as_of))
    signed = bool(cycle.get("approved"))
    window = review_window_state(as_of)
    closed_without = window == "closed" and not signed
    unapplied_n = remaining if closed_without else 0
    cd = cycle_dates(as_of)
    in_november = parse_date(as_of) >= NOV_OPEN

    # November review lines (arrears) for up-next detail when unsigned
    from_oct_lines = 0
    if in_november and not signed:
        from_oct_lines = len(unsigned_outcome_rows())
    carried_n = len(rules_svc.carry_overs(store, customer_id, as_of)) if in_november else 0
    nov_need = from_oct_lines if in_november and not signed else need_check

    up_next: List[Dict[str, Any]] = [
        {
            "kind": "milestone",
            "title": "Input finalisation",
            "deadline": cd["inputFinalisation"],
            "detail": (
                f"{open_count} action{'s' if open_count != 1 else ''} open"
                + (f" ({carried_n} carried over from October)" if carried_n else "")
            ),
            "href": "/payroll/actions",
            "viewOnly": False,
        },
        {
            "kind": "milestone",
            "title": "Review window",
            "deadline": cd.get("reviewOpen"),
            "deadlineEnd": cd.get("reviewClose"),
            "detail": (
                f"{nov_need} line{'s' if nov_need != 1 else ''}"
                + (f" incl. {from_oct_lines} from October" if from_oct_lines else " need your check")
            ),
            "href": "/payroll/review",
            "viewOnly": False,
        },
    ]
    if cd.get("fundingDue"):
        up_next.append(
            {
                "kind": "milestone",
                "title": "Funding (finance)",
                "deadline": cd["fundingDue"],
                "detail": "Finance",
                "href": None,
                "viewOnly": True,
            }
        )
    up_next.append(
        {
            "kind": "milestone",
            "title": "Pay day",
            "deadline": cd["payDate"],
            "detail": f"{cd['label'].split()[0]} pay date",
            "href": None,
            "viewOnly": True,
        }
    )
    filtered: List[Dict[str, Any]] = []
    for u in up_next:
        end = u.get("deadlineEnd") or u["deadline"]
        if end and parse_date(end) >= parse_date(as_of):
            filtered.append(u)
    up_next = sorted(filtered, key=lambda x: x.get("deadline") or "9999")

    # Funding / submitted cards only during October cycle dates (not on November Overview)
    funding = None
    submitted = None
    if not in_november:
        if base["fundingVisible"]:
            funding = {
                "receivedOn": CYCLE["cycles"]["october"]["fundingDue"],
                "countries": [
                    {"country": c, "received": True, "label": "Funds received from finance ✓"}
                    for c in COUNTRY_ORDER
                ],
            }
        if base["submittedVisible"]:
            submitted = {"message": f"Payroll submitted for {len(COUNTRY_ORDER)} countries"}

    status = _status_line(
        as_of=as_of,
        open_count=open_count,
        need_check=nov_need if in_november else need_check,
        signed=signed if not in_november else False,  # November has its own sign-off later
        countdown=base["countdown"],
        closed_without=closed_without and not in_november,
        unapplied_n=unapplied_n,
    )

    # Compact October summary for November Overview
    october_summary = None
    if in_november:
        outcome = rules_svc.outcome(store, customer_id, max(as_of, "2026-10-28"))
        paid_n = (outcome or {}).get("paidOnTime", {}).get("count") or 0
        total_n = (outcome or {}).get("inRun") or sum(counts.values())
        arrears = sum(1 for r in unsigned_outcome_rows() if r["kind"] == "arrears") if not signed else 0
        recoveries = sum(1 for r in unsigned_outcome_rows() if r["kind"] == "recovery") if not signed else 0
        pay_lbl = short_date(CYCLE["cycles"]["october"]["payDate"])
        parts = [f"**October payroll** · paid {pay_lbl} · {paid_n} of {total_n} received pay"]
        if not signed and (arrears or recoveries):
            parts.append(
                f"review not signed off: {arrears} arrears, {recoveries} recoveries moved to November"
            )
        if carried_n:
            parts.append(f"{carried_n} employees carried over")
        # Green only when October closed cleanly (no unsigned review leftovers, no carry-overs)
        oct_signed = bool(CYCLE["cycles"]["october"].get("approved")) or signed
        # In this prototype October is never signed off when unsignedOutcomes apply
        tone = "ok" if arrears == 0 and recoveries == 0 and carried_n == 0 else "warn"
        october_summary = {
            "tone": tone,
            "message": " · ".join(parts),
            "href": "/payroll/review?cycle=october",
            "linkLabel": "View October summary",
            "signedOff": oct_signed and arrears == 0 and recoveries == 0,
            "paidCount": paid_n,
            "inRun": total_n,
            "arrears": arrears,
            "recoveries": recoveries,
            "carriedOver": carried_n,
        }

    return {
        **base,
        "statusLine": status,
        "reviewMeta": {
            "window": window,
            "needsCheck": nov_need if in_november else need_check,
            "remaining": remaining,
            "closedWithoutSignOff": closed_without and not in_november,
            "unappliedCount": unapplied_n if not in_november else from_oct_lines,
            "calculationDate": cd.get("calculation"),
            "reviewOpen": cd.get("reviewOpen"),
            "reviewClose": cd.get("reviewClose"),
            "cycleKey": cd["key"],
        },
        "countries": countries,
        "upNext": up_next,
        "changesReminder": changes_reminder(as_of),
        "outcome": None if in_november else rules_svc.outcome(store, customer_id, as_of),
        "funding": funding,
        "submitted": submitted,
        "octoberSummary": october_summary,
        "notInRun": rules_svc.not_in_run(store, customer_id, as_of),
        "carryOvers": rules_svc.carry_overs(store, customer_id, as_of) if in_november else [],
        "company": None,  # filled by route / state if needed
    }


def resolve(
    store: Store,
    issue_id: str,
    *,
    resolution: str,
    payload: Optional[Dict[str, Any]],
    actor: str,
    as_of: str,
    customer_id: str,
) -> Dict[str, Any]:
    row = store.get_issue(issue_id)
    if not row:
        raise LookupError("issue_not_found")
    if row["status"] != "open":
        return {"issue": get_issue(store, issue_id, as_of=as_of), "overview": overview(store, customer_id, as_of)}

    payload = payload or {}
    if resolution in ("fix_in_workday", "correct_amount"):
        raise PermissionError("not_built_in_prototype")

    log = f"Resolved via {resolution} by {actor}, {as_of}"
    if resolution in ("add_here", "add_details") and row.get("employee_id"):
        fields = payload.get("fields") or payload
        validation_svc.apply_missing_fields(
            store, row["employee_id"], fields, as_of=as_of, source="Edited by HR admin"
        )
        log = f"Details added in Payroll tab by {actor}, {as_of}"
        # apply_missing_fields already resolves when nothing is left
        refreshed = store.get_issue(issue_id)
        if refreshed and refreshed["status"] == "open":
            return {
                "issue": get_issue(store, issue_id, as_of=as_of),
                "overview": overview(store, customer_id, as_of),
                "partial": True,
            }
        return {
            "issue": get_issue(store, issue_id, as_of=as_of),
            "overview": overview(store, customer_id, as_of),
            "canApprove": approve_allowed(store, customer_id, as_of),
        }
    if resolution == "confirm":
        log = f"Confirmed by {actor}, {as_of}"
    if resolution == "salary_structure":
        log = f"Salary structure updated by {actor}, {as_of}"

    store.resolve_issue(issue_id, resolved_by=actor, resolved_at=as_of, resolution_log=log)
    return {
        "issue": get_issue(store, issue_id, as_of=as_of),
        "overview": overview(store, customer_id, as_of),
        "canApprove": approve_allowed(store, customer_id, as_of),
    }


def remind(
    store: Store,
    issue_id: str,
    *,
    as_of: str,
    customer_id: str,
    fields: Optional[List[str]] = None,
) -> Dict[str, Any]:
    from server.services import email_smtp
    from server.services import form_tokens

    row = store.get_issue(issue_id, as_of=as_of)
    if not row or not row.get("employee_id"):
        raise LookupError("issue_not_found")
    emp = store.get_employee(row["employee_id"])
    assert emp
    missing = fields or store.missing_fields(emp["id"], as_of)
    owned = rules_svc.split_owned(missing)["employee"]
    if not owned:
        raise ValueError("No employee-owned fields to remind about")
    label = rules_svc.sentence_fields(owned)
    first = emp["name"].split()[0]
    clock = _reminder_clock()
    token = form_tokens.create_form_token(
        store, employee_id=emp["id"], issue_id=issue_id, as_of=as_of
    )
    form_path = f"/form/{token}"
    form_url = f"{email_smtp.app_base_url()}{form_path}"
    to_addr = email_smtp.demo_personal_email(emp["name"], emp.get("personal_email"))

    from domain.calendar_rules import NOV_CUTOFF, cycle_dates

    cd = cycle_dates(as_of)
    cutoff_label = short_date(cd["inputFinalisation"] or NOV_CUTOFF)
    carried = parse_date(as_of) > CUTOFF
    subject = f"Add your {label} for payroll"
    if carried:
        subject = f"Add your {label} for payroll – missed October pay"

    field_reason = {
        "Tax ID": "Tax ID (Steuer-ID) · needed to calculate your German income tax",
        "CPF": "CPF · needed for Brazil payroll",
        "PAN": "PAN · needed for India tax",
        "Bank account": "Bank account · needed to pay you",
    }
    what_we_need = "; ".join(field_reason.get(f, f"{f} · needed for payroll") for f in owned)

    smtp_result: Dict[str, Any] = {"sent": False, "error": "smtp_not_configured"}
    if email_smtp.smtp_configured():
        smtp_result = email_smtp.send_reminder_email(
            to_address=to_addr,
            employee_name=emp["name"],
            fields_label=label,
            form_url=form_url,
            cutoff_label=cutoff_label,
        )

    store.update_issue(issue_id, reminder_sent_on=as_of, reminder_sent_at=clock)

    # Email body = what the employee would receive (no raw URL, no SMTP status)
    body = (
        f"Hi {first}, we need your {label} to pay you on time. Please add it by **{cutoff_label}**. "
        f"It takes about a minute: [add your details here].\n\n"
        f"What we need\n{what_we_need}\n\n"
        f"Your details go straight to payroll; you don't need to reply to this email."
    )
    ui_message = _reminder_label(as_of, clock, first)
    if not smtp_result.get("sent"):
        ui_message = f"{ui_message} · email not sent (SMTP not set up — see README)"

    reminder_kind = (
        "employee_reminder" if smtp_result.get("sent") else "employee_reminder_undelivered"
    )

    nid = store.add_notification(
        store.get_current_cycle(customer_id)["id"],
        send_date=as_of,
        recipient=emp["name"],
        recipient_employee_id=emp["id"],
        subject=subject,
        body_summary=body,
        actions=[{"action_text": f"Add {label}", "deadline": cd["inputFinalisation"], "issue_id": issue_id}],
        cta_label="Add my details →",
        # HR Notifications CTA opens employee profile with Missing details expanded.
        # The SMTP email still uses form_url so the employee can fill the form.
        cta_href=f"/people/{emp['id']}?panel=missing",
        kind=reminder_kind,
    )
    return {
        "issue": get_issue(store, issue_id, as_of=as_of),
        "notificationId": nid,
        "formUrl": form_url,
        "formPath": form_path,
        "emailSent": bool(smtp_result.get("sent")),
        "to": to_addr,
        "message": ui_message,
    }


def approve_allowed(store: Store, customer_id: str, as_of: Optional[str] = None) -> bool:
    cycle = store.get_current_cycle(customer_id)
    if not cycle:
        return False
    return can_approve(store.list_issues(cycle["id"], as_of=as_of))


def ensure_missing_fields_issue(store: Store, employee_id: str, as_of: str) -> None:
    """Deprecated alias — prefer inputs.sync_issues_from_findings / revalidate."""
    from server.services import inputs as inputs_svc

    emp = store.get_employee(employee_id)
    if not emp:
        return
    inputs_svc.revalidate(store, employee_id, as_of=as_of, customer_id=emp["customer_id"])
