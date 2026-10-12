"""Notification visibility rules."""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Sequence

from .calendar_rules import parse_date


def emails_visible_on(
    emails: Iterable[Mapping[str, Any]],
    prototype_date: str | Any,
) -> list[Mapping[str, Any]]:
    """Show only emails whose send_date ≤ prototype date, newest first."""
    proto = parse_date(prototype_date)
    visible = [
        e for e in emails if parse_date(str(e["send_date"])) <= proto
    ]
    return sorted(
        visible,
        key=lambda e: (
            parse_date(str(e["send_date"])).toordinal(),
            1 if e.get("created_at") else 0,
            str(e.get("created_at") or ""),
        ),
        reverse=True,
    )


def groups_issues_not_per_item_buttons(email: Mapping[str, Any]) -> bool:
    """Email has one CTA; actions are listed, not individually actionable in-mail."""
    actions = email.get("actions") or []
    # Structural invariant for seed/UI: action_count matches listed actions when present
    if "action_count" in email and actions:
        return int(email["action_count"]) == len(actions)
    return True


def filter_channel(
    notifications: Sequence[Mapping[str, Any]],
    channel: str = "email",
) -> list[Mapping[str, Any]]:
    return [n for n in notifications if n.get("channel", "email") == channel]
