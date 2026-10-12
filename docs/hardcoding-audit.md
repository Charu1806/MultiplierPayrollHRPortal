# Hardcoding audit

Runtime behaviour must not branch on seed names, ids, or filenames. Values come from config + DB + clock.

## Removed / generalized (this pass + prior dynamic-inputs)

| Item | Was | Now |
|------|-----|-----|
| Employees “will be paid” column | Client `payText` + `_will_be_paid` special cases; gen employees fell through to “Paid in October” | `pay_outlook()` server DTO; column **Pay this cycle** |
| Priya / James / issue_002 / rev_001 forks | connector, extraction, review, Actions `isJames` | inputs pipeline + kind-based pay_confirmation |
| TOTAL_WITH_JOINERS = 122 | rules.py | live DB counts |
| Filename DEMO_FALLBACK business logic | extraction filename table | regex parser + UI presets only |
| Powered by Multiplier | Repeated on People page headers | Sidebar caption on the Payroll group only, from `company.payrollCaption` |
| Dashboard and mail dates | Fixed October labels | Open cycle month from `cycle.json`. Covered by `tests/test_dynamic_calendar.py` and `e2e/dynamic-calendar.spec.ts` |
| Confirm toast under modal | z-50 both | Toast z-[70]; ConfirmModal errors for API |

## Still seed/test only

- `config/seed.json`, unsignedOutcomes employee ids
- `demoFiles.ts` / DriveAttach preset labels
- Seed integrity + named e2e paths (Lena, Beatriz) until rewritten to read from dataset config

## Alt dataset

- `config/alt/*` + `seed/alt.json` (Northwind Labs, BambooHR, cutoff 10th, spike +40%)
- Select with `DATASET=alt`

## Copy templates

- `src/copy/en.ts` — valued sentences as placeholders
