"""Unified pay outlook for the Employees table — one rule for every employee."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from domain.calendar_rules import (
    CUTOFF,
    NOV_CUTOFF,
    PAYMENT_RETURNED,
    PAY_DATE,
    cycle_dates,
    parse_date,
    prorate,
    short_date,
)

from server.db.repositories import Store
from server.services import rules as rules_svc

_PREV_MONTH = {
    "october": "September",
    "november": "October",
    "december": "November",
    "january": "December",
}


def pay_outlook(store: Store, emp: Dict[str, Any], as_of: str) -> Dict[str, Any]:
    """Return structured outlook; client only renders `display` / `tone` / `note`."""
    flag = rules_svc.pay_flag(store, emp, as_of)
    salary = rules_svc.salary_structure(store, emp, as_of).to_dict()
    otps = rules_svc.one_time_payments(store, emp["id"], as_of)
    missing = rules_svc.payment_missing_fields(store, emp, as_of)
    cd = cycle_dates(as_of)
    pay_date = parse_date(cd["payDate"])
    d = parse_date(as_of)
    after_pay = d >= pay_date
    month = cd["label"].split()[0]
    prev_month = _PREV_MONTH.get(cd.get("key") or "", "previous month")
    currency = emp["currency"]
    base = float(emp.get("base_salary") or 0)
    sept = float(emp.get("september_pay") or 0)
    monthly = float(salary.get("net") or base or sept)
    hire = emp.get("hire_date")
    fixed_on = rules_svc._payment_completed_on(store, emp, as_of)
    missed_october = _missed_october_pay(emp, as_of, missing, fixed_on, flag)

    exit_row = store.get_exit(emp["id"], as_of)
    if exit_row:
        plan = rules_svc.exit_pay_plan(emp, exit_row)
        net = float(plan["fnf"]["net"])
        money = rules_svc.fmt_money(currency, net)
        days = f"{plan['daysWorked']}/{plan['daysInMonth']} days"
        if plan["onHold"]:
            note = f"on hold for {plan['heldMonth']} · prorated {days} · pays {plan['payMonth']}"
            return _pack(net, currency, plan["payMonth"], "held", note, f"{money} · {plan['payMonth']}", "warn")
        note = f"prorated {days}"
        return _pack(net, currency, plan["payMonth"], "scheduled", note, f"{money} · {plan['payMonth']}", "ok")

    # --- Still missing required fields ---
    if missing or flag.run in ("Held", "At risk"):
        held_field = missing[0] if missing else (flag.reason or "data")
        if d > PAY_DATE and cd["key"] in ("november", "december", "january"):
            # Catch-up owed if they fix in time; otherwise slips further
            catch = _catch_up_amount(monthly, hire, as_of, cd, include_current=True)
            amount = catch["amount"]
            if d > NOV_CUTOFF or (cd["key"] == "november" and missing):
                # Still missing in November (or later) → pays in next cycle with caveat
                land = "December" if cd["key"] == "november" else _next_month(cd)
                tone = "danger"
                status = "held"
                display = f"{rules_svc.fmt_money(currency, amount)} · {land}"
                note = (
                    f"held: missing {held_field} · "
                    f"{catch['label']} combined if fixed; else pays in {land}"
                )
                if cd["key"] == "november" and missing:
                    note = (
                        f"held: missing {held_field} · "
                        f"Oct + Nov combined if fixed by {short_date(NOV_CUTOFF)}; "
                        f"otherwise pays in December"
                    )
                    display = f"{rules_svc.fmt_money(currency, amount)} · November"
                return _pack(amount, currency, month, status, note, display, tone)
            tone = "warn"
            status = "moves"
            display = f"{rules_svc.fmt_money(currency, amount)} · {month}"
            note = f"held: missing {held_field} · {catch['label']}"
            return _pack(amount, currency, month, status, note, display, tone)

        amount = monthly or sept or base
        if after_pay:
            status = "not_paid"
            tone = "danger"
            display = f"Not paid: moved to {_next_month(cd)}"
            note = f"held: missing {held_field}"
        else:
            status = "held"
            tone = "danger"
            display = f"{rules_svc.fmt_money(currency, amount)} · {month}"
            note = f"held: missing {held_field}"
        return _pack(amount, currency, month, status, note, display, tone)

    # --- Catch-up: missed October, now complete → Oct + Nov (or more) ---
    if missed_october and cd["key"] != "october":
        catch = _catch_up_amount(monthly, hire, as_of, cd, include_current=True)
        amount = catch["amount"]
        if after_pay:
            return _pack(
                amount,
                currency,
                month,
                "paid",
                catch["label"],
                f"Paid {rules_svc.fmt_money(currency, amount)} · {short_date(pay_date)}",
                "ok",
            )
        # Fixed after Oct cutoff → paid in this cycle as combined
        if flag.run == "November" or (fixed_on and parse_date(fixed_on) > CUTOFF):
            tone = "warn" if cd["key"] == "november" else "ok"
            return _pack(
                amount,
                currency,
                month,
                "scheduled",
                catch["label"],
                f"{rules_svc.fmt_money(currency, amount)} · {month}",
                tone,
            )

    # Moved to next cycle (other reasons)
    if flag.run == "November" and cd["key"] == "october":
        next_m = "November"
        if after_pay:
            return _pack(
                monthly,
                currency,
                month,
                "not_paid",
                flag.reason or "moved to next cycle",
                f"Not paid: moved to {next_m}",
                "danger",
            )
        return _pack(
            monthly,
            currency,
            month,
            "moves",
            flag.reason or f"moves to {next_m}",
            f"{rules_svc.fmt_money(currency, monthly)} · {month}",
            "warn",
        )

    # Returned payment
    if emp["id"] == "emp_david" and d >= PAYMENT_RETURNED:
        issue = store.get_issue("issue_david_return", as_of=as_of)
        if issue and issue.get("status") == "open":
            return _pack(monthly, currency, month, "returned", "Account closed", "Returned by bank", "warn")

    # After pay day — paid (single month)
    if after_pay:
        return _pack(
            monthly,
            currency,
            month,
            "paid",
            "",
            f"Paid {rules_svc.fmt_money(currency, monthly)} · {short_date(pay_date)}",
            "ok",
        )

    # First-month / mid-month joiner proration
    amount = monthly
    note = ""
    prorate_info = _first_month_prorate(monthly, hire, cd, as_of)
    if prorate_info:
        amount = prorate_info["amount"]
        note = (
            f"prorated from {short_date(hire)} · "
            f"{prorate_info['daysWorked']}/{prorate_info['daysInMonth']} days"
        )

    display = f"{rules_svc.fmt_money(currency, amount)} · {month}"

    if not note:
        bonuses = [p for p in otps if p.type == "Bonus" or "bonus" in (p.label or "").lower()]
        cycle_bonuses = [
            b
            for b in bonuses
            if not b.recorded_on
            or _otp_in_cycle(b.recorded_on, cd)
            or (b.cycle and month.lower() in str(b.cycle).lower())
        ]
        if cycle_bonuses and cd["key"] == "october":
            b = cycle_bonuses[0]
            note = f"includes {rules_svc.fmt_money(currency, b.amount)} bonus"

    if not note:
        baseline, raised_this_cycle = _baseline_vs_previous(store, emp, as_of, cd, sept, base)
        if raised_this_cycle and baseline > 0 and abs(base - baseline) > 0.5:
            delta = base - baseline
            sign = "+" if delta > 0 else "−"
            kind = " (raise)" if delta > 0 else ""
            note = f"changed: {sign}{rules_svc.fmt_money(currency, abs(delta))}{kind}"
        elif baseline > 0 or cd["key"] != "october":
            note = f"same as {prev_month}"

    return _pack(amount, currency, month, "scheduled", note, display, "ok")


def _missed_october_pay(
    emp: Dict[str, Any],
    as_of: str,
    missing: List[str],
    fixed_on: Optional[str],
    flag: Any,
) -> bool:
    """True when October pay was skipped due to missing data (now catching up or still open)."""
    d = parse_date(as_of)
    if d <= CUTOFF:
        return False
    if fixed_on and parse_date(fixed_on) > CUTOFF:
        return True
    if flag.reason == "missing data" and flag.run in ("November", "At risk", "Held"):
        return True
    if missing and d > PAY_DATE:
        return True
    # Seed joiners added after cutoff never got October
    date_added = emp.get("date_added")
    if date_added and parse_date(date_added) > CUTOFF:
        return False  # never owed October as a full employee month from before
    return False


def _month_pay(monthly: float, hire: Optional[str], year: int, month: int) -> float:
    """Full month or prorated if hire falls mid that month."""
    if not hire:
        return float(monthly)
    try:
        hd = parse_date(hire)
    except ValueError:
        return float(monthly)
    if hd.year == year and hd.month == month and hd.day > 1:
        return float(prorate(monthly, hire)["amount"])
    if hd.year > year or (hd.year == year and hd.month > month):
        return 0.0
    return float(monthly)


def _catch_up_amount(
    monthly: float,
    hire: Optional[str],
    as_of: str,
    cd: Dict[str, Any],
    *,
    include_current: bool,
) -> Dict[str, Any]:
    """Sum missed months through current cycle (Oct + Nov, or Oct+Nov+Dec, …)."""
    del include_current  # always include months through the active cycle
    d = parse_date(as_of)
    seen: Dict[str, float] = {}
    if d > CUTOFF:
        oct_amt = _month_pay(monthly, hire, 2026, 10)
        if oct_amt > 0:
            seen["Oct"] = oct_amt
    if d >= parse_date("2026-11-01") or cd["key"] in ("november", "december", "january"):
        nov_amt = _month_pay(monthly, hire, 2026, 11)
        if nov_amt > 0:
            seen["Nov"] = nov_amt
    if d >= parse_date("2026-12-01") or cd["key"] in ("december", "january"):
        dec_amt = _month_pay(monthly, hire, 2026, 12)
        if dec_amt > 0:
            seen["Dec"] = dec_amt
    ordered = [k for k in ("Oct", "Nov", "Dec") if k in seen]
    amount = round(sum(seen[k] for k in ordered), 2)
    label = " + ".join(ordered) + (" combined" if len(ordered) > 1 else "")
    return {"amount": amount, "label": label or "catch-up", "parts": seen}


def _first_month_prorate(
    monthly: float,
    hire: Optional[str],
    cd: Dict[str, Any],
    as_of: str,
) -> Optional[Dict[str, Any]]:
    if not hire:
        return None
    try:
        hd = parse_date(hire)
    except ValueError:
        return None
    if hd.day <= 1:
        return None
    # Prorate only in the cycle that contains the hire month
    pay = parse_date(cd["payDate"])
    if hd.year != pay.year or hd.month != pay.month:
        # October hire viewed in October cycle
        if not (cd["key"] == "october" and hd.month == 10 and hd.year == 2026):
            return None
    return prorate(monthly, hire)


def _cycle_window_start(cd: Dict[str, Any]) -> str:
    if cd.get("open"):
        return str(cd["open"])
    pay = parse_date(cd["payDate"])
    return f"{pay.year}-{pay.month:02d}-01"


def _otp_in_cycle(recorded_on: str, cd: Dict[str, Any]) -> bool:
    try:
        r = parse_date(recorded_on)
        start = parse_date(_cycle_window_start(cd))
        end = parse_date(cd["payDate"])
        return start <= r <= end
    except ValueError:
        return False


def _baseline_vs_previous(
    store: Store,
    emp: Dict[str, Any],
    as_of: str,
    cd: Dict[str, Any],
    september_pay: float,
    current_base: float,
) -> Tuple[float, bool]:
    if cd.get("key") == "october":
        raised = abs(current_base - september_pay) > 0.5
        return september_pay, raised

    start = _cycle_window_start(cd)
    try:
        logs = store.change_log(emp["id"], as_of)
    except Exception:  # noqa: BLE001
        logs = []
    salary_changes = [
        row
        for row in logs
        if (row.get("field") or "") in ("base_salary", "baseSalary", "Salary")
        and start <= str(row.get("as_of") or "") <= as_of
    ]
    if salary_changes:
        first = min(salary_changes, key=lambda r: (r.get("as_of") or "", r.get("id") or 0))
        try:
            old = float(first.get("old_value") or september_pay or 0)
        except (TypeError, ValueError):
            old = september_pay
        return old, True
    return current_base, False


def _next_month(cd: Dict[str, Any]) -> str:
    chain = {
        "october": "November",
        "november": "December",
        "december": "January",
        "january": "February",
    }
    return chain.get(cd.get("key") or "", "next cycle")


def _pack(
    amount: float,
    currency: str,
    month: str,
    status: str,
    note: str,
    display: str,
    tone: str,
) -> Dict[str, Any]:
    return {
        "amount": amount,
        "currency": currency,
        "month": month,
        "status": status,
        "note": note,
        "display": display,
        "tone": tone,
    }


def profile_pay_banner(store: Store, emp: Dict[str, Any], as_of: str, outlook: Dict[str, Any]) -> Dict[str, str]:
    """One banner for the employee profile: who gets paid, in which cycle."""
    from domain.calendar_rules import cycle_dates, cycle_for_new_input, next_cycle_dates

    currency = emp["currency"]
    sentences: List[str] = []

    exit_row = store.get_exit(emp["id"], as_of)
    if exit_row:
        plan = rules_svc.exit_pay_plan(emp, exit_row)
        sentences.append(str(plan.get("message") or outlook.get("note") or outlook.get("display") or ""))
        return _banner(sentences, outlook)

    if outlook.get("status") == "returned":
        sentences.append(
            "October payment was returned by the bank on 29 Oct. "
            "It will be re-sent in November 2026 (Nov 28) once the bank account is updated."
        )
        return _banner(sentences, outlook)

    missing = rules_svc.payment_missing_fields(store, emp, as_of)
    if missing:
        fields = _added_clause(missing)
        land = _salary_landing(emp, as_of)
        cut = short_date(land["inputFinalisation"])
        pay = short_date(land["payDate"])
        added = emp.get("date_added")
        late = ""
        if added:
            home = cycle_dates(added)
            if parse_date(added) > parse_date(home["inputFinalisation"]):
                late = f"Added after inputs closed on {short_date(home['inputFinalisation'])}. "
        if parse_date(as_of) > parse_date(land["inputFinalisation"]):
            nxt = next_cycle_dates(land["payDate"])
            sentences.append(
                f"{late}Not in this run until {fields} added. "
                f"Inputs for {land['label']} closed {cut}. "
                f"They will be paid in {nxt['label']} ({short_date(nxt['payDate'])})."
            )
        else:
            sentences.append(
                f"{late}Not in this run until {fields} added. "
                f"Will be paid in {land['label']} ({pay}) if fixed by {cut}."
            )
    else:
        sentences.append(_salary_sentence(store, emp, as_of, outlook))

    for payment in rules_svc.one_time_payments(store, emp["id"], as_of):
        kind = payment.type or ""
        label = payment.label or ""
        if kind != "Bonus" and "bonus" not in label.lower():
            continue
        if not payment.recorded_on:
            continue
        recorded = str(payment.recorded_on)
        land = cycle_for_new_input(recorded)
        money = rules_svc.fmt_money(currency, payment.amount)
        pay = short_date(land["payDate"])
        home = cycle_dates(recorded)
        if parse_date(recorded) > parse_date(home["inputFinalisation"]):
            closed = short_date(home["inputFinalisation"])
            sentences.append(
                f"Bonus of {money} was added after inputs closed on {closed}. "
                f"It will be paid in {land['label']} ({pay})."
            )
        else:
            sentences.append(f"Bonus of {money} will be paid in {land['label']} ({pay}).")

    hike = _hike_sentence(store, emp, as_of)
    if hike:
        sentences.append(hike)
    return _banner(sentences, outlook)


def _added_clause(fields: List[str]) -> str:
    text = rules_svc.sentence_fields(fields)
    verb = "is" if len(fields) == 1 else "are"
    return f"{text} {verb}"


def _banner(sentences: List[str], outlook: Dict[str, Any]) -> Dict[str, str]:
    text = " ".join(s.strip() for s in sentences if s and s.strip())
    late = "after inputs closed" in text or "Not in this run" in text
    if outlook.get("status") in ("held", "not_paid", "returned") or outlook.get("tone") == "danger":
        tone = "danger"
    elif late or outlook.get("tone") == "warn" or outlook.get("status") == "moves":
        tone = "warn"
    elif outlook.get("status") == "paid":
        tone = "ok"
    else:
        tone = "info"
    return {"text": text, "tone": tone}


def _salary_landing(emp: Dict[str, Any], as_of: str) -> Dict[str, Any]:
    from domain.calendar_rules import cycle_dates, cycle_for_new_input

    added = emp.get("date_added")
    if added:
        return cycle_for_new_input(added)
    return cycle_dates(as_of)


def _salary_sentence(store: Store, emp: Dict[str, Any], as_of: str, outlook: Dict[str, Any]) -> str:
    from domain.calendar_rules import cycle_dates, cycle_for_new_input

    status = outlook.get("status")
    if status == "returned":
        return "October payment was returned by the bank. It will be re-sent once bank details are updated."
    if status == "paid":
        text = str(outlook.get("display") or "Paid")
        return text if text.endswith(".") else f"{text}."

    added = emp.get("date_added")
    if added:
        home = cycle_dates(added)
        land = cycle_for_new_input(added)
        pay = short_date(land["payDate"])
        if parse_date(added) > parse_date(home["inputFinalisation"]):
            closed = short_date(home["inputFinalisation"])
            return (
                f"Added after inputs closed on {closed}. "
                f"Will be paid in {land['label']} ({pay})."
            )
        return f"Will be paid in {land['label']} ({pay})."

    cd = cycle_dates(as_of)
    if status in ("moves", "not_paid"):
        nxt = _next_month(cd)
        return f"Will not be paid in {cd['label']}. Pay moves to {nxt}."
    return f"Will be paid in {cd['label']} ({short_date(cd['payDate'])})."


def _hike_sentence(store: Store, emp: Dict[str, Any], as_of: str) -> str:
    from domain.calendar_rules import cycle_dates, cycle_for_new_input, next_cycle_dates

    try:
        logs = store.change_log(emp["id"], as_of)
    except Exception:  # noqa: BLE001
        logs = []
    changes = [row for row in logs if (row.get("field") or "") == "base_salary" and row.get("as_of")]
    if not changes:
        return ""
    last = changes[-1]
    when = str(last["as_of"])
    try:
        amount = float(last.get("new_value") or 0)
    except (TypeError, ValueError):
        return ""
    if amount <= 0:
        return ""
    money = rules_svc.fmt_money(emp["currency"], amount)
    home = cycle_dates(when)
    land = cycle_for_new_input(when)
    pay = short_date(land["payDate"])
    if parse_date(when) > parse_date(home["inputFinalisation"]):
        if _hike_stays_on_open_review(store, emp, when, as_of):
            return (
                f"New monthly salary of {money} will be paid in {home['label']} "
                f"({short_date(home['payDate'])})."
            )
        closed = short_date(home["inputFinalisation"])
        return (
            f"New monthly salary of {money} was added after inputs closed on {closed}. "
            f"It will be paid in {land['label']} ({pay}). This cycle pays the previous salary."
        )
    return f"New monthly salary of {money} will be paid in {land['label']} ({pay})."


def _hike_stays_on_open_review(store: Store, emp: Dict[str, Any], when: str, as_of: str) -> bool:
    """A hike saved during an open review stays on that review when the row was approved there."""
    from domain.calendar_rules import next_cycle_dates

    cycle = store.get_current_cycle(emp["customer_id"])
    if not cycle:
        return False
    line = store.current_review_line(cycle["id"], emp["id"])
    if not line or not store.line_approval(line["id"], as_of):
        return False
    created = line.get("created_on") or ""
    nxt_open = str(next_cycle_dates(when).get("open") or "")
    if created and nxt_open and created >= nxt_open:
        return False
    return True
