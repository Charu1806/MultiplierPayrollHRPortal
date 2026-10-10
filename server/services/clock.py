"""Request-scoped prototype clock — as-of date with real wall time."""

from __future__ import annotations

from contextvars import ContextVar
from datetime import date, datetime

_as_of: ContextVar[str | None] = ContextVar("clock_as_of", default=None)


def set_as_of(iso_date: str | None) -> None:
    """Pin the calendar date for the current request (from ?asOf= / demo date)."""
    _as_of.set(iso_date)


def today() -> str:
    """ISO date: pinned as-of date, or real today."""
    pinned = _as_of.get()
    if pinned:
        text = str(pinned).strip()
        if "T" in text:
            return text.split("T", 1)[0]
        return text[:10]
    return date.today().isoformat()


def now() -> str:
    """ISO datetime: date from as-of (or today) + current wall-clock time."""
    d = datetime.strptime(today(), "%Y-%m-%d").date()
    wall = datetime.now().time().replace(microsecond=0)
    return datetime.combine(d, wall).isoformat(timespec="seconds")


def stamp(as_of: str | None = None) -> str:
    """ISO datetime on the demo date, with the current time of day.

    Passing as_of pins the prototype clock so later writes in this request
    do not fall back to the real calendar day.
    """
    if as_of:
        set_as_of(as_of)
    return now()
