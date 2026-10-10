"""Review Matching Service — fixed window Oct 17–22 (config), per-line approve, sign-off."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "data"))

from domain.calendar_rules import (  # noqa: E402
    NOV_OPEN,
    REVIEW_CLOSE,
    REVIEW_OPEN,
    active_cycle_key,
    cycle_dates,
    next_cycle_dates,
    parse_date,
    review_bounds,
    review_countdown,
    review_window_state,
    short_date,
    show_october_closed_review,
    unsigned_outcome_rows,
)
from domain.config import company_config, cycle_config  # noqa: E402

from server.db.repositories import Store  # noqa: E402
from server.services import clock as clock_svc  # noqa: E402
from server.services import calendar as calendar_svc  # noqa: E402
from server.services import rules as rules_svc  # noqa: E402
from server.services import submission as submission_svc  # noqa: E402

CYCLE = cycle_config()
OCT = CYCLE["cycles"]["october"]
NOV = CYCLE["cycles"]["november"]


class AiCheckRequired(Exception):
    def __init__(self, payload: Dict[str, Any]):
        super().__init__("ai_check")
        self.payload = payload


def _line_dto(store: Store, r: Dict[str, Any], as_of: str) -> Dict[str, Any]:
    approval = store.line_approval(r["id"], as_of)
    source = r["matching_source"]
    issue_id = r.get("linked_issue_id")
    if issue_id and r.get("matching_source_resolved"):
        issue = store.get_issue(issue_id, as_of=as_of)
        if issue and issue.get("status") == "resolved":
            source = r["matching_source_resolved"]
    dto: Dict[str, Any] = {
        "id": r["id"],
        "employeeId": r.get("employee_id"),
        "employeeName": r["employee_name"],
        "country": r["country"],
        "changeSummary": r["change_summary"],
        "whyFlagged": r["why_flagged"],
        "matchingSource": source,
        "origin": r.get("origin") or "seed",
        "needsHumanCheck": approval is None,
        "approved": approval is not None,
        "approvedOn": approval["approved_on"] if approval else None,
        "approvedBy": approval["approved_by"] if approval else None,
        "openHref": f"/people/{r['employee_id']}?panel=salary" if r.get("employee_id") else "/people",
    }
    if r.get("requires_employee_notified"):
        dto["requiresEmployeeNotified"] = True
    return dto


def attach_llm_decisions(lines: List[Dict[str, Any]], *, force: bool = False) -> List[Dict[str, Any]]:
    """Ask the LLM whether each unapproved line should be approved or held."""
    from server.services import llm as llm_svc

    for line in lines:
        if line.get("approved"):
            line["llmDecision"] = {
                "recommend": "approve",
                "confidence": 1.0,
                "reason": "Already approved.",
                "label": "Approved",
                "source": "approved",
            }
            continue
        line["llmDecision"] = llm_svc.decide_review_line(line, force=force)
    return lines


def _outcome_lookup() -> Dict[str, Dict[str, Any]]:
    return {row["employeeId"]: row for row in unsigned_outcome_rows()}


def _unapplied(store: Store, lines: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Unapproved need-check lines → paid at September; arrears or recovery in November."""
    outcomes = _outcome_lookup()
    next_c = next_cycle_dates("2026-10-23")
    next_open = short_date(next_c["reviewOpen"])
    next_close = short_date(next_c["reviewClose"])
    out: List[Dict[str, Any]] = []
    for line in lines:
        if line.get("approved"):
            continue
        eid = line.get("employeeId")
        emp = store.get_employee(eid) if eid else None
        currency = (emp or {}).get("currency") or "£"
        sept = rules_svc.fmt_money(currency, emp["september_pay"]) if emp else None
        row = outcomes.get(eid or "")
        kind = (row or {}).get("kind") or "arrears"
        if row and kind == "arrears":
            amt = rules_svc.fmt_money(currency, row["amount"])
            note = (
                f"paid {sept} in October · {amt} "
                f"added as arrears in November review"
            )
            banner = f"{line['employeeName']} — {note}"
        elif row and kind == "recovery":
            amt = rules_svc.fmt_money(currency, row["amount"])
            note = f"paid {sept} in October · {amt} to be recovered in November review"
            banner = f"{line['employeeName']} — {note}"
        else:
            note = f"Paid {sept} in October; change moves to November as arrears" if sept else "Moved to November"
            banner = f"{line['employeeName']} — {note}"
        out.append(
            {
                "id": eid,
                "name": line["employeeName"],
                "href": line.get("openHref") or "/people",
                "septemberPay": sept,
                "changeSummary": line["changeSummary"],
                "kind": kind,
                "note": note,
                "banner": banner,
                "nextReviewLabel": f"{next_open}–{next_close}",
            }
        )
    return out


