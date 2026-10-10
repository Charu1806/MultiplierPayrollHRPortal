"""Derive per-country chips from open issues."""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Sequence

COUNTRIES = ("India", "UK", "Germany", "Brazil")


def country_status(
    country: str,
    issues: Iterable[Mapping[str, Any]],
) -> str:
    """
    On track | Action needed | Deadline risk

    - Any open blocking for that country → Action needed (or treat blocking as Action needed)
    - Any open deadline_risk → Deadline risk
    - Any open needs_confirmation → Action needed
    - Else On track
    """
    open_for = [
        i
        for i in issues
        if i.get("status") == "open" and i.get("country") == country
    ]
    if not open_for:
        return "On track"

    severities = {i.get("severity") for i in open_for}
    if "deadline_risk" in severities:
        return "Deadline risk"
    if "blocking" in severities or "needs_confirmation" in severities:
        return "Action needed"
    if "next_cycle" in severities:
        return "Action needed"
    return "Action needed"


def country_statuses(
    issues: Sequence[Mapping[str, Any]],
    countries: Sequence[str] = COUNTRIES,
) -> dict[str, str]:
    return {c: country_status(c, issues) for c in countries}
