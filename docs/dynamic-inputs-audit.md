# Dynamic inputs audit — removed name / file special cases

Runtime behaviour must not branch on seed names, ids or filenames. Seed data and seed/integrity tests may still name them.

## Removed / generalized

| Location | What was removed |
|----------|------------------|
| `server/services/connector.py` | Entire Priya-only Manager requirement + `ensure_priya_issue` call; James bonus → `issue_002` / `rev_001` resolve. Connector now delegates to `inputs.py`. |
| `server/services/issue.py` | `ensure_priya_issue` → `ensure_missing_fields_issue` (calls `inputs.revalidate`). |
| `server/services/extraction.py` | Hard-coded `document_name="bonus_letter_james.pdf"`; `issue_002` / `rev_001` resolves. Bonus apply now resolves any open `pay_confirmation` for that employee. Added `parse_document_text` generic regex fallback. |
| `server/services/review.py` | `emp_james`-only arrears wording; James-only duplicate £8,000 cleanup; James-only salary split resolve. Replaced with generic carry wording, amount+type duplicate cleanup, `_maybe_resolve_pay_confirmation`. |
| `server/services/rules.py` | `TOTAL_WITH_JOINERS = 120 + 2` (Priya + Arjun). Use live counts via `live_employee_count` / DB. |
| `src/features/people/PayrollPanel.tsx` | `isJames` / `bonus_letter_james.pdf` attach button (UI follow-up). |
| `src/features/people/EmployeeProfilePage.tsx` | James-only “Split to base + bonus” gate on `emp_james` (generalize in UI). |
| `src/features/payroll/ActionsPage.tsx` | Prefer `kind === 'pay_confirmation'` over `issue_002` / James name. |
| `src/features/people/DriveAttach.tsx` | Fixed filename lists → labelled demo presets calling same attach API. |
| `context.md` §14.5 | Filename-keyed DEMO_FALLBACK → rule-based parser; presets are UI-only. |

## Still allowed (seed / tests only)

- `config/seed.json`, `config/cycle.json` `unsignedOutcomes` employeeIds
- `tests/test_seed_integrity.py`, document fixture edge cases, e2e demo script
- Plus-alias email docstring example mentioning Priya

## New pipeline entry points

- `server/services/inputs.py` — create / OTP / exit / preview / revalidate
- `server/services/findings.py` — config-driven findings
- `POST /api/inputs/preview`, `POST /api/documents/generate`
- `review.calculate_and_build_review`