def _assert_window_open(as_of: str) -> None:
    if review_window_state(as_of) != "open":
        raise PermissionError("Review window is not open")


def _carry_line_id(kind: str, employee_id: str) -> str:
    return f"rev_nov_{kind}_{employee_id}"


def _november_visible_rows(raw_lines: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        r
        for r in raw_lines
        if (r.get("origin") or "") in ("edited", "november", "october_carry")
        or (r.get("created_on") or "") >= "2026-11-01"
    ]


def _line_summary_counts(lines: List[Dict[str, Any]], rollup: Dict[str, int]) -> Dict[str, int]:
    if not lines:
        return {
            "changedLines": 0,
            "matchedLines": 0,
            "needsHumanCheck": 0,
            "employeeCount": rollup["employeeCount"],
        }
    return {
        "changedLines": len(lines),
        "matchedLines": sum(1 for l in lines if l.get("approved")),
        "needsHumanCheck": sum(1 for l in lines if l.get("needsHumanCheck")),
        "employeeCount": rollup["employeeCount"],
    }


def _cleanup_november_review_lines(store: Store, cycle: Dict[str, Any], as_of: str) -> None:
    outcomes = {row["employeeId"]: row for row in unsigned_outcome_rows()}
    cut = parse_date(cycle_dates(as_of)["inputFinalisation"])
    nxt_open = str(next_cycle_dates(as_of).get("open") or "2026-12-01")
    for r in store.review_lines(cycle["id"], as_of=as_of):
        lid = r["id"]
        if lid.startswith("rev_nov_emp_"):
            store.delete_review_line(lid)
            continue
        eid = r.get("employee_id")
        origin = r.get("origin") or ""
        created = r.get("created_on")
        summary = r.get("change_summary") or ""
        row = outcomes.get(eid or "")
        # Drop duplicate OTP review lines that mirror an unsigned arrears carry for same emp+amount
        if row and row.get("kind") == "arrears" and origin in ("edited", "november"):
            try:
                if abs(float(row["amount"])) > 0 and str(int(row["amount"])) in summary.replace(",", ""):
                    if "Bonus" in summary or "one-time" in summary.lower() or "One-time" in summary:
                        store.delete_review_line(lid)
                        continue
            except (TypeError, ValueError):
                pass
        if created and origin in ("edited", "november") and parse_date(created) > cut:
            store.update_review_line(lid, created_on=nxt_open, origin="november")


def _persist_november_carry_lines(store: Store, cycle: Dict[str, Any], as_of: str) -> None:
    if bool(cycle.get("approved")):
        return
    created_on = max(as_of, "2026-11-01")
    for row in unsigned_outcome_rows():
        eid = row["employeeId"]
        emp = store.get_employee(eid)
        if not emp:
            continue
        currency = emp.get("currency") or "£"
        amt = rules_svc.fmt_money(currency, row["amount"])
        kind = row["kind"]
        label = "Arrears" if kind == "arrears" else "Recovery"
        sign = "+" if kind == "arrears" else "–"
        store.upsert_review_line(
            {
                "id": _carry_line_id(kind, eid),
                "cycle_id": cycle["id"],
                "employee_id": eid,
                "employee_name": emp["name"],
                "country": emp["country"],
                "change_summary": f"{label} {sign}{amt}",
                "why_flagged": "From October review (not signed off)",
                "matching_source": row.get("label") or label,
                "origin": "october_carry",
                "created_on": created_on,
                "requires_employee_notified": kind == "recovery",
            }
        )


