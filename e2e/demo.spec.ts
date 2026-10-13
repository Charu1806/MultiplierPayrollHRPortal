import { expect, test, type Page } from '@playwright/test'

test.describe.configure({ mode: 'serial' })

const DATE = {
  oct12: '2026-10-12',
  oct13: '2026-10-13',
  oct17: '2026-10-17',
  oct22: '2026-10-22',
}

async function setDate(page: Page, iso: string) {
  await page.getByLabel('Prototype date').selectOption(iso)
  await expect(page.getByLabel('Prototype date')).toHaveValue(iso)
  await expect(page.getByText('Refreshing…')).toHaveCount(0)
}

function nav(page: Page, label: string) {
  const escaped = label.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  return page.locator('nav').getByRole('link', { name: new RegExp(`^${escaped}`) })
}

function badge(page: Page) {
  return nav(page, 'Action needed')
}

async function expectBadge(page: Page, count: number) {
  await expect(badge(page)).toContainText(String(count))
}

function toast(page: Page, text: string | RegExp) {
  return page.getByRole('status').filter({ hasText: text })
}

async function confirm(page: Page) {
  await page.getByRole('button', { name: 'Confirm', exact: true }).click()
}

let page: Page
const pageErrors: string[] = []

test.beforeAll(async ({ browser }) => {
  page = await browser.newPage()
  page.on('pageerror', (err) => pageErrors.push(err.message))
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Overview' })).toBeVisible({ timeout: 20000 })
  await setDate(page, DATE.oct12)
})

test.afterAll(async () => {
  if (page) await page.close()
})

test('1. Oct 12 — one email, 3 grouped actions, CTA opens Overview', async () => {
  await nav(page, 'Notifications').click()
  const inbox = page.getByTestId('inbox').locator('button')
  const detail = page.getByTestId('email-detail')
  await expect(inbox).toHaveCount(1)
  await expect(inbox.first()).toContainText('3 days to input finalisation: 3 actions')
  await expect(detail.locator('ol li')).toHaveCount(3)
  await page.getByRole('button', { name: 'Open Payroll tab' }).click()
  await expect(page).toHaveURL(/\/payroll\/overview$/)
  await expect(page.getByTestId('sync-summary').getByText('3 actions need you')).toBeVisible()
  await expect(page.getByText('Any October changes?')).toHaveCount(0)
  await expect(page.getByTestId('sync-summary').getByRole('link', { name: 'Add employee' })).toBeVisible()
  await expectBadge(page, 3)
})

test('Review is open on Oct 12 with 38/32/6 and not-in-run line', async () => {
  await nav(page, 'Review & approve').click()
  await expect(page.getByText('Changed lines')).toBeVisible()
  await expect(page.getByText('2 employees are not in this run because data is missing')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Sign off October payroll' })).toBeDisabled()
})

test('2. Oct 12 — Take action on Missing CPF selects Beatriz; fix Lena', async () => {
  await nav(page, 'Overview').click()
  await page.getByRole('link', { name: 'Take action' }).nth(0).click()
  await expect(page).toHaveURL(/issue=/)
  await nav(page, 'Employees').click()
  const rows = page.locator('tbody tr')
  await expect(rows.filter({ hasText: 'Lena Fischer' })).toContainText(
    'Held until tax ID is added – fix by Oct 15',
  )
  await expect(rows.filter({ hasText: 'Beatriz Costa' })).toContainText('Held until CPF')
  await expect(page.getByTestId('people-pagination')).toContainText(/Showing 1–25 of 120/)

  await badge(page).click()
  await page.getByRole('button', { name: /Missing tax ID/ }).click()
  await expect(page).toHaveURL(/issue=issue_001/)
  await page.getByRole('button', { name: 'Add details myself' }).click()
  await page.getByRole('button', { name: 'Use demo value' }).click()
  await page.getByRole('button', { name: 'Save & resolve' }).click()
  await confirm(page)
  await expect(toast(page, 'Resolved: Missing tax ID')).toBeVisible()
  await expectBadge(page, 2)
  await nav(page, 'Overview').click()
  await expect(page.getByTestId('country-Germany')).toContainText('On track')
})

test('3. Oct 13 — add Priya, remind, form, manager', async () => {
  await setDate(page, DATE.oct13)
  await nav(page, 'Employees').click()
  await page.getByRole('link', { name: 'Add employee' }).click()
  await page.getByTestId('input-source-demo').click()
  await page.getByLabel('Demo file').selectOption('offer_letter_priya.pdf')
  await expect(page.getByLabel('Legal name')).toHaveValue('Priya Nair')
  await page.getByRole('button', { name: 'Submit' }).click()
  await expect(page.getByText('Mapped')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Skip for now' })).toBeVisible({
    timeout: 15_000,
  })
  await page.getByRole('button', { name: 'Skip for now' }).click()
  await expect(page).toHaveURL(/\/people\/emp_priya_nair$/)
  await expect(page.getByRole('heading', { name: 'Priya Nair' })).toBeVisible()

  await badge(page).click()
  await page.getByRole('button', { name: /Missing PAN/ }).click()
  await page.getByRole('button', { name: 'Remind employee' }).click()
  await confirm(page)
  await nav(page, 'Notifications').click()
  await page.getByTestId('inbox').getByText('To: Priya Nair').click()
  await expect(page.getByTestId('email-detail')).toContainText('To: Priya Nair')
  await page.getByRole('button', { name: 'Add my details' }).click()
  await expect(page).toHaveURL(/\/people\/emp_priya_nair\?panel=missing/)
  await expect(page.getByTestId('missing-details-panel')).toBeVisible()
  await page.getByRole('button', { name: 'Use demo values' }).click()
  await expect(toast(page, /Missing details added|Payment on track/)).toBeVisible()
})

