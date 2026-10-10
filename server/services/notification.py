"""Notification Service — computed HR emails + stored employee reminders (SMTP is in email_smtp)."""

from __future__ import annotations

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
from server.services import rules as rules_svc  # noqa: E402

TEMPLATES = seed_config()["emailTemplates"]


def _delivery_from_kind(kind: Optional[str]) -> Optional[str]:
    if kind == "employee_reminder_undelivered":
        return "not_sent_smtp_missing"
    if kind == "employee_reminder":
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
    return sum(1 for r in lines if not store.line_approval(r["id"], as_of))


def _computed(store: Store, customer_id: str, as_of: str) -> List[Dict[str, Any]]:
    cycle = store.get_current_cycle(customer_id)
    assert cycle
    issues = _open_actions(store, cycle["id"], as_of)
    blocking = [i for i in issues if i.get("severity") == "blocking"]
    outcome = rules_svc.outcome(store, customer_id, as_of)
    carry = rules_svc.carry_overs(store, customer_id, as_of)
    days = max(0, days_until_cutoff(as_of))
    n = len(issues)
    b = len(blocking)
    on_time = outcome["paidOnTime"]["count"] if outcome else 0
    moved = outcome["movedToNovember"]["count"] if outcome else len(carry)
    signed = _signed_off(store, cycle, as_of)
    remaining = _remaining_lines(store, cycle["id"], as_of)
    need_check = len(store.review_lines(cycle["id"], as_of=as_of))

    computed: List[Dict[str, Any]] = []
    for t in TEMPLATES:
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

        if kind == "actions_open":
            subject = _fill(subject, days=days or 0, n=n)
            if t["date"] == "2026-10-12":
                subject = _fill(t["subject"], days=days_until_cutoff("2026-10-12"), n=n)
            if n == 1 and issues[0].get("id"):
                cta = {"label": "Open Action needed", "href": f"/payroll/actions?issue={issues[0]['id']}"}
        elif kind == "blocking_open":
            subject = _fill(subject, n=b, s="" if b == 1 else "s")
            actions = _action_rows(store, blocking)
            if b == 1 and blocking[0].get("id"):
                cta = {"label": "Open Action needed", "href": f"/payroll/actions?issue={blocking[0]['id']}"}
        elif kind == "inputs_locked":
            actions = [
                {
                    "actionText": f"{c['name']} — {c.get('reason') or 'moved to November'}",
                    "deadline": "2026-11-15",
                    "issueId": None,
                }
                for c in carry
            ]
            cta = {"label": "Open Overview", "href": "/payroll/overview"}
            body = (
                "Inputs locked after Oct 15. Multiplier calculates pay on Oct 16. "
                f"Review opens Oct 17."
                + (f" Moved to November: {', '.join(c['name'] for c in carry)}." if carry else "")
            )
        elif kind in ("review_open", "review_reminder", "review_closes_today"):
            subject = _fill(subject, n=remaining if kind != "review_open" else need_check)
            actions = []
            cta = {"label": "Open Review & approve", "href": "/payroll/review"}
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
                        }
                        for a in (actions or [])
                    ],
                    "cta": cta,
                    "kind": kind,
                    "computed": True,
                }
            )
    return computed


def list_notifications(
    store: Store, customer_id: str, as_of: str, channel: str = "email"
) -> List[Dict[str, Any]]:
    cycle = store.get_current_cycle(customer_id)
    if not cycle:
        raise LookupError("cycle_not_found")
    stored = [
        {
            "id": n["id"],
            "send_date": n["send_date"],
            "recipient": n["recipient"],
            "channel": n.get("channel", "email"),
            "subject": n["subject"],
            "body_summary": n.get("body_summary"),
            "action_count": n.get("action_count"),
            "cta_label": n.get("cta_label"),
            "cta_href": n.get("cta_href"),
            "kind": n.get("kind"),
            "delivery": _delivery_from_kind(n.get("kind")),
            "computed": False,
        }
        for n in _stored_for_cycles(store, customer_id, as_of, channel)
    ]
    computed = _computed(store, customer_id, as_of) if channel == "email" else []
    merged = emails_visible_on(computed + stored, as_of)
    return [
        {
            "id": n["id"],
            "sendDate": n["send_date"],
            "recipient": n["recipient"],
            "channel": n.get("channel", "email"),
            "subject": n["subject"],
            "bodySummary": n.get("body_summary"),
            "actionCount": n.get("action_count"),
            "kind": n.get("kind"),
            "delivery": n.get("delivery") or _delivery_from_kind(n.get("kind")),
            "ctaLabel": n.get("cta_label") or (n.get("cta") or {}).get("label"),
        }
        for n in merged
    ]


def get_notification(store: Store, notification_id: str, customer_id: str, as_of: Optional[str] = None) -> Dict[str, Any]:
    as_of = as_of or store.meta("prototype_date") or "2026-10-12"
    stored = store.get_notification(notification_id)
    if stored:
        actions = [
            {"actionText": a["action_text"], "deadline": a.get("deadline"), "issueId": a.get("issue_id")}
            for a in store.notification_actions(notification_id)
        ]
        cta_href = stored.get("cta_href") or "/payroll/overview"
        emp_id = stored.get("recipient_employee_id")
        kind = stored.get("kind")
        # Reminder CTAs open Missing details on the employee profile (HR tool).
        # Legacy rows may still point at /form/… — rewrite when we know the employee.
        if (
            emp_id
            and kind
            and str(kind).startswith("employee_reminder")
            and (cta_href.startswith("/form/") or "panel=missing" not in cta_href)
        ):
            cta_href = f"/people/{emp_id}?panel=missing"
        return {
            "id": stored["id"],
            "sendDate": stored["send_date"],
            "recipient": stored["recipient"],
            "channel": stored.get("channel", "email"),
            "subject": stored["subject"],
            "bodySummary": stored.get("body_summary"),
            "actionCount": stored.get("action_count"),
            "actions": actions,
            "cta": {
                "label": stored.get("cta_label") or "Open Payroll tab",
                "href": cta_href,
            },
            "kind": kind,
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
                "cta": n["cta"],
                "kind": n["kind"],
                "delivery": _delivery_from_kind(n.get("kind")),
            }
    raise LookupError("notification_not_found")
