"""Salary structure maths (context.md §8): tax, net, FnF, AI-check rule. Rates from config/rules.json."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional, Sequence, Union

from .calendar_rules import payment_apply_cycle, parse_date
from .config import rules_config

DateLike = Union[str, date]

_RULES = rules_config()
TAX_RATES: Dict[str, float] = _RULES["taxRates"]
DAYS_IN_MONTH: int = int(_RULES.get("daysInMonth", 30))
AI_UP = float(_RULES["aiCheck"]["upThreshold"])
AI_DOWN = float(_RULES["aiCheck"]["downThreshold"])


def tax_rate(country: str) -> float:
    return float(TAX_RATES.get(country, 0.0))


def _r(x: float) -> float:
    return round(float(x), 2)


@dataclass(frozen=True)
class OneTimePayment:
    type: str
    label: str
    amount: float
    recorded_on: str
    id: Optional[str] = None
    document_name: Optional[str] = None
    source: Optional[str] = None

    @property
    def cycle(self) -> str:
        return payment_apply_cycle(self.recorded_on)


@dataclass(frozen=True)
class SalaryStructure:
    base: float
    allowances: float
    unpaid_leave_days: int
    one_time_payments: Sequence[OneTimePayment]
    tax_rate: float
    cycle: str = "October"
    one_time_total: float = field(init=False, default=0.0)
    deductions: float = field(init=False, default=0.0)
    gross: float = field(init=False, default=0.0)
    tax: float = field(init=False, default=0.0)
    net: float = field(init=False, default=0.0)

    def __post_init__(self) -> None:
        one_time = sum(p.amount for p in self.one_time_payments if p.cycle == self.cycle)
        deductions = self.base * self.unpaid_leave_days / DAYS_IN_MONTH if self.unpaid_leave_days else 0.0
        gross = self.base + self.allowances + one_time - deductions
        tax = gross * self.tax_rate
        object.__setattr__(self, "one_time_total", _r(one_time))
        object.__setattr__(self, "deductions", _r(deductions))
        object.__setattr__(self, "gross", _r(gross))
        object.__setattr__(self, "tax", _r(tax))
        object.__setattr__(self, "net", _r(gross - tax))

    def to_dict(self) -> dict:
        return {
            "base": self.base,
            "allowances": self.allowances,
            "unpaidLeaveDays": self.unpaid_leave_days,
            "deductions": self.deductions,
            "oneTimePayments": [
                {
                    "id": p.id,
                    "type": p.type,
                    "label": p.label,
                    "amount": p.amount,
                    "recordedOn": p.recorded_on,
                    "cycle": p.cycle,
                    "documentName": p.document_name,
                    "source": p.source,
                }
                for p in self.one_time_payments
            ],
            "oneTimeTotal": self.one_time_total,
            "gross": self.gross,
            "taxRate": self.tax_rate,
            "tax": self.tax,
            "net": self.net,
            "cycle": self.cycle,
        }


def ai_check(september_pay: float, new_gross: float) -> Optional[dict]:
    """Return the AI-check payload when a pay change is > +50% or < −30% vs September."""
    if september_pay <= 0:
        return None
    ratio = new_gross / september_pay
    if ratio > 1 + AI_UP:
        return {"direction": "up", "ratio": round(ratio, 2), "multiple": _multiple(ratio)}
    if ratio < 1 - AI_DOWN:
        return {"direction": "down", "ratio": round(ratio, 2), "multiple": _multiple(ratio)}
    return None


def _multiple(ratio: float) -> str:
    if ratio >= 1.95:
        return f"{round(ratio)}x" if abs(ratio - round(ratio)) < 0.1 else f"{ratio:.1f}x"
    pct = round((ratio - 1) * 100)
    return f"{pct:+d}%"


@dataclass(frozen=True)
class FnF:
    prorated_salary: float
    notice_pay: float
    severance: float
    leave_encashment: float
    recoveries: float
    gross: float
    tax: float
    net: float
    days_worked: int

    def to_dict(self) -> dict:
        return {
            "proratedSalary": self.prorated_salary,
            "noticePay": self.notice_pay,
            "severance": self.severance,
            "leaveEncashment": self.leave_encashment,
            "recoveries": self.recoveries,
            "gross": self.gross,
            "tax": self.tax,
            "net": self.net,
            "daysWorked": self.days_worked,
        }


def fnf(
    *,
    base: float,
    country: str,
    last_working_day: DateLike,
    notice_pay: float = 0.0,
    severance: float = 0.0,
    leave_encashment_days: int = 0,
    recoveries: float = 0.0,
) -> FnF:
    """FnF = base × days worked/30 + notice pay + severance + leave encashment − recoveries − tax."""
    lwd = parse_date(last_working_day)
    days_worked = max(0, min(DAYS_IN_MONTH, lwd.day))
    prorated = base * days_worked / DAYS_IN_MONTH
    encash = base * leave_encashment_days / DAYS_IN_MONTH
    gross = prorated + notice_pay + severance + encash - recoveries
    tax = max(0.0, gross) * tax_rate(country)
    return FnF(
        prorated_salary=_r(prorated),
        notice_pay=_r(notice_pay),
        severance=_r(severance),
        leave_encashment=_r(encash),
        recoveries=_r(recoveries),
        gross=_r(gross),
        tax=_r(tax),
        net=_r(gross - tax),
        days_worked=days_worked,
    )