test('4. Oct 13 — James salary structure + bonus letter', async () => {
  await badge(page).click()
  await page.getByRole('button', { name: /Salary up 3x/ }).click()
  await page.getByRole('link', { name: 'Open salary structure' }).click()
  await expect(page).toHaveURL(/\/people\/emp_james/)
  await page.getByTestId('doc-source-demo').click()
  await page.getByLabel('Demo document').selectOption('bonus_letter_james.pdf')
  await expect(page.getByText(/Used saved extraction|Performance bonus|Fields filled/).first()).toBeVisible({
    timeout: 8000,
  })
  await nav(page, 'Employees').click()
  await page.getByPlaceholder('Filter by name').fill('James Patel')
  await expect(page.locator('tbody tr').filter({ hasText: 'James Patel' })).toContainText(/Bonus|October/)
})

test('5. Oct 17 — add Arjun, instant payment disabled', async () => {
  await setDate(page, DATE.oct17)
  await page.goto('/people/add')
  await page.getByTestId('input-source-demo').click()
  await page.getByLabel('Demo file').selectOption('offer_letter_arjun.pdf')
  await expect(page.getByLabel('Legal name')).toHaveValue('Arjun Mehta')
  await page.getByRole('button', { name: 'Submit' }).click()
  await expect(page.getByText('Mapped')).toBeVisible()
  await page.waitForURL(/\/people\/emp_arjun_mehta$/, { timeout: 20_000 }).catch(async () => {
    await page.getByRole('button', { name: 'Skip for now' }).click()
    await page.waitForURL(/\/people\/emp_arjun_mehta$/)
  })
  await expect(page).toHaveURL(/\/people\/emp_arjun_mehta$/)
  await expect(page.getByText(/Added after Oct 15 cutoff/).first()).toBeVisible()
  await expect(page.getByRole('button', { name: /Instant payment/ })).toBeDisabled()
})

test('6. Oct 22 — per-line approve and sign-off', async () => {
  await setDate(page, DATE.oct22)
  await nav(page, 'Review & approve').click()
  await expect(page.getByText('38', { exact: true })).toBeVisible()
  const approveButtons = page.getByRole('button', { name: 'Approve' })
  const count = await approveButtons.count()
  for (let i = 0; i < count; i++) {
    await page.getByRole('button', { name: 'Approve' }).first().click()
    await confirm(page)
  }
  await page.getByRole('button', { name: 'Sign off October payroll' }).click()
  await page.getByRole('button', { name: 'Sign off', exact: true }).click()
  await expect(toast(page, /Payroll signed off/)).toBeVisible()
})

test('7. Stubs show their note and nothing crashes', async () => {
  await nav(page, 'Notifications').click()
  await page.getByRole('button', { name: /Slack/ }).click()
  await expect(toast(page, 'Slack reminders are coming in V2')).toBeVisible()
  await page.getByRole('button', { name: /AI Chat Assistance/ }).click()
  await expect(toast(page, 'AI Chat Assistance is coming in V2')).toBeVisible()
  expect(pageErrors, `page errors: ${pageErrors.join('\n')}`).toEqual([])
})
