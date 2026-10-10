"""AI Explain Service — read-only notes; never mutates pay amounts."""

from __future__ import annotations

from typing import Any, Dict, Optional


def note_for_issue(issue: Dict[str, Any]) -> Optional[str]:
    return issue.get("ai_note")
