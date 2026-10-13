"""Notification Service — computed HR emails + stored employee reminders (SMTP is in email_smtp)."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "data"))

from domain.calendar_rules import (  # noqa: E402
    CUTOFF,
    countdown_text,
    cycle_dates,
    days_until_cutoff,
    parse_date,
    previous_cycle_dates,
    short_date,
)
from domain.config import seed_config  # noqa: E402
from domain.issues import open_issues  # noqa: E402
from domain.notifications import emails_visible_on  # noqa: E402

from server.db.repositories import Store  # noqa: E402
from server.services import rules as rules_svc
from server.services.email_smtp import employee_details_mail  # noqa: E402

TEMPLATES = seed_config()["emailTemplates"]


_SAVED_REMIND_LABEL = re.compile(
    r"^Add your (?P<label>.+?)(?:"
    r" for payroll\b.*|"
    r" or this payment will be missed"
    r")$"
)


def _details_deadline(send_date: str) -> tuple:
    cycle = cycle_dates(send_date)
    month = str(cycle.get("label") or "This").split()[0]
    deadline = short_date(parse_date(cycle["payDate"]).replace(day=15))
    return deadline, month


def present_employee_reminder(row: Dict[str, Any]) -> tuple:
    """Show saved missing-details mail with the deadline and the month's payroll."""
    subject = row.get("subject") or ""
    body = row.get("body_summary") or ""
    match = _SAVED_REMIND_LABEL.match(subject)
    if not match or not row.get("send_date"):
        return subject, body
    deadline, month = _details_deadline(row["send_date"])
    first = str(row.get("recipient") or "there").split()[0]
    return employee_details_mail(
        first=first,
        label=match.group("label"),
        deadline=deadline,
        month=month,
    )


def _delivery_from_kind(kind: Optional[str]) -> Optional[str]:
    if kind == "employee_reminder_undelivered":
        return "not_sent_smtp_missing"
    if kind == "employee_reminder":
        return "sent"
    if kind == "payroll_on_track_undelivered":
        return "not_sent_smtp_missing"
    if kind == "payroll_on_track":
        return "sent"
    return None


def _stored_for_cycles(store: Store, customer_id: str, as_of: str, channel: str) -> List[Dict[str, Any]]:
    """Stored notifications for the active cycle and the one before it."""
    current = cycle_dates(as_of)
    previous = previous_cycle_dates(as_of)
    cycle_ids: List[str] = []
    for c in (current, previous):
        cid = c.get("id")
        if cid and cid not in cycle_ids:
            cycle_ids.append(cid)
    rows: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for cycle_id in cycle_ids:
        for n in store.list_notifications(cycle_id):
            if n["id"] in seen:
                continue
            seen.add(n["id"])
            if n.get("channel", "email") != channel:
                continue
            rows.append(n)
    return rows


def _open_actions(store: Store, cycle_id: str, as_of: str) -> List[Dict[str, Any]]:
    return list(open_issues(store.list_issues(cycle_id, as_of=as_of)))


