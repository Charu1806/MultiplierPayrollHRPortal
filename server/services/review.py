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
    cycle_for_new_input,
    next_cycle_dates,
    previous_cycle_dates,
    parse_date,
    review_bounds,
    review_countdown,
    review_window_state,
    short_date,
    show_october_closed_review,
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
    decision = store.line_decision(r["id"], as_of)
    rejected = bool(decision and (decision.get("decision") or "approved") == "rejected")
    approval = None if rejected else decision
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
        "needsHumanCheck": decision is None,
        "approved": approval is not None,
        "rejected": rejected,
        "approvedOn": decision["approved_on"] if decision else None,
        "approvedBy": decision["approved_by"] if decision else None,
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


def _unapplied(store: Store, lines: List[Dict[str, Any]], as_of: str) -> List[Dict[str, Any]]:
    """Unapproved lines: old base pay is deposited; the difference lands in the next cycle."""
    current = cycle_dates(as_of)
    nxt = next_cycle_dates(as_of)
    this_month = _month_name(current.get("label") or "")
    next_month = _month_name(nxt.get("label") or "")
    next_open = short_date(nxt["reviewOpen"])
    next_close = short_date(nxt["reviewClose"])
    out: List[Dict[str, Any]] = []
    for line in lines:
        if line.get("approved") or line.get("rejected"):
            continue
        eid = line.get("employeeId")
        emp = store.get_employee(eid) if eid else None
        if not emp:
            continue
        row = _live_carry_row(store, emp, as_of, pay_month=this_month)
        if not row:
            continue
        currency = emp.get("currency") or ""
        old_base = rules_svc.fmt_money(currency, float(emp.get("september_pay") or 0))
        kind = row["kind"]
        amt = rules_svc.fmt_money(currency, row["amount"])
        kind_label = "an arrear" if kind == "arrears" else "a deductible"
        note = (
            f"old base pay {old_base} deposited in {this_month} · "
            f"{amt} taken as {kind_label} in {next_month}"
        )
        out.append(
            {
                "id": eid,
                "name": line["employeeName"],
                "href": line.get("openHref") or "/people",
                "septemberPay": old_base,
                "changeSummary": line["changeSummary"],
                "kind": kind,
                "note": note,
                "banner": f"{line['employeeName']} — {note}",
                "nextReviewLabel": f"{next_open}–{next_close}",
            }
        )
    return out


def _month_name(label: str) -> str:
    parts = (label or "").split()
    return parts[0] if parts else "the next cycle"


def _carry_item(
    emp: Dict[str, Any],
    row: Dict[str, Any],
    next_cycle: str,
    *,
    tense: str,
) -> Dict[str, Any]:
    currency = emp.get("currency") or ""
    kind = row.get("kind") or "arrears"
    paid = row.get("octoberPaid")
    if paid is None:
        paid = emp.get("september_pay") or 0
    previous = rules_svc.fmt_money(currency, float(paid))
    difference = rules_svc.fmt_money(currency, float(row["amount"]))
    kind_label = "arrear" if kind == "arrears" else "deductible"
    article = "an" if kind_label == "arrear" else "a"
    if tense == "settled":
        note = (
            f"Old base pay {previous} was deposited. "
            f"The difference {difference} is in this cycle as {article} {kind_label}."
        )
    elif tense == "closed":
        note = (
            f"Not approved in time. Old base pay {previous} is deposited. "
            f"The difference {difference} is taken as {article} {kind_label} in {next_cycle}."
        )
    else:
        note = (
            f"If not approved in time, old base pay {previous} will be deposited. "
            f"The difference {difference} is taken as {article} {kind_label} in {next_cycle}."
        )
    return {
        "employeeId": emp["id"],
        "name": emp["name"],
        "kind": kind,
        "kindLabel": kind_label,
        "previousPay": previous,
        "difference": difference,
        "nextCycle": next_cycle,
        "note": note,
    }


