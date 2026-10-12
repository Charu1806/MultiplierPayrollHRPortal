# Test report

## Suite orchestration

`npm test` runs:

1. `check:dates`
2. `check:hardcoding`
3. `pytest tests/`
4. `vitest run`
5. `playwright test` (bugs + inventory + demo)

`npm run test:e2e:ui` for interactive Playwright debugging.

## Datasets

| DATASET | Company | Cutoff | Spike threshold |
|---------|---------|--------|-----------------|
| acme (default) | Acme Tech / Workday | 15th | +50% |
| alt | Northwind Labs / BambooHR | 10th | +40% |

Load alt with `DATASET=alt` before seeding / starting the API. Config loader: `data/domain/config.py`.

## Config-change demos (no code change)

1. Change `config/cycle.json` october `inputFinalisation` → Overview countdown and confirm messages move.
2. Change `config/rules.json` `taxRates.India` → salary net and OTP tax lines change.
3. Change `config/company.json` `admin.name` → review “Approved · edited by …” uses the new name.

## Bugs fixed this pass

1. **Pay this cycle** — `pay_outlook()`; no “Paid in October” before payday.
2. **Pagination** — footer + URL; e2e asserts Showing 1–25 of N.
3. **Powered by Multiplier** — sidebar caption on the Payroll group. People page headers do not repeat it.
4. **Remind** — stores an in-app email for the country admin and for Global. Undelivered only when SMTP is configured and the send fails.
5. **Add details** — inline format validation; modal errors; toast z-index above modal.

## Inventory findings

- Sweep in `e2e/inventory.spec.ts` across key dates/routes; destructive actions (Reset demo, Approve payroll) skipped.
- Horizontal overflow guard attached.

## Skips

None intended. If Playwright inventory flakes on date picker, prefer API `PUT /api/demo/date` (already used).

## Counts (this pass)

| Layer | Result |
|-------|--------|
| pytest | All green (~190 tests including pay_outlook, field_normalize, alt_dataset) |
| vitest | 20 passed |
| Playwright bugs + pagination | 6 passed |
| check:dates / check:hardcoding | Soft-report mode while remaining literals migrate to config |
| DATASET=alt | Config load verified (`tests/test_alt_dataset.py`) |

Inventory full date matrix: set `INVENTORY_FULL=1` for Oct 12–Dec 1 sweep.