def _sync_november_review(store: Store, cycle: Dict[str, Any], as_of: str) -> None:
    if show_october_closed_review(as_of) or active_cycle_key(as_of) != "november":
        return
    store.ensure_schema()
    _cleanup_november_review_lines(store, cycle, as_of)
    if parse_date(as_of) >= parse_date(NOV.get("calculation") or "2026-11-16"):
        _persist_november_carry_lines(store, cycle, as_of)


def calculate_and_build_review(store: Store, customer_id: str, as_of: str) -> None:
    """Idempotent: upsert review lines for changed employees / OTPs in the active cycle."""
    cycle = store.get_current_cycle(customer_id)
    if not cycle:
        return
    cd = cycle_dates(as_of)
    calc = cd.get("calculation") or cd["inputFinalisation"]
    if parse_date(as_of) < parse_date(calc):
        return
    store.ensure_schema()
    if cd["key"] == "november":
        _sync_november_review(store, cycle, as_of)
    emps = store.list_employees(customer_id, as_of=as_of)
    for emp in emps:
        otps = store.one_time_payments(emp["id"], as_of)
        # Only OTPs recorded on/after this cycle's open (or always for changed)
        cycle_otps = [
            p
            for p in otps
            if (p.get("recorded_on") or "") >= (cd.get("open") or cd["inputFinalisation"][:8] + "01")
        ]
        if not emp.get("changed_this_cycle") and not cycle_otps and not emp.get("edited_by_you"):
            continue
        if cycle_otps:
            last = cycle_otps[-1]
            lid = f"rev_{cd['key']}_otp_{emp['id']}_{last.get('id') or last.get('type')}"
            store.upsert_review_line(
                {
                    "id": lid,
                    "cycle_id": cycle["id"],
                    "employee_id": emp["id"],
                    "employee_name": emp["name"],
                    "country": emp["country"],
                    "change_summary": f"{last.get('type') or 'Payment'} {rules_svc.fmt_money(emp['currency'], float(last.get('amount') or 0))}",
                    "why_flagged": "One-time payment – needs approval",
                    "matching_source": last.get("document_name") or "No supporting document",
                    "origin": "november" if cd["key"] != "october" else "edited",
                    "created_on": last.get("recorded_on") or as_of,
                }
            )
        elif emp.get("edited_by_you") or emp.get("changed_this_cycle"):
            ensure_edited_line(
                store,
                emp,
                as_of=as_of,
                change_summary=f"Change in {cd['label']}",
                why_flagged="Edited by you – needs approval",
                matching_source="Edited by HR admin",
            )