def _action_rows(store: Store, issues: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows = []
    for i, issue in enumerate(issues, start=1):
        emp = store.get_employee(issue["employee_id"]) if issue.get("employee_id") else None
        who = emp["name"] if emp else issue["country"]
        rows.append(
            {
                "action_text": f"{issue['title']} — {who}",
                "deadline": issue["deadline"],
                "issue_id": issue["id"],
                "sort_order": i,
            }
        )
    return rows


def _reminder_days(send_date: str) -> set:
    """Input and review reminders on days 1, 10, 15, 20, 21, and 22, through the deadline."""
    from domain.config import cycle_config

    cd = cycle_dates(send_date)
    deadline = parse_date(cd["inputFinalisation"])
    start = parse_date(cd.get("open") or f"{deadline.year}-{deadline.month:02d}-01")
    configured = (cycle_config().get("reminders") or {}).get("daysOfMonth") or [1, 10, 15, 20, 21, 22]
    days = set()
    for day in configured:
        try:
            candidate = deadline.replace(day=int(day))
        except ValueError:
            continue
        if start <= candidate <= deadline:
            days.add(candidate.isoformat())
    return days


def _input_deadline_mail(send_date: str, *, open_actions: int, review_lines: int) -> tuple:
    """One mail for missing actions, new inputs, and review. Sent on the configured days."""
    days_left = days_until_cutoff(send_date)
    deadline = parse_date(cycle_dates(send_date)["inputFinalisation"])
    long = f"{deadline.day} {deadline.strftime('%B')}"
    if days_left <= 0:
        subject = "Last day to add inputs and finish review"
        close = f"today, {long}"
    elif days_left == 1:
        subject = "1 day left to add inputs and finish review"
        close = f"on {long}"
    else:
        subject = f"{days_left} days left to add inputs and finish review"
        close = f"on {long}"
    body = (
        f"Inputs and review close {close}. "
        f"{open_actions} open actions and {review_lines} review lines are still outstanding. "
        "Please resolve missing actions, add any new employees, salary changes, and bonuses, and finish review, on or before that date. "
        "If this work is not completed, affected employees may have all or part of their pay moved to the next cycle."
    )
    return subject, body


def _input_deadline_follow_up(send_date: str) -> tuple:
    from domain.calendar_rules import cycle_dates

    deadline = cycle_dates(send_date)["inputFinalisation"]
    actions = [
        {
            "actionText": "Resolve actions in Action needed",
            "deadline": deadline,
            "issueId": None,
            "href": "/payroll/actions",
        },
        {
            "actionText": "Finish review",
            "deadline": deadline,
            "issueId": None,
            "href": "/payroll/review",
        },
    ]
    policy = {
        "label": "Payroll input policy",
        "href": "/payroll/input-policy",
        "note": "Demo",
    }
    cta = {"label": "Open Action needed", "href": "/payroll/actions"}
    return actions, policy, cta


def _fill(template: str, **kwargs: Any) -> str:
    out = template
    for k, v in kwargs.items():
        out = out.replace("{" + k + "}", str(v))
    return out


def _signed_off(store: Store, cycle: Dict[str, Any], as_of: str) -> bool:
    if cycle.get("approved"):
        return True
    signoff = store.active_signoff(cycle["id"], as_of)
    if not signoff:
        return False
    reopened = bool(signoff.get("reopened_on") and signoff["reopened_on"] <= as_of)
    return not reopened


def _remaining_lines(store: Store, cycle_id: str, as_of: str) -> int:
    lines = store.review_lines(cycle_id, as_of=as_of)
    return sum(1 for r in lines if not store.line_decision(r["id"], as_of))


def _computed(store: Store, customer_id: str, as_of: str) -> List[Dict[str, Any]]:
    cycle = store.get_current_cycle(customer_id)
    assert cycle
    issues = _open_actions(store, cycle["id"], as_of)
    outcome = rules_svc.outcome(store, customer_id, as_of)
    carry = rules_svc.carry_overs(store, customer_id, as_of)
    on_time = outcome["paidOnTime"]["count"] if outcome else 0
    moved = outcome["movedToNovember"]["count"] if outcome else len(carry)
    signed = _signed_off(store, cycle, as_of)
    remaining = _remaining_lines(store, cycle["id"], as_of)
    need_check = len(store.review_lines(cycle["id"], as_of=as_of))

    computed: List[Dict[str, Any]] = []
    from domain.calendar_rules import cycle_dates as _cycle_dates

    cd_now = _cycle_dates(as_of)
    funding_day = cd_now.get("fundingRequest") or cd_now.get("fundingDue")
    submitted_day = cd_now.get("submitted")
    pay_day = cd_now.get("payDate")
    extra_templates = []
    for day in sorted(_reminder_days(as_of)):
        extra_templates.append(
            {
                "id": f"notif_cycle_{day}",
                "date": day,
                "kind": "actions_open",
                "subject": "",
                "summary": "",
                "recipient": "HR admin",
            }
        )
    if funding_day:
        extra_templates.append(
            {
                "id": "notif_funding_request",
                "date": funding_day,
                "kind": "funding_request_scheduled",
                "subject": "Add funds for payroll",
                "summary": "Finance funding request for this cycle.",
                "recipient": "Finance",
            }
        )
    if submitted_day:
        extra_templates.append(
            {
                "id": f"notif_submitted_{submitted_day}",
                "date": submitted_day,
                "kind": "payroll_submitted",
                "subject": "Payroll submitted",
                "summary": "",
                "recipient": "HR admin",
            }
        )
    if pay_day:
        extra_templates.append(
            {
                "id": f"notif_paid_{pay_day}",
                "date": pay_day,
                "kind": "paid",
                "subject": "Payroll paid: {on_time} on time, {moved} moved to the next cycle",
                "summary": f"Pay date {pay_day} outcome.",
                "recipient": "HR admin",
            }
        )
    for t in list(TEMPLATES) + extra_templates:
        if parse_date(t["date"]) > parse_date(as_of):
            continue
        kind = t["kind"]
        # Conditional templates
        if kind in ("review_reminder", "review_closes_today") and signed:
            continue
        if kind == "signed_off_funding" and not signed:
            continue
        if kind == "closed_without_signoff" and signed:
            continue
        # Old review_ready removed from seed; skip if any leftover
        if kind == "review_ready":
            continue

        subject = t["subject"]
        actions = _action_rows(store, issues)
        cta = {"label": "Open Action needed", "href": "/payroll/actions"}
        body = t["summary"]
        policy = None

        if kind in ("review_open", "review_reminder", "review_closes_today", "inputs_locked"):
            continue
        if kind == "funding_due":
            due = cycle_dates(t["date"]).get("fundingRequest") or cycle_dates(t["date"]).get("fundingDue")
            if due and t["date"] != due:
                continue
        if kind == "paid":
            paid_on = cycle_dates(t["date"]).get("payDate")
            if paid_on and t["date"] != paid_on:
                continue
        if kind == "actions_open" or kind == "blocking_open":
            if not str(t["id"]).startswith("notif_cycle_"):
                continue
            if t["date"] not in _reminder_days(t["date"]):
                continue
            if not issues and remaining == 0:
                continue
            subject, body = _input_deadline_mail(t["date"], open_actions=len(issues), review_lines=remaining)
            actions, policy, cta = _input_deadline_follow_up(t["date"])
        elif kind == "funding_request_scheduled":
            actions = []
            cta = {"label": "Open Overview", "href": "/payroll/overview"}
            closed = cycle_dates(t["date"]).get("inputFinalisation")
            body = (
                f"Inputs and review closed on {closed}. "
                f"Please add funds by {t['date']}. Illustrative demo rates. Fees are not included."
            )
        elif kind == "payroll_submitted":
            actions = []
            cta = {"label": "Open Overview", "href": "/payroll/overview"}
            pay_on = cycle_dates(t["date"]).get("payDate")
            subject = "Payroll submitted"
            body = f"Payroll was submitted on {t['date']}. Pay day is {pay_on}."
        elif kind == "signed_off_funding":
            actions = []
            cta = {"label": "Open Overview", "href": "/payroll/overview"}
        elif kind == "closed_without_signoff":
            subject = _fill(subject, n=remaining)
            actions = []
            cta = {"label": "Open Review & approve", "href": "/payroll/review"}
        elif kind == "paid":
            subject = _fill(subject, on_time=on_time, moved=moved)
            actions = []
            cta = {"label": "Open Overview", "href": "/payroll/overview"}
        elif kind == "november_open":
            subject = _fill(subject, n=len(carry))
            actions = [
                {
                    "actionText": f"{c['name']} — {c.get('reason') or 'carry-over'}",
                    "deadline": "2026-11-15",
                    "issueId": None,
                }
                for c in carry
            ]
            cta = {"label": "Open Action needed", "href": "/payroll/actions"}
        elif kind == "november_review_open":
            from_oct = remaining  # unapproved October lines become Nov review items when unsigned
            subject = _fill(subject, n=need_check + from_oct, from_oct=from_oct)
            actions = []
            cta = {"label": "Open Review & approve", "href": "/payroll/review"}
        elif kind in ("funds_received", "funding_due"):
            actions = []
            cta = {"label": "Open Overview", "href": "/payroll/overview"}

        if kind != "november_open":
            computed.append(
                {
                    "id": t["id"],
                    "send_date": t["date"],
                    "recipient": t["recipient"],
                    "channel": "email",
                    "subject": subject,
                    "body_summary": body,
                    "action_count": len(actions) if isinstance(actions, list) else 0,
                    "actions": [
                        {
                            "actionText": a.get("actionText") or a.get("action_text"),
                            "deadline": a.get("deadline"),
                            "issueId": a.get("issueId") or a.get("issue_id"),
                            "href": a.get("href"),
                        }
                        for a in (actions or [])
                    ],
                    "policy": policy,
                    "cta": cta,
                    "kind": kind,
                    "computed": True,
                }
            )
    computed.extend(_persona_reports(store, customer_id, as_of))
    return computed


def _month_day(cycle: Dict[str, Any], day: int) -> str:
    pay = parse_date(cycle["payDate"])
    return pay.replace(day=day).isoformat()


_MISS_KINDS = {"missing_fields", "missing_data"}


def _miss_snapshot(store: Store, customer_id: str, as_of: str) -> Dict[str, Dict[str, Any]]:
    """Missing details miss pay. An open review change does not; old base pay is used."""
    cycle = store.get_current_cycle(customer_id)
    by_country: Dict[str, Dict[str, Any]] = {}

    def bucket(country: str) -> Dict[str, Any]:
        row = by_country.setdefault(
            country, {"actions": 0, "approvals": 0, "people": set(), "miss": set(), "wrong": set()}
        )
        return row

    if not cycle:
        return {}
    for issue in _open_actions(store, cycle["id"], as_of):
        if (issue.get("kind") or "missing_fields") not in _MISS_KINDS:
            continue
        country = issue.get("country") or "Unknown"
        row = bucket(country)
        row["actions"] += 1
        if issue.get("employee_id"):
            row["people"].add(issue["employee_id"])
            row["miss"].add(issue["employee_id"])
    for line in store.review_lines(cycle["id"], as_of=as_of):
        if store.line_decision(line["id"], as_of):
            continue
        country = line.get("country") or "Unknown"
        row = bucket(country)
        row["approvals"] += 1
        if line.get("employee_id"):
            row["people"].add(line["employee_id"])
            row["wrong"].add(line["employee_id"])
    return by_country


_EMPTY_MISS = {"actions": 0, "approvals": 0, "people": set(), "miss": set(), "wrong": set()}
_IGNORE = "You can ignore this if nothing is still open."
_IGNORE_FUNDS = "You can ignore this if funds are already in."


def _will_miss(store: Store, customer_id: str, as_of: str) -> Dict[str, Dict[str, Any]]:
    """People who will miss this cycle because details are missing."""
    cycle = store.get_current_cycle(customer_id)
    people: Dict[str, Dict[str, Any]] = {}
    if not cycle:
        return people

    def slot(emp_id: str, country: str, name: str) -> Dict[str, Any]:
        row = people.setdefault(
            emp_id,
            {"id": emp_id, "name": name or "Employee", "country": country or "Unknown", "reasons": []},
        )
        return row

    for issue in _open_actions(store, cycle["id"], as_of):
        emp_id = issue.get("employee_id")
        if not emp_id:
            continue
        if (issue.get("kind") or "missing_fields") not in _MISS_KINDS:
            continue
        emp = store.get_employee(emp_id) or {}
        row = slot(emp_id, issue.get("country") or emp.get("country") or "", emp.get("name") or "")
        title = issue.get("title")
        if title and title not in row["reasons"]:
            row["reasons"].append(title)
    return people


def _wrong_pay(store: Store, customer_id: str, as_of: str) -> Dict[str, Dict[str, Any]]:
    """Open review changes. These people are paid, but not at the new amount."""
    cycle = store.get_current_cycle(customer_id)
    people: Dict[str, Dict[str, Any]] = {}
    if not cycle:
        return people
    for line in store.review_lines(cycle["id"], as_of=as_of):
        if store.line_decision(line["id"], as_of):
            continue
        emp_id = line.get("employee_id")
        if not emp_id:
            continue
        emp = store.get_employee(emp_id) or {}
        people[emp_id] = {
            "id": emp_id,
            "name": emp.get("name") or line.get("employee_name") or "Employee",
            "country": line.get("country") or emp.get("country") or "Unknown",
            "reasons": ["change not approved, old base pay is used"],
        }
    return people


def _forecast_text(store: Store, customer_id: str, as_of: str, country: Optional[str] = None) -> str:
    """How many are on track to be paid, and who will miss, with why."""
    missed = list(_will_miss(store, customer_id, as_of).values())
    wrong = list(_wrong_pay(store, customer_id, as_of).values())
    if country:
        missed = [person for person in missed if person["country"] == country]
        wrong = [person for person in wrong if person["country"] == country]
    missed_ids = {person["id"] for person in missed}
    roster = [
        emp
        for emp in store.list_employees(customer_id, as_of=as_of)
        if (country is None or emp.get("country") == country) and emp.get("status") != "Exited"
    ]
    on_track = sum(1 for emp in roster if emp["id"] not in missed_ids)
    miss_n = len(missed)
    wrong_n = len(wrong)
    scope = "" if country else " across all countries"
    paid_line = (
        f"{on_track} will be paid{scope}. {miss_n} will miss payment because details are missing. "
        f"{wrong_n} will get old base payment."
    )
    lines = [
        f"{person['name']} — missing details"
        for person in sorted(missed, key=lambda person: (person["country"], person["name"]))
    ]
    lines.extend(
        f"{person['name']} — will get old base payment"
        for person in sorted(wrong, key=lambda person: (person["country"], person["name"]))
    )
    if not lines:
        return f"{paid_line}\n\nNo one will miss payment."
    return paid_line + "\n\n" + "\n".join(lines)


def _actual_text(outcomes: Dict[str, Any], country: Optional[str] = None) -> str:
    """How many were paid, and who missed, with why."""
    by_country = outcomes.get("byCountry") or {}
    reasons = (
        ("missingInputs", "missing details, missed payment"),
        ("paidPreviousSalary", "got old base payment"),
        ("addedAfterCutoff", "added after the window closed"),
        ("paymentReturned", "payment was returned by the bank"),
    )

    def named(country_name: str) -> List[str]:
        lines = []
        for key, label in reasons:
            for person in (outcomes.get(key) or {}).get("employees") or []:
                if person.get("country") != country_name or not person.get("name"):
                    continue
                lines.append(f"{person['name']} — {label}")
        return lines

    if country:
        row = by_country.get(country) or {}
        paid = int(row.get("paid") or 0)
        lines = named(country)
        missed_lines = [line for line in lines if "missed payment" in line or "missing details" in line]
        old_base_lines = [line for line in lines if "old base payment" in line]
        if not lines:
            return f"{paid} were paid. No one missed payment."
        parts = [f"{paid} were paid."]
        if missed_lines:
            parts.append(f"{len(missed_lines)} missed payment because details were missing.")
        if old_base_lines:
            parts.append(f"{len(old_base_lines)} got old base payment.")
        return " ".join(parts) + "\n\n" + "\n".join(lines)

    paid = int((outcomes.get("paidSuccessfully") or {}).get("count") or 0)
    blocks = []
    missed_total = 0
    wrong_total = 0
    for country_name in ("India", "UK", "Germany", "Brazil"):
        lines = named(country_name)
        missed_lines = [line for line in lines if "missed payment" in line]
        wrong_lines = [line for line in lines if "old base payment" in line]
        missed_total += len(missed_lines)
        wrong_total += len(wrong_lines)
        row = by_country.get(country_name) or {}
        paid_n = int(row.get("paid") or 0)
        bits = [f"{country_name}: {paid_n} paid."]
        if missed_lines:
            bits.append(f"{len(missed_lines)} missed payment because details were missing.")
        if wrong_lines:
            bits.append(f"{len(wrong_lines)} got old base payment.")
        if not missed_lines and not wrong_lines and not lines:
            bits.append("No one missed payment.")
        blocks.append(" ".join(bits) + ("\n" + "\n".join(lines) if lines else ""))
    return (
        f"{paid} were paid. {missed_total} missed payment because details were missing. "
        f"{wrong_total} got old base payment.\n\n"
        + "\n\n".join(blocks)
    )


def _pending_line(row: Dict[str, Any], country: str) -> str:
    miss_n = len(row.get("miss") or [])
    wrong_n = len(row.get("wrong") or [])
    if miss_n == 0 and wrong_n == 0:
        return f"Nothing is open for {country}."
    parts = []
    if miss_n:
        people = "1 employee" if miss_n == 1 else f"{miss_n} employees"
        parts.append(f"{people} will miss payment because details are missing.")
    if wrong_n:
        people = "1 employee" if wrong_n == 1 else f"{wrong_n} employees"
        parts.append(f"{people} will get old base payment.")
    return " ".join(parts)


def _persona_reports(store: Store, customer_id: str, as_of: str) -> List[Dict[str, Any]]:
    """Country, employee, and global notes on the payroll calendar for the pay month."""
    from domain.config import company_config

    company = company_config()
    admins = list(company.get("countryAdmins") or [])
    if not admins:
        return []
    global_admin = company.get("admin") or {}
    global_name = global_admin.get("name") or "Global HR leader"
    global_label = f"{global_name}, Global HR leader"
    finance_name = (company.get("financeAdmin") or {}).get("name") or "Finance"
    current = cycle_dates(as_of)
    previous = previous_cycle_dates(as_of)
    cycles = [previous, current] if previous.get("key") != current.get("key") else [current]
    today = parse_date(as_of)
    reports: List[Dict[str, Any]] = []
    snaps: Dict[str, Dict[str, Dict[str, Any]]] = {}

    def snap(day: str) -> Dict[str, Dict[str, Any]]:
        if day not in snaps:
            snaps[day] = _miss_snapshot(store, customer_id, day)
        return snaps[day]

    def mail(
        *,
        mail_id: str,
        send_date: str,
        recipient: str,
        subject: str,
        body: str,
        audience: str,
        country: Optional[str],
        cc: Optional[str],
        href: str,
        cta_label: str,
        kind: str = "persona_report",
        cycle_key: Optional[str] = None,
        action_count: int = 0,
    ) -> None:
        if parse_date(send_date) > today:
            return
        reports.append(
            {
                "id": mail_id,
                "send_date": send_date,
                "recipient": recipient,
                "channel": "email",
                "subject": subject,
                "body_summary": body,
                "action_count": action_count,
                "actions": [],
                "policy": None,
                "cta": {"label": cta_label, "href": href},
                "kind": kind,
                "computed": True,
                "audience": audience,
                "country": country,
                "cc": cc,
                "cycle_key": cycle_key,
            }
        )

    def country_cta(admin: Dict[str, Any], row: Dict[str, Any], prefer: str) -> tuple:
        code = admin["code"]
        if prefer == "add" and not row["actions"]:
            return "Add employees", "/people/add"
        if row["actions"] and prefer in ("add", "fix", "review"):
            return "Open action needed", f"/payroll/actions?country={code}"
        if row["approvals"] and prefer in ("review", "fix"):
            return "Open review", f"/payroll/review?country={code}"
        if prefer == "add":
            return "Add employees", "/people/add"
        return "Open overview", "/payroll/overview"

    for cycle in cycles:
        month = str(cycle.get("label") or "").split()[0] or "This cycle"
        day = {n: _month_day(cycle, n) for n in (3, 10, 13, 14, 15, 16, 18, 19, 20, 21, 22, 23, 25, 26, 27, 28, 30)}
        pay_day = str(cycle.get("payDate") or _month_day(cycle, 29))
        submitted_on = _month_day(cycle, 28)
        d15, d16, d19, d20, d22, d23, d27 = (short_date(day[n]) for n in (15, 16, 19, 20, 22, 23, 27))
        pay_label = short_date(pay_day)
        submitted_label = short_date(submitted_on)
        cycle_key = str(cycle.get("key") or "")

        def funds_line(when: str) -> str:
            from server.services.funding import funding_decision_view

            view = funding_decision_view(store, customer_id, cycle_key, when)
            if view.get("fundsAddedOn"):
                return f"Funds added: Yes, on {short_date(view['fundsAddedOn'])}."
            if view.get("decision") == "no":
                return (
                    f"Funds added: No. {finance_name} confirmed on {short_date(view['decidedOn'])} "
                    f"that funds are not added."
                )
            return f"Funds added: No. {finance_name} has not confirmed the funds."

        def schedule_notes() -> str:
            return (
                f"Add employees, bonuses, and hikes, and resolve missing details by {d15}. "
                f"People added after {d15} move to next month.\n"
                f"Review and approve from {d16} to {d19}.\n"
                f"The final report is on {d20}. It goes to {global_name} and each country HR admin.\n"
                f"Review close is {d22}, seven days before pay day, a deadline set by Multiplier. "
                f"Changes after {d22} apply next month.\n"
                f"The funding window is {d23} to {d27}. You set that window.\n"
                f"Payroll is submitted on {submitted_label}, the 28th of the pay month.\n"
                f"Pay day is {pay_label}. You set pay day."
            )

        for admin in admins:
            country = admin["country"]
            who = f"{admin['name']}, {country} HR admin"
            hello = admin["name"].split()[0]

            row3 = snap(day[3]).get(country) or _EMPTY_MISS
            mail(
                mail_id=f"notif_country_{admin['code']}_{day[3]}",
                send_date=day[3],
                recipient=who,
                subject=f"{month} payroll schedule · {country}",
                body=(
                    f"Hello {hello},\n\n"
                    f"Here is the {month} payroll schedule for {country}.\n\n"
                    f"{schedule_notes()}"
                ),
                audience="country",
                country=country,
                cc=None,
                href="/payroll/overview",
                cta_label="Open overview",
            )
            row10 = snap(day[10]).get(country) or _EMPTY_MISS
            mail(
                mail_id=f"notif_country_{admin['code']}_{day[10]}",
                send_date=day[10],
                recipient=who,
                subject=f"{country}: please finish inputs by {d15}",
                body=(
                    f"Hello {hello},\n\n"
                    f"{d15} is the deadline for {country}. Please finish inputs this week.\n\n"
                    f"{schedule_notes()}\n\n"
                    f"{_pending_line(row10, country)}"
                ),
                audience="country",
                country=country,
                cc=None,
                href="/payroll/overview",
                cta_label="Open overview",
            )
            for num, subject, lead in (
                (
                    13,
                    f"{country}: 2 days left to add employees",
                    f"Please add any new {country} employees by {d15}. "
                    f"Anyone added after {d15} moves to next month.\n\n"
                    f"Bonuses, hikes, and missing details are due the same day.",
                ),
                (
                    14,
                    f"{country}: last day to add employees is tomorrow",
                    f"Tomorrow, {d15}, is the last day to add {country} employees for {month}. "
                    f"After that they move to next month.\n\n"
                    f"Please also finish bonuses, hikes, and missing details tomorrow.",
                ),
                (
                    15,
                    f"{country}: last day to add employees",
                    f"Today is the last day to add {country} employees, bonuses, hikes, and missing details. "
                    f"Anyone added after today moves to next month.\n\n"
                    f"Review opens tomorrow and closes {d19}.",
                ),
            ):
                row = snap(day[num]).get(country) or _EMPTY_MISS
                label, href = country_cta(admin, row, "add")
                mail(
                    mail_id=f"notif_country_{admin['code']}_{day[num]}",
                    send_date=day[num],
                    recipient=who,
                    subject=subject,
                    body=f"Hello {hello},\n\n{lead}\n\n{_pending_line(row, country)}",
                    audience="country",
                    country=country,
                    cc=None,
                    href=href,
                    cta_label=label,
                )

            row16 = snap(day[16]).get(country) or _EMPTY_MISS
            label, href = country_cta(admin, row16, "review")
            mail(
                mail_id=f"notif_country_{admin['code']}_{day[16]}",
                send_date=day[16],
                recipient=who,
                subject=f"{country}: review is open until {d19}",
                body=(
                    f"Hello {hello},\n\n"
                    f"The window for new employees has closed. Joiners added from today move to next month.\n\n"
                    f"Please review and approve {country} pay by {d19}. "
                    f"The final report is on {d20}, for you and {global_name}.\n\n"
                    f"{_pending_line(row16, country)}"
                ),
                audience="country",
                country=country,
                cc=None,
                href=href,
                cta_label=label,
            )
            for num, subject, lead in (
                (
                    18,
                    f"{country}: please review before {d19}",
                    f"The {country} review window closes tomorrow, {d19}. "
                    f"Please approve any open lines before then. The final report is on {d20}.",
                ),
                (
                    19,
                    f"{country}: review closes today",
                    f"Today is the last day of the {country} review window. "
                    f"Please close any open approvals today. The final report is tomorrow, {d20}.",
                ),
            ):
                row = snap(day[num]).get(country) or _EMPTY_MISS
                label, href = country_cta(admin, row, "review")
                mail(
                    mail_id=f"notif_country_{admin['code']}_{day[num]}",
                    send_date=day[num],
                    recipient=who,
                    subject=subject,
                    body=f"{_IGNORE}\n\nHello {hello},\n\n{lead}\n\n{_pending_line(row, country)}",
                    audience="country",
                    country=country,
                    cc=None,
                    href=href,
                    cta_label=label,
                )
            for num, subject, lead in (
                (
                    20,
                    f"{country}: report for {global_name}",
                    f"Today, {d20}, is the final report. {global_name} is copied here.\n\n"
                    f"You can still add inputs until {d22}. Anything after {d22} applies next month.",
                ),
                (
                    21,
                    f"{country}: one day left before {d22}",
                    f"The review window is closed. One day remains to add inputs, until {d22}. "
                    f"{global_name} is copied on this report.\n\n"
                    f"Anything still open after {d22} applies next month.",
                ),
                (
                    22,
                    f"{country}: {d22} is the last day",
                    f"Today is the last day for missing details and approvals. "
                    f"{global_name} is copied on this final report.\n\n"
                    f"Anything added after today applies next month.",
                ),
            ):
                row = snap(day[num]).get(country) or _EMPTY_MISS
                label, href = country_cta(admin, row, "fix")
                mail(
                    mail_id=f"notif_country_{admin['code']}_{day[num]}",
                    send_date=day[num],
                    recipient=who,
                    subject=subject,
                    body=f"{_IGNORE}\n\nHello {hello},\n\n{lead}\n\n{_pending_line(row, country)}",
                    audience="country",
                    country=country,
                    cc=global_label,
                    href=href,
                    cta_label=label,
                )
            mail(
                mail_id=f"notif_country_{admin['code']}_{day[23]}",
                send_date=day[23],
                recipient=who,
                subject=f"{country}: please ask {finance_name} to add funds by {d27}",
                body=(
                    f"Hello {hello},\n\n"
                    f"The funding window is {d23} to {d27}. "
                    f"Please ask {finance_name} to add funds by {d27} so {month} payroll can be submitted."
                ),
                audience="country",
                country=country,
                cc=None,
                href="/payroll/overview",
                cta_label="Open overview",
            )
            if parse_date(day[23]) <= today:
                mail(
                    mail_id=f"notif_country_{admin['code']}_{day[23]}_report",
                    send_date=day[23],
                    recipient=who,
                    subject=f"{country}: final report · who will be paid",
                    body=(
                        f"Hello {hello},\n\n"
                        f"Final report for {country}.\n\n"
                        f"{_forecast_text(store, customer_id, day[23], country)}\n\n"
                        f"Full details are on the overview."
                    ),
                    audience="country",
                    country=country,
                    cc=global_label,
                    href="/payroll/overview#miss-details",
                    cta_label="Open overview",
                )
            for num, subject, waiting in (
                (
                    26,
                    f"{country}: funds due {d27}",
                    f"{finance_name} still needs to add funds by tomorrow, {d27}. {global_name} is copied on this note.",
                ),
                (
                    27,
                    f"{country}: funds are due today",
                    f"Today is the last day of the funding window for {finance_name} to add funds. "
                    f"{global_name} is copied on this note. "
                    f"Payroll is submitted on {submitted_label}, the 28th of the pay month.",
                ),
            ):
                added = funds_line(day[num])
                lead = added if added.startswith("Funds added: Yes") else f"{waiting}\n\n{added}"
                mail(
                    mail_id=f"notif_country_{admin['code']}_{day[num]}",
                    send_date=day[num],
                    recipient=who,
                    subject=subject,
                    body=f"{_IGNORE_FUNDS}\n\nHello {hello},\n\n{lead}",
                    audience="country",
                    country=country,
                    cc=global_label,
                    href="/payroll/overview",
                    cta_label="Open overview",
                )

        leader = global_name.split()[0]

        def glance(when: str) -> str:
            miss_bits = []
            wrong_bits = []
            miss_n = 0
            wrong_n = 0
            for admin in admins:
                row = snap(when).get(admin["country"]) or _EMPTY_MISS
                missed = len(row.get("miss") or [])
                wrong = len(row.get("wrong") or [])
                miss_n += missed
                wrong_n += wrong
                if missed:
                    miss_bits.append(f"{admin['country']} {missed}")
                if wrong:
                    wrong_bits.append(f"{admin['country']} {wrong}")
            if miss_n == 0 and wrong_n == 0:
                return "Nothing is open."
            parts = []
            if miss_n:
                parts.append(
                    f"{miss_n} will miss payment because details are missing ({', '.join(miss_bits)})."
                )
            if wrong_n:
                parts.append(
                    f"{wrong_n} will get old base payment ({', '.join(wrong_bits)})."
                )
            return " ".join(parts) + " Full details are on the overview."

        def global_mail(num: int, subject: str, body: str) -> None:
            mail(
                mail_id=f"notif_global_{day[num]}",
                send_date=day[num],
                recipient=global_label,
                subject=subject,
                body=body,
                audience="global",
                country=None,
                cc=None,
                href="/payroll/overview",
                cta_label="Open overview",
            )

        global_mail(
            10,
            f"{month}: employee window is open",
            (
                f"Hello {leader},\n\n"
                f"The window to add new employees for {month} is open, through {d15}. "
                f"Anyone added after {d15} moves to next month."
            ),
        )
        global_mail(
            15,
            f"{month}: employee window is closed",
            (
                f"Hello {leader},\n\n"
                f"The window to add new employees closed today. "
                f"Anyone added after today moves to next month.\n\n"
                f"Review opens tomorrow."
            ),
        )
        global_mail(
            16,
            f"{month}: review window is open",
            (
                f"Hello {leader},\n\n"
                f"The review window is open until {d19}. "
                f"Country HR admins can approve pay until then.\n\n"
                f"{glance(day[16])}"
            ),
        )
        global_mail(
            19,
            f"{month}: review window closes today",
            (
                f"{_IGNORE}\n\n"
                f"Hello {leader},\n\n"
                f"The review window closes today.\n\n"
                f"{glance(day[19])}"
            ),
        )
        global_mail(
            20,
            f"{month}: final report",
            (
                f"{_IGNORE}\n\n"
                f"Hello {leader},\n\n"
                f"This is the final report on {d20}. You have until {d22} "
                f"to work with each HR admin and close what is still open.\n\n"
                f"{glance(day[20])}"
            ),
        )
        global_mail(
            22,
            f"{month}: today is the last day",
            (
                f"{_IGNORE}\n\n"
                f"Hello {leader},\n\n"
                f"Today is the last day. This is the final report.\n\n"
                f"{glance(day[22])}\n\n"
                f"Anything still open after today applies next month."
            ),
        )
        fund_sentence = f"{finance_name} should confirm the funding amount on the overview."
        if parse_date(day[23]) <= today:
            from server.services.funding import estimate as funding_estimate

            fund = funding_estimate(store, customer_id, day[23])
            currency = fund.get("currency") or "USD"
            symbol = "$" if currency == "USD" else f"{currency} "
            fund_sentence = (
                f"{finance_name} should have {symbol}{fund['required']:,.0f} with finance by {d27}."
            )
        finance_hello = finance_name.split()[0]
        from server.services.funding import funding_decision_view

        finance_view = funding_decision_view(store, customer_id, cycle_key, as_of)
        if finance_view.get("fundsAddedOn"):
            finance_status = (
                f"You confirmed Yes on {short_date(finance_view['fundsAddedOn'])}. "
                f"Funds were added on {short_date(finance_view['fundsAddedOn'])}."
            )
        elif finance_view.get("decision") == "no":
            finance_status = (
                f"You confirmed No on {short_date(finance_view['decidedOn'])}. Funds are not added."
            )
        else:
            finance_status = "Yes adds the funds today. No leaves them unadded."
        mail(
            mail_id=f"notif_finance_{day[23]}",
            send_date=day[23],
            recipient=f"{finance_name}, Fund manager",
            subject=f"{month}: please confirm funds are added",
            body=(
                f"Hello {finance_hello},\n\n"
                f"Please confirm whether funds for {month} payroll are added.\n\n"
                f"The funding window is {d23} to {d27}.\n"
                f"{fund_sentence}\n\n"
                f"{finance_status}"
            ),
            audience="finance",
            country=None,
            cc=None,
            href="/payroll/overview",
            cta_label="Open overview",
            kind="funding_confirm",
            cycle_key=cycle_key,
            action_count=2,
        )
        global_mail(
            23,
            f"{month}: funding period has started",
            (
                f"{_IGNORE}\n\n"
                f"Hello {leader},\n\n"
                f"Review close was {d22}, a deadline set by Multiplier. "
                f"The funding window is {d23} to {d27}. You set that window.\n\n"
                f"{fund_sentence}\n\n"
                f"{glance(day[23])}"
            ),
        )
        if parse_date(day[23]) <= today:
            mail(
                mail_id=f"notif_global_{day[23]}_report",
                send_date=day[23],
                recipient=global_label,
                subject=f"{month}: final report · who will be paid",
                body=(
                    f"Hello {leader},\n\n"
                    f"Final report for {month}, alongside the funding note.\n\n"
                    f"{_forecast_text(store, customer_id, day[23])}\n\n"
                    f"Full details are on the overview."
                ),
                audience="global",
                country=None,
                cc=None,
                href="/payroll/overview#miss-details",
                cta_label="Open overview",
            )
        global_mail(
            25,
            f"{month}: funds added",
            (
                f"{_IGNORE_FUNDS}\n\n"
                f"Hello {leader},\n\n"
                f"{funds_line(day[25])} {finance_name} is the fund manager for {month}."
            ),
        )
        day26 = funds_line(day[26])
        global_mail(
            26,
            f"{month}: one day left to add funds",
            (
                f"{_IGNORE_FUNDS}\n\n"
                f"Hello {leader},\n\n"
                f"The funding window closes tomorrow, {d27}. {day26}"
            ),
        )
        day27 = funds_line(day[27])
        global_mail(
            27,
            f"{month}: last day to add funds",
            (
                f"{_IGNORE_FUNDS}\n\n"
                f"Hello {leader},\n\n"
                f"Today is the last day to add funds. The window you set runs through {d27}. {day27}"
            ),
        )
        if parse_date(submitted_on) <= today:
            mail(
                mail_id=f"notif_global_{submitted_on}_submitted",
                send_date=submitted_on,
                recipient=global_label,
                subject=f"{month}: payroll submitted",
                body=(
                    f"Hello {leader},\n\n"
                    f"Payroll was submitted on {submitted_label}, the 28th of the pay month. Pay day is {pay_label}. "
                    f"Multiplier is calculating the payment."
                ),
                audience="global",
                country=None,
                cc=None,
                href="/payroll/overview",
                cta_label="Open overview",
            )
            for admin in admins:
                mail(
                    mail_id=f"notif_country_{admin['code']}_{submitted_on}_submitted",
                    send_date=submitted_on,
                    recipient=f"{admin['name']}, {admin['country']} HR admin",
                    subject=f"{admin['country']}: {month} payroll submitted",
                    body=(
                        f"Hello {admin['name'].split()[0]},\n\n"
                        f"{month} payroll was submitted on {submitted_label}, the 28th of the pay month. "
                        f"Pay day is {pay_label}. "
                        f"Multiplier is calculating the payment."
                    ),
                    audience="country",
                    country=admin["country"],
                    cc=global_label,
                    href="/payroll/overview",
                    cta_label="Open overview",
                )

        if parse_date(pay_day) <= today:
            from server.services.sync import _bank_returned_phrase, payday_outcomes

            outcomes = payday_outcomes(store, customer_id, pay_day) or {}
            by_country = outcomes.get("byCountry") or {}

            def reasons_for(country_name: str) -> str:
                row = by_country.get(country_name) or {}
                paid = int(row.get("paid") or 0)
                bits = []
                for key, label in (
                    ("missingInputs", "missed payment because details were missing"),
                    ("paidPreviousSalary", "got old base payment"),
                    ("addedAfterCutoff", "added after the window closed"),
                    ("paymentReturned", "payment was returned by the bank"),
                ):
                    count = int((row.get(key) or {}).get("count") or 0)
                    if not count:
                        continue
                    names = [
                        person.get("name")
                        for person in (outcomes.get(key) or {}).get("employees") or []
                        if person.get("country") == country_name and person.get("name")
                    ]
                    phrase = _bank_returned_phrase(count) if key == "paymentReturned" else f"{count} {label}"
                    if names:
                        shown = ", ".join(names[:3])
                        extra = f" and {len(names) - 3} more" if len(names) > 3 else ""
                        bits.append(f"{phrase} ({shown}{extra})")
                    else:
                        bits.append(phrase)
                moved = sum(int((row.get(key) or {}).get("count") or 0) for key, _label in (
                    ("missingInputs", ""),
                    ("paidPreviousSalary", ""),
                    ("addedAfterCutoff", ""),
                    ("paymentReturned", ""),
                ))
                missed = int((row.get("missingInputs") or {}).get("count") or 0)
                wrong = int((row.get("paidPreviousSalary") or {}).get("count") or 0)
                if moved == 0:
                    return f"{country_name}: {paid} paid. No one missed payment."
                return (
                    f"{country_name}: {paid} paid. {missed} missed payment because details were missing. "
                    f"{wrong} got old base payment; that difference moves to the next cycle"
                    + (f" — {'; '.join(bits)}." if bits else ".")
                )

            paid_total = 0
            affected_total = 0
            for admin in admins:
                row = by_country.get(admin["country"]) or {}
                paid_total += int(row.get("paid") or 0)
                affected_total += sum(
                    int((row.get(key) or {}).get("count") or 0)
                    for key in ("missingInputs", "paidPreviousSalary", "addedAfterCutoff", "paymentReturned")
                )
            from server.services.funding import estimate as funding_estimate

            paid_fund = funding_estimate(store, customer_id, pay_day)
            paid_currency = paid_fund.get("currency") or "USD"
            paid_symbol = "$" if paid_currency == "USD" else f"{paid_currency} "
            paid_amount = f"{paid_symbol}{paid_fund['required']:,.0f}"
            mail(
                mail_id=f"notif_global_{pay_day}",
                send_date=pay_day,
                recipient=global_label,
                subject=f"{month} pay sent",
                body=(
                    f"Hello {leader},\n\n"
                    f"{month} pay went out on {pay_label}.\n\n"
                    f"{paid_total} employees were paid. {affected_total} were affected.\n"
                    f"Amount paid: {paid_amount}.\n\n"
                    + "\n".join(reasons_for(admin["country"]) for admin in admins)
                    + "\n\nFull details are on the overview."
                ),
                audience="global",
                country=None,
                cc=None,
                href="/payroll/overview",
                cta_label="Open overview",
            )
            for admin in admins:
                country = admin["country"]
                mail(
                    mail_id=f"notif_country_{admin['code']}_{pay_day}",
                    send_date=pay_day,
                    recipient=f"{admin['name']}, {country} HR admin",
                    subject=f"{country}: {month} pay submitted",
                    body=(
                        f"Hello {admin['name'].split()[0]},\n\n"
                        f"{month} pay was submitted for {country} on {pay_label}.\n\n"
                        f"{reasons_for(country)}"
                    ),
                    audience="country",
                    country=country,
                    cc=global_label,
                    href="/payroll/overview",
                    cta_label="Open overview",
                )

        if parse_date(day[30]) <= today:
            from server.services.sync import payday_outcomes

            final_outcomes = payday_outcomes(store, customer_id, day[30]) or {}
            final_label = short_date(day[30])
            mail(
                mail_id=f"notif_global_{day[30]}",
                send_date=day[30],
                recipient=global_label,
                subject=f"{month}: final report · who was paid",
                body=(
                    f"Hello {leader},\n\n"
                    f"Final report for {month} on {final_label}. This is who was actually paid, and who missed.\n\n"
                    f"{_actual_text(final_outcomes)}\n\n"
                    f"Full details are on the overview."
                ),
                audience="global",
                country=None,
                cc=None,
                href="/payroll/overview#miss-details",
                cta_label="Open overview",
            )
            for admin in admins:
                country = admin["country"]
                mail(
                    mail_id=f"notif_country_{admin['code']}_{day[30]}",
                    send_date=day[30],
                    recipient=f"{admin['name']}, {country} HR admin",
                    subject=f"{country}: final report · who was paid",
                    body=(
                        f"Hello {admin['name'].split()[0]},\n\n"
                        f"Final report for {country} on {final_label}.\n\n"
                        f"{_actual_text(final_outcomes, country)}\n\n"
                        f"Full details are on the overview."
                    ),
                    audience="country",
                    country=country,
                    cc=global_label,
                    href="/payroll/overview#miss-details",
                    cta_label="Open overview",
                )

        if cycle.get("key") != current.get("key"):
            continue
        cycle_row = store.get_current_cycle(customer_id)
        open_rows = _open_actions(store, cycle_row["id"], as_of) if cycle_row else []
        missing_ids = sorted(
            {
                issue["employee_id"]
                for issue in open_rows
                if (issue.get("kind") or "") in ("missing_fields", "missing_data") and issue.get("employee_id")
            }
        )
        when_notes = {
            10: "",
            13: "2 days left",
            14: "tomorrow",
            15: "today is the last day",
        }
        for employee_id in missing_ids:
            emp = store.get_employee(employee_id)
            if not emp:
                continue
            missing = store.missing_fields(employee_id, as_of)
            owned = rules_svc.split_owned(missing).get("employee") or []
            label = rules_svc.sentence_fields(owned) if owned else "missing details"
            first = emp["name"].split()[0]
            for num, when_note in when_notes.items():
                subject, body = employee_details_mail(
                    first=first,
                    label=label,
                    deadline=d15,
                    month=month,
                    when_note=when_note,
                )
                mail(
                    mail_id=f"notif_emp_{employee_id}_{day[num]}",
                    send_date=day[num],
                    recipient=emp["name"],
                    subject=subject,
                    body=body,
                    audience="employee",
                    country=emp.get("country"),
                    cc=None,
                    href=f"/people/{employee_id}?panel=missing#missing-details",
                    cta_label="Add my details",
                )
    return reports


def notify_payroll_on_track(
    store: Store,
    emp: Dict[str, Any],
    *,
    as_of: str,
    label: str,
    month: Optional[str] = None,
) -> None:
    """Email the employee once their details put that pay month on track."""
    from server.services import email_smtp

    cycle = cycle_dates(as_of)
    month = month or str(cycle.get("label") or "This").split()[0]
    first = str(emp.get("name") or "there").split()[0]
    what = label or "details"
    subject = f"Thanks for adding your details. {month} payroll is on track."
    body = (
        f"Hi {first},\n\n"
        f"Thanks for adding your details. {month} payroll is on track.\n\n"
        f"What: your {what}.\n"
        f"Why: {month} payroll is on track.\n"
        f"You don't need to reply to this email."
    )
    kind = "payroll_on_track"
    if email_smtp.smtp_configured():
        sent = email_smtp.send_employee_note(
            to_address=email_smtp.demo_personal_email(emp["name"], emp.get("personal_email")),
            subject=subject,
            text=body,
        )
        if not sent.get("sent"):
            kind = "payroll_on_track_undelivered"
    db_cycle = store.get_current_cycle(emp["customer_id"])
    if not db_cycle:
        return
    store.add_notification(
        db_cycle["id"],
        send_date=as_of,
        recipient=emp["name"],
        recipient_employee_id=emp["id"],
        subject=subject,
        body_summary=body,
        actions=[],
        cta_label="View employee",
        cta_href=f"/people/{emp['id']}",
        kind=kind,
    )


def _stored_audience(store: Store, row: Dict[str, Any]) -> tuple:
    """Employee mail belongs in that country's inbox, and in Global's."""
    kind = str(row.get("kind") or "")
    if not (kind.startswith("employee_reminder") or kind.startswith("payroll_on_track")):
        return None, None
    emp_id = row.get("recipient_employee_id")
    emp = store.get_employee(emp_id) if emp_id else None
    return "employee", (emp or {}).get("country")


def list_notifications(
    store: Store, customer_id: str, as_of: str, channel: str = "email"
) -> List[Dict[str, Any]]:
    cycle = store.get_current_cycle(customer_id)
    if not cycle:
        raise LookupError("cycle_not_found")
    stored = []
    for n in _stored_for_cycles(store, customer_id, as_of, channel):
        if n.get("kind") == "details_confirmed":
            continue
        audience, country = _stored_audience(store, n)
        subject, body = (
            present_employee_reminder(n)
            if str(n.get("kind") or "").startswith("employee_reminder")
            else (n["subject"], n.get("body_summary"))
        )
        stored.append(
            {
                "id": n["id"],
                "send_date": n["send_date"],
                "recipient": n["recipient"],
                "channel": n.get("channel", "email"),
                "subject": subject,
                "body_summary": body,
                "action_count": n.get("action_count"),
                "cta_label": n.get("cta_label"),
                "cta_href": n.get("cta_href"),
                "kind": n.get("kind"),
                "audience": audience,
                "country": country,
                "created_at": n.get("created_at"),
                "delivery": _delivery_from_kind(n.get("kind")),
                "computed": False,
            }
        )
    computed = _computed(store, customer_id, as_of) if channel == "email" else []
    merged = emails_visible_on(computed + stored, as_of)
    read_ids = store.notification_read_ids()
    return [
        {
            "id": n["id"],
            "sendDate": n["send_date"],
            "createdAt": n.get("created_at"),
            "recipient": n["recipient"],
            "channel": n.get("channel", "email"),
            "subject": n["subject"],
            "bodySummary": n.get("body_summary"),
            "actionCount": n.get("action_count"),
            "kind": n.get("kind"),
            "audience": n.get("audience"),
            "country": n.get("country"),
            "cc": n.get("cc"),
            "delivery": n.get("delivery") or _delivery_from_kind(n.get("kind")),
            "ctaLabel": n.get("cta_label") or (n.get("cta") or {}).get("label"),
            "unread": n["id"] not in read_ids,
        }
        for n in merged
    ]


def get_notification(store: Store, notification_id: str, customer_id: str, as_of: Optional[str] = None) -> Dict[str, Any]:
    as_of = as_of or store.meta("prototype_date") or "2026-10-12"
    detail = _notification_detail(store, notification_id, customer_id, as_of)
    store.mark_notification_read(notification_id, read_on=as_of)
    detail["unread"] = False
    return detail


def _funding_confirm(
    store: Store, customer_id: str, as_of: str, row: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    if row.get("kind") != "funding_confirm":
        return None
    from server.services.funding import funding_decision_view

    key = row.get("cycle_key") or cycle_dates(as_of).get("key") or ""
    return funding_decision_view(store, customer_id, str(key), as_of)


def _notification_detail(store: Store, notification_id: str, customer_id: str, as_of: str) -> Dict[str, Any]:
    stored = store.get_notification(notification_id)
    if stored:
        actions = [
            {"actionText": a["action_text"], "deadline": a.get("deadline"), "issueId": a.get("issue_id")}
            for a in store.notification_actions(notification_id)
        ]
        cta_href = stored.get("cta_href") or "/payroll/overview"
        emp_id = stored.get("recipient_employee_id")
        kind = stored.get("kind")
        audience, country = _stored_audience(store, stored)
        # Reminder CTAs open Missing details on the employee profile (HR tool).
        # Legacy rows may still point at /form/… — rewrite when we know the employee.
        if (
            emp_id
            and kind
            and str(kind).startswith("employee_reminder")
            and (cta_href.startswith("/form/") or "panel=missing" not in cta_href)
        ):
            cta_href = f"/people/{emp_id}?panel=missing#missing-details"
        subject, body = (
            present_employee_reminder(stored)
            if str(kind or "").startswith("employee_reminder")
            else (stored["subject"], stored.get("body_summary"))
        )
        return {
            "id": stored["id"],
            "sendDate": stored["send_date"],
            "recipient": stored["recipient"],
            "channel": stored.get("channel", "email"),
            "subject": subject,
            "bodySummary": body,
            "actionCount": stored.get("action_count"),
            "actions": actions,
            "cta": {
                "label": stored.get("cta_label") or "Open Payroll tab",
                "href": cta_href,
            },
            "kind": kind,
            "audience": audience,
            "country": country,
            "delivery": _delivery_from_kind(kind),
            "recipientEmployeeId": emp_id,
        }
    for n in _computed(store, customer_id, as_of):
        if n["id"] == notification_id:
            return {
                "id": n["id"],
                "sendDate": n["send_date"],
                "recipient": n["recipient"],
                "channel": "email",
                "subject": n["subject"],
                "bodySummary": n["body_summary"],
                "actionCount": n["action_count"],
                "actions": n["actions"],
                "policy": n.get("policy"),
                "cta": n["cta"],
                "kind": n["kind"],
                "cc": n.get("cc"),
                "audience": n.get("audience"),
                "country": n.get("country"),
                "delivery": _delivery_from_kind(n.get("kind")),
                "fundingConfirm": _funding_confirm(store, customer_id, as_of, n),
            }
    raise LookupError("notification_not_found")