def _live_carry_row(
    store: Store,
    emp: Dict[str, Any],
    as_of: str,
    *,
    pay_month: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Difference between last approved pay and this cycle, from the employee record."""
    month = pay_month or _month_name(cycle_dates(as_of).get("label") or "")
    struct = rules_svc.salary_structure(store, emp, as_of, cycle=month)
    payable = (
        float(emp.get("base_salary") or 0)
        + float(emp.get("allowances") or 0)
        + float(struct.one_time_total)
        - float(struct.deductions)
    )
    sept = float(emp.get("september_pay") or 0)
    diff = payable - sept
    if abs(diff) < 0.5:
        return None
    if diff > 0:
        return {"kind": "arrears", "amount": diff, "octoberPaid": sept}
    return {"kind": "recovery", "amount": -diff, "octoberPaid": sept}


def _annotate_unapproved_carry(
    store: Store,
    lines: List[Dict[str, Any]],
    next_cycle: str,
    tense: str,
    as_of: str,
) -> List[Dict[str, Any]]:
    """Unapproved lines: old base pay is deposited; the gap is next cycle's arrear or deductible."""
    items: List[Dict[str, Any]] = []
    for line in lines:
        if line.get("approved") or line.get("rejected") or (line.get("origin") or "") == "october_carry":
            continue
        eid = line.get("employeeId") or ""
        emp = store.get_employee(eid) if eid else None
        if not emp:
            continue
        row = _live_carry_row(store, emp, as_of)
        if not row:
            continue
        item = _carry_item(emp, row, next_cycle, tense=tense)
        line["carryNote"] = item["note"]
        items.append(item)
    return items


def _settled_carry_items(store: Store, cycle_id: str, as_of: str, pay_month: str) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for line in store.review_lines(cycle_id):
        if (line.get("origin") or "") != "october_carry":
            continue
        emp = store.get_employee(line.get("employee_id") or "")
        if not emp:
            continue
        row = _live_carry_row(store, emp, as_of, pay_month=pay_month)
        if not row:
            continue
        items.append(_carry_item(emp, row, "this cycle", tense="settled"))
    return items


def _carry_block(
    store: Store,
    cycle: Dict[str, Any],
    lines: List[Dict[str, Any]],
    *,
    november_view: bool,
    window: str,
    next_month: str,
    source_month: str,
    as_of: str,
) -> Optional[Dict[str, Any]]:
    if november_view:
        items = _settled_carry_items(store, cycle["id"], as_of, source_month)
        if items:
            return {
                "headline": (
                    f"{source_month} was not approved in time, so the old base pay was deposited. "
                    "These differences are in this cycle as an arrear or a deductible."
                ),
                "nextCycle": next_month,
                "settled": True,
                "items": items,
            }
        tracked = [
            line
            for line in _october_source_lines(store, cycle["id"])
            if _line_has_october_difference(store, line, as_of)
        ]
        if tracked and all(
            _october_change_approved(store, cycle["id"], line.get("employee_id") or "", as_of)
            for line in tracked
        ):
            return {
                "headline": (
                    f"{source_month} changes were approved in time, so the new amounts were paid. "
                    "No arrears or deductibles carried into this cycle."
                ),
                "nextCycle": next_month,
                "settled": True,
                "items": [],
            }
        return None
    if window == "before":
        return None
    tense = "open" if window == "open" else "closed"
    items = _annotate_unapproved_carry(store, lines, next_month, tense, as_of)
    if not items:
        if lines and all(line.get("approved") for line in lines):
            return {
                "headline": (
                    f"If a line is not manually approved in time, the old base pay is deposited. "
                    f"The difference is taken as an arrear or a deductible in {next_month}. "
                    f"Every line is approved, so nothing carries."
                ),
                "nextCycle": next_month,
                "settled": False,
                "items": [],
            }
        return None
    if tense == "open":
        headline = (
            f"If a line is not manually approved in time, the old base pay is deposited. "
            f"The difference is taken as an arrear or a deductible in {next_month}."
        )
    else:
        headline = (
            f"This review was not approved in time. The old base pay is deposited. "
            f"The difference is taken as an arrear or a deductible in {next_month}."
        )
    return {
        "headline": headline,
        "nextCycle": next_month,
        "settled": False,
        "items": items,
    }


def _assert_window_open(as_of: str) -> None:
    if review_window_state(as_of) != "open":
        raise PermissionError("Review window is not open")


def _october_source_lines(store: Store, cycle_id: str) -> List[Dict[str, Any]]:
    """October review rows. Carry rows and later-cycle rows are not sources."""
    seen = set()
    out: List[Dict[str, Any]] = []
    for row in store.review_lines(cycle_id):
        origin = row.get("origin") or ""
        if origin in ("october_carry", "exit") or str(row["id"]).startswith("rev_nov_"):
            continue
        eid = row.get("employee_id")
        if not eid or eid in seen:
            continue
        seen.add(eid)
        out.append(row)
    return out


def _line_has_october_difference(store: Store, line: Dict[str, Any], as_of: str) -> bool:
    emp = store.get_employee(line.get("employee_id") or "")
    if not emp:
        return False
    source_month = _month_name(previous_cycle_dates(as_of).get("label") or "")
    return _live_carry_row(store, emp, as_of, pay_month=source_month) is not None


def _carry_line_id(kind: str, employee_id: str) -> str:
    return f"rev_nov_{kind}_{employee_id}"


def _november_visible_rows(raw_lines: List[Dict[str, Any]], as_of: str) -> List[Dict[str, Any]]:
    """Lines that belong to the cycle being reviewed, not the month before or after."""
    cd = cycle_dates(as_of)
    start = str(cd["open"])
    end = str(next_cycle_dates(as_of)["open"])
    visible = []
    for row in raw_lines:
        origin = row.get("origin") or ""
        created = row.get("created_on") or ""
        if origin not in ("edited", "november", "october_carry", "exit") and created < start:
            continue
        if created and not (start <= created < end):
            continue
        visible.append(row)
    return visible


def _review_headline_counts(
    store: Store,
    customer_id: str,
    as_of: str,
    lines: List[Dict[str, Any]],
    rollup: Dict[str, int],
) -> Dict[str, int]:
    """Cards follow the employees on this review, not a fixed seed total.

    Auto-matched employees stay in Matched. Approving a line moves that person
    from Need your check into Matched. A changed flag with no pay difference and
    no review line is not counted.
    """
    emps = store.list_employees(customer_id, as_of=as_of)
    by_id = {e["id"]: e for e in emps}
    line_ids = {l.get("employeeId") for l in lines if l.get("employeeId")}
    approved_ids = {l.get("employeeId") for l in lines if l.get("approved") and l.get("employeeId")}
    changed_ids = set()
    for emp in emps:
        eid = emp["id"]
        if eid in line_ids or emp.get("matched_source"):
            changed_ids.add(eid)
            continue
        if not emp.get("changed_this_cycle"):
            continue
        sept = float(emp.get("september_pay") or 0)
        base = float(emp.get("base_salary") or 0)
        if abs(base - sept) > 0.5 or int(emp.get("unpaid_leave_days") or 0) > 0:
            changed_ids.add(eid)
    matched = 0
    for eid in changed_ids:
        emp = by_id.get(eid) or {}
        if eid in approved_ids or emp.get("matched_source"):
            matched += 1
    changed = len(changed_ids)
    return {
        "changedLines": changed,
        "matchedLines": matched,
        "needsHumanCheck": changed - matched,
        "employeeCount": rollup["employeeCount"],
    }


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
    cut = parse_date(cycle_dates(as_of)["inputFinalisation"])
    nxt_open = str(next_cycle_dates(as_of)["open"])
    for r in store.review_lines(cycle["id"], as_of=as_of):
        lid = r["id"]
        if lid.startswith("rev_nov_emp_"):
            store.delete_review_line(lid)
            continue
        eid = r.get("employee_id")
        origin = r.get("origin") or ""
        created = r.get("created_on")
        summary = r.get("change_summary") or ""
        emp = store.get_employee(eid) if eid else None
        source_month = _month_name(previous_cycle_dates(as_of).get("label") or "")
        live = _live_carry_row(store, emp, as_of, pay_month=source_month) if emp else None
        # Drop a later bonus line that repeats the October arrears amount.
        if live and live.get("kind") == "arrears" and origin in ("edited", "november"):
            try:
                amount_txt = str(int(round(float(live["amount"]))))
                if amount_txt and amount_txt in summary.replace(",", ""):
                    if "Bonus" in summary or "one-time" in summary.lower() or "One-time" in summary:
                        store.delete_review_line(lid)
                        continue
            except (TypeError, ValueError):
                pass
        if created and origin in ("edited", "november") and parse_date(created) > cut:
            store.update_review_line(lid, created_on=nxt_open, origin="november")


def _october_change_rejected(store: Store, cycle_id: str, employee_id: str, as_of: str) -> bool:
    """Rejected lines stay on old base pay and do not carry as an incorrect payment."""
    for row in store.review_lines(cycle_id):
        if row.get("employee_id") != employee_id:
            continue
        origin = row.get("origin") or ""
        if origin == "october_carry" or str(row["id"]).startswith("rev_nov_"):
            continue
        decision = store.line_decision(row["id"], as_of)
        if decision and (decision.get("decision") or "approved") == "rejected":
            return True
    return False


def _october_change_approved(store: Store, cycle_id: str, employee_id: str, as_of: str) -> bool:
    """True when the October line was manually approved, so nothing carries forward."""
    for row in store.review_lines(cycle_id):
        if row.get("employee_id") != employee_id:
            continue
        origin = row.get("origin") or ""
        if origin == "october_carry" or str(row["id"]).startswith("rev_nov_"):
            continue
        if store.line_approval(row["id"], as_of):
            return True
    return False


def _persist_november_carry_lines(store: Store, cycle: Dict[str, Any], as_of: str) -> None:
    """Next cycle opens with last cycle's unapproved gaps: arrears or deductibles."""
    source = previous_cycle_dates(as_of)
    source_month = _month_name(source.get("label") or "")
    created_on = str(cycle_dates(as_of).get("open") or "")
    signed_off = bool(cycle.get("approved"))
    kept = set()
    for line in _october_source_lines(store, cycle["id"]):
        eid = line.get("employee_id") or ""
        emp = store.get_employee(eid) if eid else None
        live = _live_carry_row(store, emp, as_of, pay_month=source_month) if emp else None
        approved = signed_off or _october_change_approved(store, cycle["id"], eid, as_of)
        rejected = _october_change_rejected(store, cycle["id"], eid, as_of)
        if not emp or not live or approved or rejected:
            for kind in ("arrears", "recovery"):
                stale = _carry_line_id(kind, eid)
                if store.get_review_line(stale):
                    store.delete_review_line(stale)
            continue
        kind = live["kind"]
        other = "recovery" if kind == "arrears" else "arrears"
        other_id = _carry_line_id(other, eid)
        if store.get_review_line(other_id):
            store.delete_review_line(other_id)
        currency = emp.get("currency") or ""
        amt = rules_svc.fmt_money(currency, live["amount"])
        label = "Arrears" if kind == "arrears" else "Deductible"
        sign = "+" if kind == "arrears" else "–"
        store.upsert_review_line(
            {
                "id": _carry_line_id(kind, eid),
                "cycle_id": cycle["id"],
                "employee_name": emp["name"],
                "employee_id": eid,
                "country": emp["country"],
                "change_summary": f"{label} {sign}{amt}",
                "why_flagged": f"From {source_month} review (not signed off)",
                "matching_source": label,
                "origin": "october_carry",
                "created_on": created_on,
                "requires_employee_notified": kind == "recovery",
            }
        )
        kept.add(eid)
    for row in store.review_lines(cycle["id"]):
        if (row.get("origin") or "") == "october_carry" and row.get("employee_id") not in kept:
            store.delete_review_line(row["id"])


def _sync_november_review(store: Store, cycle: Dict[str, Any], as_of: str) -> None:
    if show_october_closed_review(as_of) or active_cycle_key(as_of) != "november":
        return
    store.ensure_schema()
    _cleanup_november_review_lines(store, cycle, as_of)
    # Cycle reset is Nov 1, not the later calculation date — differences show as soon as November opens.
    _persist_november_carry_lines(store, cycle, as_of)


def exit_review_line_id(cycle_key: str, employee_id: str) -> str:
    return f"rev_{cycle_key}_exit_{employee_id}"


def upsert_exit_review_line(
    store: Store,
    emp: Dict[str, Any],
    exit_row: Dict[str, Any],
    as_of: str,
) -> None:
    """Review row for an exit: prorated days only, and next month when the exit is after lock-in."""
    cycle = store.get_current_cycle(emp["customer_id"])
    if not cycle:
        return
    cd = cycle_dates(as_of)
    plan = rules_svc.exit_pay_plan(emp, exit_row)
    net = rules_svc.fmt_money(emp["currency"], plan["fnf"]["net"])
    days = plan["daysWorked"]
    if plan["onHold"]:
        why = f"On hold for {plan['heldMonth']}. Prorated pay will be paid in {plan['payMonth']}."
    else:
        why = f"Prorated pay for {days} days will be paid in {plan['payMonth']}."
    store.upsert_review_line(
        {
            "id": exit_review_line_id(cd["key"], emp["id"]),
            "cycle_id": cycle["id"],
            "employee_id": emp["id"],
            "employee_name": emp["name"],
            "country": emp["country"],
            "change_summary": f"Exit · prorated {days} days · {net}",
            "why_flagged": why,
            "matching_source": f"Exit · last day {exit_row.get('last_working_day')}",
            "origin": "exit",
            "created_on": exit_row.get("recorded_on") or as_of,
        }
    )


def delete_exit_review_line(store: Store, emp: Dict[str, Any], as_of: str) -> None:
    cycle = store.get_current_cycle(emp["customer_id"])
    if not cycle:
        return
    cd = cycle_dates(as_of)
    line_id = exit_review_line_id(cd["key"], emp["id"])
    store.delete_line_approvals(line_id)
    store.delete_review_line(line_id)


def calculate_and_build_review(store: Store, customer_id: str, as_of: str) -> None:
    """Idempotent: upsert review lines for changed employees / OTPs in the active cycle."""
    cycle = store.get_current_cycle(customer_id)
    if not cycle:
        return
    cd = cycle_dates(as_of)
    opened = cd.get("open") or (cd["inputFinalisation"][:8] + "01")
    if parse_date(as_of) < parse_date(opened):
        return
    store.ensure_schema()
    if cd["key"] == "november":
        _sync_november_review(store, cycle, as_of)
    carried = set()
    for line in _october_source_lines(store, cycle["id"]):
        eid = line.get("employee_id") or ""
        if not eid:
            continue
        if (
            _october_change_approved(store, cycle["id"], eid, as_of)
            or store.get_review_line(_carry_line_id("arrears", eid))
            or store.get_review_line(_carry_line_id("recovery", eid))
        ):
            carried.add(eid)
    emps = store.list_employees(customer_id, as_of=as_of)
    for emp in emps:
        exit_row = store.get_exit(emp["id"], as_of)
        if exit_row:
            upsert_exit_review_line(store, emp, exit_row, as_of)
            continue
        # Already carried forward, or approved in October so nothing should carry or be rebuilt.
        if emp["id"] in carried:
            continue
        otps = store.one_time_payments(emp["id"], as_of)
        cycle_open = str(cd.get("open") or cd["inputFinalisation"][:8] + "01")
        cycle_otps = [
            p
            for p in otps
            if p.get("recorded_on") and cycle_for_new_input(p["recorded_on"])["key"] == cd["key"]
        ]
        if cycle_otps:
            last = cycle_otps[-1]
            recorded = str(last.get("recorded_on") or cycle_open)
            # A bonus saved after the previous cutoff is dated on this cycle's open,
            # so it shows here and not on the locked review.
            visible_on = recorded if recorded >= cycle_open else cycle_open
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
                    "created_on": visible_on,
                }
            )
            continue
        existing = store.current_review_line(cycle["id"], emp["id"])
        if existing:
            # Already scheduled. Opening this review (after the 15th) must not push it forward.
            continue
        added = emp.get("date_added") or ""
        if added and cycle_for_new_input(added)["key"] == cd["key"]:
            ensure_edited_line(
                store,
                emp,
                as_of=cycle_open,
                change_summary=f"New employee · {cd['label']}",
                why_flagged="New employee – needs approval",
                matching_source="Added by HR admin",
            )
    if cd["key"] == "november":
        _persist_november_carry_lines(store, cycle, as_of)


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
    next_month = _month_name(next_c.get("label") or "")
    this_month = _month_name(cd.get("label") or "")
    source_month = (
        _month_name(previous_cycle_dates(as_of).get("label") or "")
        if november_view
        else this_month
    )
    # Differences from an unsigned October review land as soon as November opens, including before Nov 17.
    if november_view:
        _sync_november_review(store, cycle, as_of)
    # October review lines come from seed; rebuild only for November+ cycles
    if window != "before" and not october_closed_view and active_cycle_key(as_of) != "october":
        calculate_and_build_review(store, customer_id, as_of)

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
        "ifUnapproved": None,
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
            "ifUnapproved": _carry_block(
                store,
                cycle,
                [],
                november_view=november_view,
                window=window,
                next_month=next_month,
                source_month=source_month,
                as_of=as_of,
            ),
        }

    raw_lines = store.review_lines(cycle["id"], as_of=as_of)
    if october_closed_view or active_cycle_key(as_of) == "october":
        lines = [_line_dto(store, r, as_of) for r in raw_lines]
    else:
        lines = [_line_dto(store, r, as_of) for r in _november_visible_rows(raw_lines, as_of)]

    # LLM decides approve vs hold for each line (replaces hard-coded match heuristics in the UI).
    if window == "open":
        attach_llm_decisions(lines)

    if_unapproved = _carry_block(
        store,
        cycle,
        lines,
        november_view=november_view,
        window=window,
        next_month=next_month,
        source_month=source_month,
        as_of=as_of,
    )

    line_counts = (
        _line_summary_counts(lines, counts)
        if november_view
        else _review_headline_counts(store, customer_id, as_of, lines, counts)
    )
    remaining = sum(1 for l in lines if not l["approved"] and not l.get("rejected"))
    badge = remaining if window == "open" and not active else 0

    if window == "closed":
        unapplied = [] if active else _unapplied(store, lines, as_of)
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
                f"{arrears_n} arrears, {recovery_n} recoveries moved to {next_month}"
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
            "numbersLabel": f"Final {this_month} numbers",
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
            "ifUnapproved": if_unapproved,
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
        else f"Approve or reject {remaining} remaining line{'s' if remaining != 1 else ''} to approve payroll",
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
        "ifUnapproved": if_unapproved,
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


