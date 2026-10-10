"""Pay timing flags (context.md §8) — cycle-aware for any active payroll month."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable, Optional, Sequence, Union

from .calendar_rules import (
    cycle_dates,
    next_cycle_dates,
    parse_date,
    previous_cycle_dates,
    short_date,
)

DateLike = Union[str, date]


@dataclass(frozen=True)
class PayFlag:
    level: str  # green | amber | red
    message: str
    run: str
    reason: Optional[str] = None
    instant_payment_disabled: bool = False

    @property
    def show_off_cycle_stub(self) -> bool:
        return self.instant_payment_disabled


def _format_missing(missing: Sequence[str]) -> str:
    if not missing:
        return ""
    if len(missing) == 1:
        return missing[0]
    if len(missing) == 2:
        return f"{missing[0]} and {missing[1]}"
    return ", ".join(missing[:-1]) + f" and {missing[-1]}"


def _sentence_case(field: str) -> str:
    """'Tax ID' → 'tax ID'; acronyms like 'PAN' are left alone."""
    if len(field) > 1 and field[1].islower():
        return field[0].lower() + field[1:]
    return field


def _month_name(cycle: dict) -> str:
    label = str(cycle.get("label") or "")
    if label:
        return label.split()[0]
    return str(cycle.get("key") or "").capitalize()


def _home_cycle(
    *,
    date_added: Optional[DateLike],
    prototype_date: date,
) -> dict:
    """Cycle the employee was targeting for pay (enrolment / hold window)."""
    if date_added is not None:
        return cycle_dates(date_added)
    # Existing employees (no dateAdded): October hold carries into early November
    # as "Missed October pay" until the next cycle fully owns the message.
    active = cycle_dates(prototype_date)
    if active["key"] == "october":
        return active
    prev = previous_cycle_dates(prototype_date)
    # Still past previous pay date → keep previous month wording for carry-over miss
    if prototype_date > parse_date(prev["payDate"]):
        return prev
    return active


def pay_timing(
    *,
    date_added: Optional[DateLike],
    missing_fields: Iterable[str] = (),
    prototype_date: DateLike,
    fixed_on: Optional[DateLike] = None,
    exit_recorded_on: Optional[DateLike] = None,
    cutoff: Optional[date] = None,
    pay_date: Optional[date] = None,
    next_cutoff: Optional[date] = None,
) -> PayFlag:
    """
    Cycle-aware pay timing:
    - Cutoffs and month names come from the cycle the employee belongs to
      (date_added's cycle, or October carry-over for existing staff).
    - dateAdded after that cycle's input finalisation → paid in the *next* cycle.
    - Explicit cutoff/pay_date/next_cutoff overrides remain for unit tests.
    """
    missing = [m for m in missing_fields if m]
    proto = parse_date(prototype_date)

    home = _home_cycle(date_added=date_added, prototype_date=proto)
    nxt = next_cycle_dates(home["payDate"] if home.get("payDate") else proto)
    # next_cycle_dates(value) uses active_cycle_key of value — pass home's open/pay
    nxt = next_cycle_dates(home.get("open") or home["inputFinalisation"])

    resolved_cutoff = cutoff if cutoff is not None else parse_date(home["inputFinalisation"])
    resolved_pay = pay_date if pay_date is not None else parse_date(home["payDate"])
    resolved_next_cut = (
        next_cutoff if next_cutoff is not None else parse_date(nxt["inputFinalisation"])
    )

    this_month = _month_name(home)
    next_month = _month_name(nxt)
    cut_label = short_date(resolved_cutoff)
    next_cut_label = short_date(resolved_next_cut)

    if exit_recorded_on is not None:
        exit_d = parse_date(exit_recorded_on)
        exit_home = cycle_dates(exit_d)
        exit_cut = parse_date(exit_home["inputFinalisation"])
        if exit_d <= exit_cut:
            return PayFlag(
                "green",
                f"FnF paid in {_month_name(exit_home)} payroll",
                _month_name(exit_home),
            )
        exit_next = next_cycle_dates(exit_home.get("open") or exit_home["inputFinalisation"])
        return PayFlag(
            "red",
            f"FnF moves to {_month_name(exit_next)} payroll",
            _month_name(exit_next),
            reason="exit recorded after cutoff",
            instant_payment_disabled=True,
        )

    if date_added is not None and parse_date(date_added) > resolved_cutoff:
        return PayFlag(
            "red",
            f"Added after {cut_label} cutoff → paid in {next_month}",
            next_month,
            reason="added after cutoff",
            instant_payment_disabled=True,
        )

    if missing:
        if proto <= resolved_cutoff:
            if date_added is None:
                label = _format_missing([_sentence_case(m) for m in missing])
                return PayFlag(
                    "red",
                    f"Held until {label} is added – fix by {cut_label}",
                    "Held",
                    reason="missing data",
                )
            label = _format_missing([_sentence_case(m) for m in missing])
            return PayFlag(
                "amber",
                f"Missing {label} – fix by {cut_label} for {this_month} pay",
                "Held",
                reason="missing data",
            )
        if proto <= resolved_pay:
            return PayFlag(
                "amber",
                f"Moved to {next_month} · fix by {next_cut_label}",
                next_month,
                reason="missing data",
                instant_payment_disabled=True,
            )
        return PayFlag(
            "red",
            f"Missed {this_month} pay. {next_month} pay at risk.",
            "At risk",
            reason="missing data",
            instant_payment_disabled=True,
        )

    if fixed_on is not None and parse_date(fixed_on) > resolved_cutoff:
        return PayFlag(
            "amber",
            f"Paid in {next_month} payroll",
            next_month,
            reason="missing data",
            instant_payment_disabled=True,
        )

    if proto >= resolved_pay:
        return PayFlag("green", f"Paid in {this_month}", this_month)
    return PayFlag("green", f"Payment on track for {this_month}", this_month)