def get_review(store: Store, customer_id: str, as_of: str) -> Dict[str, Any]:
    cycle = store.get_current_cycle(customer_id)
    if not cycle:
        raise LookupError("cycle_not_found")

    # Oct 23–31: closed October view. From Nov 1: November cycle (before until Nov 17).
    october_closed_view = show_october_closed_review(as_of)
    window = review_window_state(as_of, for_october_summary=october_closed_view)
    cd = cycle_dates(as_of if not october_closed_view else "2026-10-22")
    open_d, close_d = review_bounds(as_of if not october_closed_view else "2026-10-22")
    open_label = short_date(open_d)
    close_label = short_date(close_d)
    next_c = next_cycle_dates(as_of)
    next_open = short_date(next_c["reviewOpen"])
    next_close = short_date(next_c["reviewClose"])
    funding_label = short_date(cd["fundingDue"]) if cd.get("fundingDue") else None

    signoff = store.active_signoff(cycle["id"], as_of)
    reopened = bool(signoff and signoff.get("reopened_on") and (not as_of or signoff["reopened_on"] <= as_of))
    active = bool(signoff and not reopened)
    not_in = rules_svc.not_in_run(store, customer_id, as_of) if window == "open" else {"count": 0, "employees": [], "message": "", "href": "/payroll/actions"}
    counts = calendar_svc.cycle_counts(store, customer_id, as_of)
    november_view = not october_closed_view and active_cycle_key(as_of) == "november"
    # October review lines come from seed; rebuild only for November+ cycles
    if window != "before" and not october_closed_view and active_cycle_key(as_of) != "october":
        calculate_and_build_review(store, customer_id, as_of)
    elif november_view and window != "before":
        _sync_november_review(store, cycle, as_of)

    base = {
        "windowState": window,
        "cycleKey": "october" if october_closed_view else active_cycle_key(as_of),
        "available": window == "open",
        "readOnly": window != "open",
        "inputsNote": None,
        "inputsOpen": False,
        "asOf": parse_date(as_of).isoformat(),
        "notInRun": not_in if window == "open" else None,
        "closedWithoutSignOff": False,
        "unappliedChanges": [],
        "closedSummary": None,
        "numbersLabel": None,
        "showOpenExtras": window == "open",
        "nextReviewOpen": next_c["reviewOpen"],
        "nextReviewClose": next_c["reviewClose"],
        "nextReviewLabel": f"{next_open}–{next_close}",
        "badgeCount": 0,
    }

    if window == "before":
        cut = short_date(cd["inputFinalisation"])
        return {
            **base,
            "header": f"Review opens {open_label}",
            "closedMessage": (
                f"**Review opens {open_label}.** Multiplier calculates pay after inputs lock on "
                f"{cut}, so you'll review final numbers. Until then, fix open items in Action needed →"
            ),
            "actionsHref": "/payroll/actions",
            "changedLines": 0,
            "matchedLines": 0,
            "needsHumanCheck": 0,
            "lines": [],
            "remaining": 0,
            "canSignOff": False,
            "signOffHint": f"Review opens {open_label}",
            "signedOff": False,
            "signoff": None,
            "approved": False,
        }

    raw_lines = store.review_lines(cycle["id"], as_of=as_of)
    if october_closed_view or active_cycle_key(as_of) == "october":
        lines = [_line_dto(store, r, as_of) for r in raw_lines]
    else:
        lines = [_line_dto(store, r, as_of) for r in _november_visible_rows(raw_lines)]

    # LLM decides approve vs hold for each line (replaces hard-coded match heuristics in the UI).
    if window == "open":
        attach_llm_decisions(lines)

    line_counts = _line_summary_counts(lines, counts) if november_view else counts
    remaining = sum(1 for l in lines if not l["approved"])
    badge = remaining if window == "open" and not active else 0

    if window == "closed":
        unapplied = [] if active else _unapplied(store, lines)
        arrears_n = sum(1 for u in unapplied if u.get("kind") == "arrears")
        recovery_n = sum(1 for u in unapplied if u.get("kind") == "recovery")
        emp_count = counts["employeeCount"]
        if active and signoff:
            summary = (
                f"Payroll approved {short_date(signoff['signed_on'])} · {emp_count} employees"
                + (f" · funding {funding_label}" if funding_label else "")
            )
            tone = "ok"
            header = f"Review closed {close_label} · payroll approved"
        else:
            n = len(unapplied)
            summary = (
                f"Payroll not approved · {n} changes not applied · "
                f"{arrears_n} arrears, {recovery_n} recoveries moved to November"
            )
            tone = "danger"
            header = (
                f"Review closed {close_label} · payroll not approved · next review opens {next_open}"
            )

        return {
            **base,
            "header": header,
            "closedMessage": summary,
            "closedSummary": {
                "tone": tone,
                "message": summary,
                "employees": unapplied,
                "nextHref": (
                    "/payroll/review"
                    if parse_date(as_of) >= parse_date(next_c["reviewOpen"])
                    else "/payroll/overview"
                ),
                "nextLinkLabel": f"These will need your approval {next_open}–{next_close} →",
            },
            "closedWithoutSignOff": not active,
            "unappliedChanges": unapplied,
            "changedLines": line_counts["changedLines"],
            "matchedLines": line_counts["matchedLines"],
            "needsHumanCheck": line_counts["needsHumanCheck"],
            "numbersLabel": "Final October numbers" if october_closed_view or cd["key"] == "october" else "Final numbers",
            "lines": lines,
            "remaining": remaining,
            "canSignOff": False,
            "signOffHint": "Review window closed",
            "signedOff": active,
            "badgeCount": 0,
            "signoff": (
                {
                    "signedOn": signoff["signed_on"],
                    "signedAt": signoff["signed_at"],
                    "signedBy": signoff["signed_by"],
                    "reopened": False,
                    "reopenedNote": None,
                }
                if signoff and active
                else None
            ),
            "approved": active,
        }

    left = review_countdown(as_of)
    header = f"Review open · closes {close_label} · {left}"
    if parse_date(as_of) == close_d:
        header = "Review open · Closes today"

    return {
        **base,
        "available": True,
        "readOnly": False,
        "header": header,
        "closedMessage": None,
        "changedLines": line_counts["changedLines"],
        "matchedLines": line_counts["matchedLines"],
        "needsHumanCheck": line_counts["needsHumanCheck"],
        "lines": lines,
        "remaining": remaining,
        "badgeCount": badge,
        "canSignOff": remaining == 0 and not active,
        "signOffHint": None
        if remaining == 0
        else f"Approve {remaining} remaining line{'s' if remaining != 1 else ''} to approve payroll",
        "signedOff": active,
        "signoff": (
            {
                "signedOn": signoff["signed_on"],
                "signedAt": signoff["signed_at"],
                "signedBy": signoff["signed_by"],
                "reopened": reopened,
                "reopenedNote": signoff.get("reopened_note") if reopened else None,
            }
            if signoff
            else None
        ),
        "approved": active,
    }