def reject_line(store: Store, customer_id: str, line_id: str, as_of: str, actor: str = "HR admin") -> Dict[str, Any]:
    """Send the change back to old base pay. It is not a missed or incorrect payment."""
    _assert_window_open(as_of)
    cycle = store.get_current_cycle(customer_id)
    if cycle:
        _sync_november_review(store, cycle, as_of)
    line = store.get_review_line(line_id)
    if not line:
        raise LookupError(f"Review line not found: {line_id}")
    current = store.line_decision(line_id, as_of)
    if current and (current.get("decision") or "approved") == "rejected":
        return get_review(store, customer_id, as_of)
    if current:
        store.revoke_line_approval(line_id, revoked_on=as_of, reason=f"Rejected by {actor}")
    store.reject_line(line_id, rejected_on=as_of, rejected_by=actor)
    return get_review(store, customer_id, as_of)


def unapprove_line(store: Store, customer_id: str, line_id: str, as_of: str, actor: str = "HR admin") -> Dict[str, Any]:
    _assert_window_open(as_of)
    line = store.get_review_line(line_id)
    if not line:
        raise LookupError(f"Review line not found: {line_id}")
    if not store.line_decision(line_id, as_of):
        return get_review(store, customer_id, as_of)
    store.revoke_line_approval(line_id, revoked_on=as_of, reason=f"Undo by {actor}")
    emp = store.get_employee(line.get("employee_id") or "")
    if emp and emp.get("matched_source") == "HR confirmation":
        store.update_employee_fields(emp["id"], matched_source=None)
    return get_review(store, customer_id, as_of)


