"""Issue sorting, open filters, and approve gate."""

from __future__ import annotations

from typing import Any, Iterable, List, Mapping, Optional, Sequence

SEVERITY_ORDER = {
    "blocking": 0,
    "deadline_risk": 1,
    "needs_confirmation": 2,
    "next_cycle": 3,
}


def severity_rank(severity: str) -> int:
    return SEVERITY_ORDER.get(severity, 99)


def open_issues(issues: Iterable[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return [i for i in issues if i.get("status") == "open"]


def sort_issues(issues: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """Blocking first, then by deadline ascending, then title."""
    return sorted(
        issues,
        key=lambda i: (
            severity_rank(str(i.get("severity", ""))),
            str(i.get("deadline", "9999-99-99")),
            str(i.get("title", "")),
        ),
    )


def can_approve(issues: Iterable[Mapping[str, Any]]) -> bool:
    """Approve disabled while any blocking issue is open."""
    return not any(
        i.get("status") == "open" and i.get("severity") == "blocking" for i in issues
    )


def held_employee_ids(issues: Iterable[Mapping[str, Any]]) -> set[str]:
    """Blocking open issues hold only named employees — never the whole run."""
    held: set[str] = set()
    for i in issues:
        if i.get("status") != "open" or i.get("severity") != "blocking":
            continue
        eid = i.get("employee_id")
        if eid:
            held.add(str(eid))
    return held


def resolve_issue(
    issues: Sequence[Mapping[str, Any]],
    issue_id: str,
    *,
    resolved_by: str = "HR admin",
    resolved_at: Optional[str] = None,
    log: Optional[str] = None,
) -> List[dict]:
    out: List[dict] = []
    for i in issues:
        row = dict(i)
        if row.get("id") == issue_id and row.get("status") == "open":
            row["status"] = "resolved"
            row["resolved_by"] = resolved_by
            if resolved_at:
                row["resolved_at"] = resolved_at
            if log:
                row["resolution_log"] = log
        out.append(row)
    return out
