"""Cycle calendar, stage, and countdown rules (context.md §5). Dates come from config/cycle.json."""

from __future__ import annotations

import calendar
from datetime import date, datetime
from typing import Any, Dict, List, Literal, Union

from .config import cycle_config

DateLike = Union[str, date]
ReviewWindow = Literal["before", "open", "closed"]
CycleKey = Literal["october", "november", "december", "january"]


def _d(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


_CFG = cycle_config()
_OCT = _CFG["cycles"]["october"]
_NOV = _CFG["cycles"]["november"]
_DEC = _CFG["cycles"].get("december") or {}
_JAN = _CFG["cycles"].get("january") or {}

CUTOFF = _d(_OCT["inputFinalisation"])
CALCULATION = _d(_OCT.get("calculation") or "2026-10-16")
REVIEW_OPEN = _d(_OCT.get("reviewOpen") or "2026-10-17")
REVIEW_CLOSE = _d(_OCT.get("reviewClose") or _OCT["approval"])
APPROVAL = REVIEW_CLOSE
FUNDING_DUE = _d(_OCT["fundingDue"])
SUBMITTED = _d(_OCT["submitted"])
PAY_DATE = _d(_OCT["payDate"])

NOV_OPEN = _d(_NOV["open"])
NOV_CUTOFF = _d(_NOV["inputFinalisation"])
NOV_CALCULATION = _d(_NOV.get("calculation") or "2026-11-16")
NOV_REVIEW_OPEN = _d(_NOV.get("reviewOpen") or "2026-11-17")
NOV_REVIEW_CLOSE = _d(_NOV.get("reviewClose") or _NOV.get("approval") or "2026-11-22")
NOV_APPROVAL = NOV_REVIEW_CLOSE
NOV_PAY_DATE = _d(_NOV["payDate"])

DEC_OPEN = _d(_DEC["open"]) if _DEC.get("open") else date(2026, 12, 1)
DEC_CUTOFF = _d(_DEC["inputFinalisation"]) if _DEC.get("inputFinalisation") else date(2026, 12, 15)
DEC_CALCULATION = _d(_DEC.get("calculation") or "2026-12-16") if _DEC else date(2026, 12, 16)
DEC_REVIEW_OPEN = _d(_DEC.get("reviewOpen") or "2026-12-17") if _DEC else date(2026, 12, 17)
DEC_REVIEW_CLOSE = (
    _d(_DEC.get("reviewClose") or _DEC.get("approval") or "2026-12-22") if _DEC else date(2026, 12, 22)
)
DEC_APPROVAL = DEC_REVIEW_CLOSE
DEC_FUNDING_DUE = _d(_DEC["fundingDue"]) if _DEC.get("fundingDue") else date(2026, 12, 23)
DEC_SUBMITTED = _d(_DEC["submitted"]) if _DEC.get("submitted") else date(2026, 12, 25)
DEC_PAY_DATE = _d(_DEC["payDate"]) if _DEC.get("payDate") else date(2026, 12, 28)

JAN_OPEN = _d(_JAN["open"]) if _JAN.get("open") else date(2027, 1, 1)
JAN_CUTOFF = _d(_JAN["inputFinalisation"]) if _JAN.get("inputFinalisation") else date(2027, 1, 15)
JAN_CALCULATION = _d(_JAN.get("calculation") or "2027-01-16") if _JAN else date(2027, 1, 16)
JAN_REVIEW_OPEN = _d(_JAN.get("reviewOpen") or "2027-01-17") if _JAN else date(2027, 1, 17)
JAN_REVIEW_CLOSE = (
    _d(_JAN.get("reviewClose") or _JAN.get("approval") or "2027-01-22") if _JAN else date(2027, 1, 22)
)
JAN_APPROVAL = JAN_REVIEW_CLOSE
JAN_FUNDING_DUE = _d(_JAN["fundingDue"]) if _JAN.get("fundingDue") else date(2027, 1, 23)
JAN_SUBMITTED = _d(_JAN["submitted"]) if _JAN.get("submitted") else date(2027, 1, 25)
JAN_PAY_DATE = _d(_JAN["payDate"]) if _JAN.get("payDate") else date(2027, 1, 28)

_CYCLE_BY_KEY: Dict[CycleKey, Dict[str, Any]] = {
    "october": _OCT,
    "november": _NOV,
    "december": _DEC,
    "january": _JAN,
}

PROTOTYPE_DATES = tuple(_d(p["value"]) for p in _CFG["prototypeDates"])
PROTOTYPE_DATE_LABELS = tuple(p["label"] for p in _CFG["prototypeDates"])

STAGES = tuple(_CFG["stages"])
CALC_STAGE = "Calculation & final checks"


def _default_year_for_month(month: int) -> int:
    """Month-only strings in the prototype span Oct 2026–Jan 2027."""
    if month == 1:
        return 2027
    return 2026


def parse_date(value: DateLike) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    text = str(value).strip()
    if "T" in text:
        text = text.split("T", 1)[0]
    for fmt in ("%Y-%m-%d", "%b %d", "%b %d %Y", "%d %b %Y", "%b %d, %Y"):
        try:
            parsed = datetime.strptime(text, fmt)
            if parsed.year == 1900:
                return date(_default_year_for_month(parsed.month), parsed.month, parsed.day)
            return parsed.date()
        except ValueError:
            continue
    raise ValueError(f"Unrecognized date: {value!r}")


def short_date(value: DateLike) -> str:
    d = parse_date(value)
    return f"{d.strftime('%b')} {d.day}"


def active_cycle_key(value: DateLike) -> CycleKey:
    """From Nov 1 → November; Dec 1 → December; Jan 1 → January."""
    d = parse_date(value)
    if _JAN and d >= JAN_OPEN:
        return "january"
    if _DEC and d >= DEC_OPEN:
        return "december"
    return "november" if d >= NOV_OPEN else "october"


def _cycle_payload(key: CycleKey, c: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "key": key,
        "label": c["label"],
        "id": c["id"],
        "inputFinalisation": c["inputFinalisation"],
        "calculation": c.get("calculation"),
        "reviewOpen": c.get("reviewOpen") or c.get("approval"),
        "reviewClose": c.get("reviewClose") or c.get("approval"),
        "approval": c.get("reviewClose") or c.get("approval"),
        "fundingDue": c.get("fundingDue"),
        "submitted": c.get("submitted"),
        "payDate": c["payDate"],
        "open": c.get("open"),
    }


def cycle_by_key(key: CycleKey) -> Dict[str, Any]:
    return _cycle_payload(key, _CYCLE_BY_KEY[key])


def cycle_dates(value: DateLike) -> Dict[str, Any]:
    key = active_cycle_key(value)
    return _cycle_payload(key, _CYCLE_BY_KEY[key])


def next_cycle_dates(value: DateLike) -> Dict[str, Any]:
    """The cycle after the active one (October → November → December → January)."""
    key = active_cycle_key(value)
    chain: Dict[CycleKey, CycleKey] = {
        "october": "november",
        "november": "december",
        "december": "january",
        "january": "january",
    }
    nkey = chain[key]
    c = _CYCLE_BY_KEY[nkey]
    return _cycle_payload(nkey, c)


def previous_cycle_dates(value: DateLike) -> Dict[str, Any]:
    """The cycle before the active one (January → December → … → October)."""
    key = active_cycle_key(value)
    chain: Dict[CycleKey, CycleKey] = {
        "january": "december",
        "december": "november",
        "november": "october",
        "october": "october",
    }
    pkey = chain[key]
    c = _CYCLE_BY_KEY[pkey]
    return _cycle_payload(pkey, c)


def cycle_for_new_input(created_at: DateLike) -> Dict[str, Any]:
    """Input cycle: active cycle if created on/before its cutoff, else the next cycle."""
    d = parse_date(created_at)
    active = cycle_dates(d)
    cutoff = parse_date(active["inputFinalisation"])
    if d <= cutoff:
        return active
    return next_cycle_dates(d)


def cycle_containing_date(value: DateLike) -> Dict[str, Any]:
    """Payroll cycle whose calendar window contains `value` (open through day before next open)."""
    d = parse_date(value)
    if _JAN and d >= JAN_OPEN:
        return cycle_by_key("january")
    if _DEC and d >= DEC_OPEN:
        return cycle_by_key("december")
    if d >= NOV_OPEN:
        return cycle_by_key("november")
    return cycle_by_key("october")


def _cycle_sort_date(c: Dict[str, Any]) -> date:
    if c.get("payDate"):
        return parse_date(c["payDate"])
    if c.get("open"):
        return parse_date(c["open"])
    return parse_date("1900-01-01")


def first_pay_cycle(
    start_date: DateLike,
    input_cycle_key_or_dict: Union[CycleKey, Dict[str, Any]],
) -> Dict[str, Any]:
    """Later of the input cycle and the cycle containing the employee start date."""
    start_cycle = cycle_containing_date(start_date)
    if isinstance(input_cycle_key_or_dict, dict):
        input_cycle = input_cycle_key_or_dict
    else:
        input_cycle = cycle_by_key(input_cycle_key_or_dict)
    if _cycle_sort_date(input_cycle) >= _cycle_sort_date(start_cycle):
        return input_cycle
    return start_cycle


def prorate(monthly: float, start_date: DateLike) -> Dict[str, Any]:
    """First-month salary: days from start through month end ÷ calendar days in month."""
    d = parse_date(start_date)
    days_in_month = calendar.monthrange(d.year, d.month)[1]
    days_worked = days_in_month - d.day + 1
    fraction = days_worked / days_in_month
    amount = round(float(monthly) * fraction, 2)
    return {
        "amount": amount,
        "daysWorked": days_worked,
        "daysInMonth": days_in_month,
        "fraction": fraction,
        "formula": f"{monthly} × {days_worked}/{days_in_month}",
    }


def _month_start(d: date) -> date:
    return date(d.year, d.month, 1)


def _add_months(d: date, months: int) -> date:
    month_index = d.year * 12 + (d.month - 1) + months
    y, m = divmod(month_index, 12)
    return date(y, m + 1, 1)


def backdated_arrears_months(
    start_date: DateLike,
    first_pay_cycle_dict: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Calendar months from start month through the month before first pay cycle."""
    start_d = parse_date(start_date)
    pay_d = parse_date(first_pay_cycle_dict["payDate"])
    pay_month_start = _month_start(pay_d)
    cur = _month_start(start_d)
    out: List[Dict[str, Any]] = []
    while cur < pay_month_start:
        out.append(
            {
                "label": cur.strftime("%B %Y"),
                "monthKey": f"{cur.year}-{cur.month:02d}",
                "amountHint": "full monthly salary",
            }
        )
        cur = _add_months(cur, 1)
    return out


def _pay_month_name(cycle_dict: Dict[str, Any]) -> str:
    label = str(cycle_dict.get("label") or "")
    if label:
        return label.split()[0]
    return str(cycle_dict.get("key", "")).capitalize()


def payment_apply_cycle(recorded_on: DateLike) -> str:
    """Payroll month a one-time payment applies to (input cycle assignment)."""
    return _pay_month_name(cycle_for_new_input(recorded_on))


def review_bounds(value: DateLike) -> tuple[date, date]:
    """Review open/close for the cycle that owns `value` (October closed view uses Oct bounds through Oct 31)."""
    d = parse_date(value)
    if d >= JAN_OPEN:
        return JAN_REVIEW_OPEN, JAN_REVIEW_CLOSE
    if d >= DEC_OPEN:
        return DEC_REVIEW_OPEN, DEC_REVIEW_CLOSE
    if d < NOV_OPEN:
        return REVIEW_OPEN, REVIEW_CLOSE
    return NOV_REVIEW_OPEN, NOV_REVIEW_CLOSE


def review_window_state(value: DateLike, *, for_october_summary: bool = False) -> ReviewWindow:
    d = parse_date(value)
    if for_october_summary or (NOV_OPEN > d >= date(2026, 10, 23)):
        # Closed October review (Oct 23–31) or explicit October summary
        if d < REVIEW_OPEN:
            return "before"
        if d <= REVIEW_CLOSE:
            return "open"
        return "closed"
    open_, close = review_bounds(d)
    if d < open_:
        return "before"
    if d <= close:
        return "open"
    return "closed"


def show_october_closed_review(value: DateLike) -> bool:
    """Oct 23–31 show closed October review; from Nov 1 Review is November."""
    d = parse_date(value)
    return date(2026, 10, 23) <= d <= date(2026, 10, 31)


def _stage_nov_style(
    d: date,
    *,
    cutoff: date,
    review_open: date,
    review_close: date,
    pay_date: date,
) -> str:
    if d <= cutoff:
        return "Input finalisation"
    if d < review_open:
        return CALC_STAGE
    if d <= review_close:
        return "Review"
    if d < pay_date:
        return "Submitted"
    return "Paid"


def stage_for_date(value: DateLike) -> str:
    d = parse_date(value)
    if d >= JAN_OPEN:
        return _stage_nov_style(
            d,
            cutoff=JAN_CUTOFF,
            review_open=JAN_REVIEW_OPEN,
            review_close=JAN_REVIEW_CLOSE,
            pay_date=JAN_PAY_DATE,
        )
    if d >= DEC_OPEN:
        return _stage_nov_style(
            d,
            cutoff=DEC_CUTOFF,
            review_open=DEC_REVIEW_OPEN,
            review_close=DEC_REVIEW_CLOSE,
            pay_date=DEC_PAY_DATE,
        )
    if d >= NOV_OPEN:
        if d <= NOV_CUTOFF:
            return "Input finalisation"
        if d < NOV_REVIEW_OPEN:
            return CALC_STAGE
        if d <= NOV_REVIEW_CLOSE:
            return "Review"
        if d < NOV_PAY_DATE:
            return "Submitted"
        return "Paid"
    if d <= CUTOFF:
        return "Input finalisation"
    if d < REVIEW_OPEN:
        return CALC_STAGE
    if d <= REVIEW_CLOSE:
        return "Review"
    if d < SUBMITTED:
        return "Funding"
    if d < PAY_DATE:
        return "Submitted"
    return "Paid"


def _active_cutoff(d: date) -> date:
    if d >= JAN_OPEN:
        return JAN_CUTOFF
    if d >= DEC_OPEN:
        return DEC_CUTOFF
    if d >= NOV_OPEN:
        return NOV_CUTOFF
    return CUTOFF


def november_open(value: DateLike) -> bool:
    return parse_date(value) >= NOV_OPEN


def days_until_cutoff(value: DateLike) -> int:
    d = parse_date(value)
    cutoff = _active_cutoff(d)
    return (cutoff - d).days


def countdown_text(value: DateLike) -> str:
    d = parse_date(value)
    cutoff = _active_cutoff(d)
    if d > cutoff:
        return "Input finalisation closed"
    days = (cutoff - d).days
    if days == 0:
        return "Cutoff today"
    if days == 1:
        return "1 day left"
    return f"{days} days left"


def review_countdown(value: DateLike) -> str:
    _, close = review_bounds(value)
    d = parse_date(value)
    days = (close - d).days
    if days < 0:
        return "Review closed"
    if days == 0:
        return "Closes today"
    if days == 1:
        return "1 day left"
    return f"{days} days left"


def approval_countdown(value: DateLike) -> str:
    return review_countdown(value)


def unsigned_outcome_rows() -> list[Dict[str, Any]]:
    cfg = _CFG.get("unsignedOutcomes") or {}
    return list(cfg.get("arrears") or []) + list(cfg.get("recoveries") or [])