def approve_line(store: Store, customer_id: str, line_id: str, as_of: str, actor: str = "HR admin") -> Dict[str, Any]:
    _assert_window_open(as_of)
    cycle = store.get_current_cycle(customer_id)
    if cycle:
        _sync_november_review(store, cycle, as_of)
    line = store.get_review_line(line_id)
    if not line:
        raise LookupError(f"Review line not found: {line_id}")
    if store.line_approval(line_id, as_of):
        return get_review(store, customer_id, as_of)
    store.approve_line(line_id, approved_on=as_of, approved_by=actor)
    return get_review(store, customer_id, as_of)


def unapprove_line(store: Store, customer_id: str, line_id: str, as_of: str, actor: str = "HR admin") -> Dict[str, Any]:
    _assert_window_open(as_of)
    line = store.get_review_line(line_id)
    if not line:
        raise LookupError(f"Review line not found: {line_id}")
    if not store.line_approval(line_id, as_of):
        return get_review(store, customer_id, as_of)
    store.revoke_line_approval(line_id, revoked_on=as_of, reason=f"Undo by {actor}")
    return get_review(store, customer_id, as_of)


def ensure_edited_line(
    store: Store,
    emp: Dict[str, Any],
    *,
    as_of: str,
    change_summary: str,
    why_flagged: Optional[str] = None,
    matching_source: Optional[str] = None,
) -> None:
    if review_window_state(as_of) == "closed":
        raise PermissionError("Review window is closed — edits are read-only")
    cycle = store.get_current_cycle(emp["customer_id"])
    assert cycle
    existing = store.review_line_for_employee(cycle["id"], emp["id"])
    why = why_flagged or "Edited by you – needs approval"
    source = matching_source or why
    after_cutoff = rules_svc.input_finalisation_passed(as_of)
    created_on = rules_svc.review_line_created_on(as_of)
    origin = "november" if after_cutoff else "edited"
    if existing:
        store.update_review_line(
            existing["id"],
            change_summary=change_summary,
            why_flagged=why,
            matching_source=source,
            origin=origin,
            created_on=created_on if after_cutoff else (existing.get("created_on") or as_of),
        )
        if store.line_approval(existing["id"]):
            store.revoke_line_approval(existing["id"], revoked_on=as_of, reason="edited by HR admin")
    else:
        store.insert_review_line(
            {
                "id": f"rev_edit_{emp['id']}",
                "cycle_id": cycle["id"],
                "employee_id": emp["id"],
                "employee_name": emp["name"],
                "country": emp["country"],
                "change_summary": change_summary,
                "why_flagged": why,
                "matching_source": source,
                "origin": origin,
                "created_on": created_on,
            }
        )
    store.update_employee_fields(emp["id"], edited_by_you=1, changed_this_cycle=1)


