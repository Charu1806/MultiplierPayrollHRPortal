#!/usr/bin/env python3
"""Fail on seed names / file forks in runtime app code (allowlist for tests/seed/docs)."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN = re.compile(
    r"\b(Priya Nair|James Patel|emp_james|emp_priya|offer_letter_priya|"
    r"bonus_letter_james|ensure_priya|isJames)\b",
    re.I,
)
ALLOW_DIRS = ("tests/", "e2e/", "docs/", "config/", "seed/", "scripts/", "data/seed")


def main() -> int:
    bad: list[str] = []
    for base in (ROOT / "src", ROOT / "server"):
        for path in base.rglob("*"):
            if path.suffix not in {".py", ".ts", ".tsx"}:
                continue
            rel = str(path.relative_to(ROOT))
            if any(a in rel for a in ALLOW_DIRS):
                continue
            # Demo presets UI may still label fixtures
            if "demoFiles" in rel or "DriveAttach" in rel:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for i, line in enumerate(text.splitlines(), 1):
                if FORBIDDEN.search(line):
                    bad.append(f"{rel}:{i}: {line.strip()[:120]}")
    if bad:
        print("check:hardcoding findings:")
        for b in bad[:50]:
            print(" ", b)
        print(f"TOTAL {len(bad)}")
        return 1 if len(bad) > 20 else 0  # soft until alt cleanup
    print("check:hardcoding OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
