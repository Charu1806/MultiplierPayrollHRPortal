/**
 * Click every visible enabled button/link on key screens at key dates.
 * Cancels any confirm modal opened. Global guards must stay clean.
 */
import { test, expect } from '@playwright/test'
import { attachGuards, assertNoHorizontalOverflow } from './guards'

/** Core dates in default CI; expand locally with INVENTORY_FULL=1 */
const DATES =
  process.env.INVENTORY_FULL === '1'
    ? [
        '2026-10-12',
        '2026-10-15',
        '2026-10-17',
        '2026-10-22',
        '2026-10-28',
        '2026-11-01',
        '2026-11-17',
        '2026-12-01',
      ]
    : ['2026-10-12', '2026-10-17', '2026-11-17']

const ROUTES = [
  '/payroll/overview',
  '/payroll/actions',
  '/payroll/review',
  '/payroll/notifications',
  '/people',
  '/people/add',
]

async function setDate(page: import('@playwright/test').Page, asOf: string) {
  await page.goto(`/payroll/overview`)
  const picker = page.locator('select, [data-testid="date-picker"]').first()
  if (await picker.count()) {
    try {
      await picker.selectOption(asOf)
    } catch {
      /* date may be button list */
      await page.getByText(asOf.slice(5).replace('-', ' '), { exact: false }).first().click({ trial: true }).catch(() => {})
    }
  }
  // Fallback: store via API
  await page.request.put(`http://127.0.0.1:8788/api/demo/date`, {
    data: { date: asOf },
    headers: { 'X-Customer-Id': 'cust_acme', 'Content-Type': 'application/json' },
  })
  await page.reload()
}

test.describe('Inventory sweep', () => {
  for (const asOf of DATES) {
    test(`clickables @ ${asOf}`, async ({ page }) => {
      const guards = await attachGuards(page, { allowStatus: [409] })
      await setDate(page, asOf)

      for (const route of ROUTES) {
        await page.goto(route)
        await page.waitForLoadState('networkidle').catch(() => {})
        await assertNoHorizontalOverflow(page)

        const clickables = page.locator(
          'button:visible:not([disabled]), a[href]:visible, [role="button"]:visible:not([disabled])',
        )
        const n = await clickables.count()
        const limit = Math.min(n, 40)
        for (let i = 0; i < limit; i++) {
          const el = clickables.nth(i)
          const label = ((await el.innerText().catch(() => '')) || '').trim().slice(0, 40)
          if (/Reset demo|Approve payroll|Sign off/i.test(label)) continue
          try {
            await el.click({ timeout: 1500 })
          } catch {
            continue
          }
          const cancel = page.getByRole('button', { name: /Cancel|Close|Back/i }).first()
          if (await cancel.isVisible().catch(() => false)) {
            await cancel.click().catch(() => {})
          }
          // Escape any leftover modal
          await page.keyboard.press('Escape').catch(() => {})
        }
      }
      guards.assertClean()
    })
  }
})

test('people pagination visible', async ({ page }) => {
  await page.goto('/people')
  await expect(page.getByTestId('people-pagination')).toContainText(/Showing 1/)
})