def reopen_matched(store: Store, customer_id: str, employee_id: str, as_of: str) -> Dict[str, Any]:
    """Move an auto-matched employee into Need your check."""
    _assert_window_open(as_of)
    emp = store.get_employee(employee_id)
    if not emp or emp["customer_id"] != customer_id:
        raise LookupError("employee_not_found")
    if not emp.get("matched_source"):
        raise ValueError("Employee is not auto-matched")
    source = emp["matched_source"]
    store.update_employee_fields(employee_id, matched_source=None, edited_by_you=1, changed_this_cycle=1)
    ensure_edited_line(
        store,
        emp,
        as_of=as_of,
        change_summary=f"Reopened · was matched to {source}",
        why_flagged="Reopened for review – needs approval",
        matching_source="Reopened by HR admin",
    )
    rules_svc.after_input_change(store, store.get_current_cycle(customer_id), employee_id, as_of=as_of, what="reopen")
    return get_review(store, customer_id, as_of)


def _signoff_footer_summary(
    store: Store,
    customer_id: str,
    review: Dict[str, Any],
    as_of: str,
    actor: str,
) -> Dict[str, Any]:
    cd = cycle_dates(as_of)
    not_in = (review.get("notInRun") or {}).get("employees") or []
    carry = rules_svc.carry_overs(store, customer_id, as_of)
    moving = sorted({e["name"] for e in (not_in + carry)})
    emps = store.list_employees(customer_id, as_of=as_of)
    in_run = len(emps) - len(moving)
    approved_n = sum(1 for l in review.get("lines") or [] if l.get("approved"))
    cycle = store.get_current_cycle(customer_id)
    signoff_row = store.active_signoff(cycle["id"], as_of) if cycle else None
    return {
        "employeesInRun": in_run,
        "changesApproved": approved_n,
        "autoMatched": review.get("matchedLines") or 0,
        "movingToNextCycle": moving,
        "fundingDue": short_date(cd["fundingDue"]) if cd.get("fundingDue") else None,
        "approvedBy": actor,
        "approvedOn": as_of,
        "approvedAt": signoff_row["signed_at"] if signoff_row else clock_svc.stamp(as_of),
        "inThisRun": f"Employees in this run (complete data; {review['changedLines']} changed lines)",
        "movingToNovember": moving,
    }


def signoff(store: Store, customer_id: str, as_of: str, actor: str = "HR admin") -> Dict[str, Any]:
    _assert_window_open(as_of)
    review = get_review(store, customer_id, as_of)
    if review["remaining"] > 0:
        raise PermissionError(review["signOffHint"] or "Approve remaining lines to approve payroll")
    cycle = store.get_current_cycle(customer_id)
    assert cycle
    store.add_signoff(cycle["id"], signed_on=as_of, signed_by=actor)
    submission_svc.submit_approved(store, customer_id, as_of)
    not_in = review["notInRun"]["employees"]
    carry = rules_svc.carry_overs(store, customer_id, as_of)
    names = sorted({e["name"] for e in (not_in + carry)})
    clock = datetime.now().strftime("%H:%M")
    cd = cycle_dates(as_of)
    funding = short_date(cd["fundingDue"]) if cd.get("fundingDue") else short_date(OCT["fundingDue"])
    cycle_label = cd.get("label") or "payroll"
    store.add_notification(
        cycle["id"],
        send_date=as_of,
        recipient="HR admin",
        subject=f"You approved {cycle_label} at {clock}",
        body_summary=f"Payroll approved by {actor} · {short_date(as_of)}, {clock}. Funding due {funding} (finance).",
        actions=[],
        cta_label="Open Overview",
        cta_href="/payroll/overview",
        kind="signoff_confirm",
    )
    footer = _signoff_footer_summary(store, customer_id, review, as_of, actor)
    return {
        "signedOff": True,
        "signedOn": as_of,
        "signedBy": actor,
        "message": f"Payroll approved by {actor} · {short_date(as_of)}, {clock}. Funding due {funding} (finance).",
        "summary": footer,
        "review": get_review(store, customer_id, as_of),
    }


