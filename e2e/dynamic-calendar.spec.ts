import { test, expect } from '@playwright/test'

async function openOn(page: import('@playwright/test').Page, asOf: string, persona = 'global') {
  await page.addInitScript((state) => {
    localStorage.setItem('clarity.asOf', state.asOf)
    localStorage.setItem('clarity.persona', state.persona)
  }, { asOf, persona })
  await page.goto('/payroll/overview')
  await expect(page.getByRole('heading', { name: 'Overview' })).toBeVisible({ timeout: 20000 })
}

test('November dashboard and inbox follow November', async ({ page }) => {
  await openOn(page, '2026-11-14')

  const summary = page.getByTestId('sync-summary')
  await expect(summary).toContainText('by Nov 15')
  await expect(summary).toContainText('Complete review by Nov 19')
  await expect(summary).toContainText('Final closure Nov 22')
  await expect(summary).toContainText('Payroll submitted Nov 27')
  await expect(summary).toContainText('Pay day Nov 29')
  await expect(summary).not.toContainText('Oct ')
  await expect(summary.getByRole('button', { name: /will miss payment/ })).toBeVisible()

  const tracker = page.locator('section').filter({ hasText: 'Stage tracker' })
  await expect(tracker.getByText('Input close', { exact: true })).toBeVisible()
  await expect(tracker).toContainText('Nov 15')
  await expect(tracker.getByText('Pay day', { exact: true })).toBeVisible()
  await expect(tracker).toContainText('Nov 29')
  await expect(tracker).not.toContainText('Oct ')

  await expect(page.getByTestId('previous-cycle-summary')).toHaveCount(0)
  await expect(page.getByText(/people will miss payment/)).toHaveCount(0)
  const earlier = page.getByTestId('previous-payrolls')
  await expect(earlier).toContainText('October payroll')
  await expect(earlier).toContainText('paid Oct 29')
  await expect(earlier).not.toContainText('November payroll')

  await summary.getByRole('button', { name: /will miss payment/ }).click()
  await expect(page.locator('#countries')).toBeInViewport()
  await expect(page.locator('#countries')).toContainText('India')
  await expect(page.locator('#countries')).toContainText('will miss payment')

  await page.goto('/people/notifications')
  const detail = page.getByTestId('email-detail')
  await expect(detail.getByRole('heading', { name: 'November: employee window is open' })).toBeVisible()
  await expect(detail).toContainText('Nov 15')
  await expect(detail).not.toContainText('Oct 15')
  await expect(detail).not.toContainText('October')
})

test('December dashboard follows December and keeps earlier payrolls', async ({ page }) => {
  await openOn(page, '2026-12-05', 'IN')

  const summary = page.getByTestId('sync-summary')
  await expect(summary).toContainText('by Dec 15')
  await expect(summary).toContainText('Complete review by Dec 19')
  await expect(summary).toContainText('Final closure Dec 22')
  await expect(summary).toContainText('Payroll submitted Dec 27')
  await expect(summary).toContainText('Pay day Dec 29')
  await expect(summary).not.toContainText('Nov ')
  await expect(summary).not.toContainText('Oct ')

  const tracker = page.locator('section').filter({ hasText: 'Stage tracker' })
  await expect(tracker).toContainText('Dec 15')
  await expect(tracker).toContainText('Dec 29')
  await expect(tracker).not.toContainText('Nov ')

  await expect(page.getByTestId('previous-cycle-summary')).toHaveCount(0)
  const earlier = page.getByTestId('previous-payrolls')
  await expect(earlier).toContainText('November payroll')
  await expect(earlier).toContainText('October payroll')

  await page.goto('/people/notifications')
  const detail = page.getByTestId('email-detail')
  await expect(detail.getByRole('heading', { name: 'December payroll schedule · India' })).toBeVisible()
  await expect(detail).toContainText('Dec 15')
  await expect(detail).not.toContainText('Nov 15')
})
