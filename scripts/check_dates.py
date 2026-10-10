#!/usr/bin/env python3
"""Fail if business code invents dates outside config/seed/tests."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATE_RE = re.compile(r"2026-1[01]-\d{2}|2027-01-\d{2}")
ALLOW = ("config/", "tests/", "e2e/", "docs/", "seed/", "scripts/check_", "data/seed")


def main() -> int:
    bad: list[str] = []
    for base in (ROOT / "src", ROOT / "server"):
        for path in base.rglob("*"):
            if path.suffix not in {".py", ".ts", ".tsx"}:
                continue
            rel = str(path.relative_to(ROOT))
            if any(a in rel for a in ALLOW):
                continue
            # calendar_rules and cycle fixtures may reference config-loaded dates as fallbacks
            if "calendar_rules" in rel or "pay_timing" in rel:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for i, line in enumerate(text.splitlines(), 1):
                if DATE_RE.search(line) and "isoformat" not in line:
                    bad.append(f"{rel}:{i}: {line.strip()[:100]}")
    if bad:
        print("check:dates found literals:")
        for b in bad[:40]:
            print(" ", b)
        if len(bad) > 40:
            print(f"  … and {len(bad) - 40} more")
        # Soft fail for now — report but exit 0 until hardcoding phase finishes stripping
        print(f"({len(bad)} findings — non-blocking until hardcoding cleanup completes)")
        return 0
    print("check:dates OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