def ensure_edited_line(
    store: Store,
    emp: Dict[str, Any],
    *,
    as_of: str,
    change_summary: str,
    why_flagged: Optional[str] = None,
    matching_source: Optional[str] = None,
    keep_visible: bool = False,
) -> None:
    if review_window_state(as_of) == "closed":
        raise PermissionError("Review window is closed — edits are read-only")
    cycle = store.get_current_cycle(emp["customer_id"])
    assert cycle
    existing = store.current_review_line(cycle["id"], emp["id"])
    why = why_flagged or "Edited by you – needs approval"
    source = matching_source or why
    after_cutoff = rules_svc.input_finalisation_passed(as_of)
    created_on = rules_svc.review_line_created_on(as_of)
    origin = "november" if after_cutoff else "edited"
    if existing and keep_visible:
        # A salary confirmed from the employee page stays on the open review and is approved.
        kept_origin = existing.get("origin") or "seed"
        kept_created = existing.get("created_on")
        if kept_origin == "november" or (kept_created and kept_created > as_of):
            kept_origin = "seed"
            kept_created = None
        store.update_review_line(
            existing["id"],
            change_summary=change_summary,
            why_flagged=why,
            matching_source=source,
            origin=kept_origin,
            created_on=kept_created,
        )
    elif existing:
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
    base_changed = abs(new_base - float(emp["base_salary"] or 0)) > 0.01
    check = None
    if base_changed and not confirm_ai:
        check = rules_svc.ai_check_payload(emp, new_base)
    if check:
        raise AiCheckRequired(check)

    from server.services.clock import stamp

    hr_fields = {
        "base_salary": new_base,
        "allowances": allowances,
        "unpaid_leave_days": unpaid,
        "updated_at": stamp(as_of),
        "updated_by": company_config().get("admin", {}).get("name") or "HR admin",
    }
    if body.get("role"):
        hr_fields["role"] = body["role"]
    if body.get("managerName") is not None:
        hr_fields["manager_name"] = body["managerName"]
    store.upsert_hr_employee(employee_id, **hr_fields)
    if body.get("workEmail"):
        store.update_employee_fields(employee_id, work_email=body["workEmail"])

    from server.services.validation import get_employee_detail

    detail = get_employee_detail(store, employee_id, as_of, customer_id)
    detail["savedIn"] = "hr"
    detail["saveMessage"] = "Saved in HR tool"
    return detail