def patch_employee(
    store: Store,
    employee_id: str,
    body: Dict[str, Any],
    *,
    as_of: str,
    customer_id: str,
    confirm_ai: bool = False,
) -> Dict[str, Any]:
    if review_window_state(as_of) == "closed":
        raise PermissionError("Review window is closed — edits are read-only")
    emp = store.get_employee(employee_id)
    if not emp or emp["customer_id"] != customer_id:
        raise LookupError("employee_not_found")
    new_base = body.get("baseSalary", emp["base_salary"])
    allowances = body.get("allowances", emp.get("allowances") or 0)
    unpaid = body.get("unpaidLeaveDays", emp.get("unpaid_leave_days") or 0)
    try:
        new_base = float(new_base)
        allowances = float(allowances)
        unpaid = int(unpaid)
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid salary values") from exc

    salary = rules_svc.SalaryStructure(
        base=new_base,
        allowances=allowances,
        unpaid_leave_days=unpaid,
        one_time_payments=rules_svc.one_time_payments(store, employee_id, as_of),
        tax_rate=rules_svc.tax_rate(emp["country"]),
    )
    check = None if confirm_ai else rules_svc.ai_check_payload(emp, salary.gross)
    if check:
        raise AiCheckRequired(check)

    updates = {"base_salary": new_base, "allowances": allowances, "unpaid_leave_days": unpaid, "edited_by_you": 1, "changed_this_cycle": 1}
    if body.get("role"):
        updates["role"] = body["role"]
    if body.get("managerName") is not None:
        updates["manager_name"] = body["managerName"]
    if body.get("workEmail"):
        updates["work_email"] = body["workEmail"]
    store.update_employee_fields(employee_id, **updates)
    store.log_change(employee_id, "base_salary", emp["base_salary"], new_base, source="Edited by HR admin", as_of=as_of)

    cycle = store.get_current_cycle(customer_id)
    existing_line = store.review_line_for_employee(cycle["id"], employee_id) if cycle else None
    had_review_line = existing_line is not None
    signoff = store.active_signoff(cycle["id"], as_of) if cycle else None
    signoff_reopened = bool(
        signoff and signoff.get("reopened_on") and (not as_of or signoff["reopened_on"] <= as_of)
    )
    payroll_was_approved = bool(
        (cycle and cycle.get("approved")) or (signoff and not signoff_reopened)
    )
    admin_name = company_config().get("admin", {}).get("name") or "HR admin"

    change = f"{rules_svc.fmt_money(emp['currency'], emp['september_pay'])} → {rules_svc.fmt_money(emp['currency'], salary.net)}"
    ensure_edited_line(store, {**emp, **{"base_salary": new_base}}, as_of=as_of, change_summary=change)
    if payroll_was_approved and cycle:
        store.reopen_signoff(cycle["id"], reopened_on=as_of, note="1 line changed since approval")
        store.set_cycle_approved(cycle["id"], 0)
    rules_svc.after_input_change(store, cycle, employee_id, as_of=as_of, what="salary edited")
    if had_review_line and cycle:
        line = store.review_line_for_employee(cycle["id"], employee_id)
        if line:
            store.update_review_line(
                line["id"],
                change_summary=f"Approved · edited by {admin_name}",
            )
            store.approve_line(line["id"], approved_on=as_of, approved_by=admin_name)

    # Generic: base restored to last approved + OTP present → resolve pay_confirmation
    if abs(new_base - float(emp["september_pay"])) < 0.5 and store.one_time_payments(emp["id"], as_of):
        from server.services.inputs import _maybe_resolve_pay_confirmation

        _maybe_resolve_pay_confirmation(store, {**emp, "base_salary": new_base}, as_of)

    from server.services.validation import get_employee_detail

    return get_employee_detail(store, employee_id, as_of, customer_id)
