import { test, expect } from '@playwright/test'

test('fund manager Yes marks funds added on that day', async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem('clarity.asOf', '2026-10-24')
    localStorage.setItem('clarity.persona', 'global')
  })
  await page.goto('/payroll/overview')
  await expect(page.getByRole('heading', { name: 'Overview' })).toBeVisible({ timeout: 20000 })
  const tracker = page.locator('section').filter({ hasText: 'Stage tracker' })
  await expect(tracker.getByText(/Add funds · /)).toBeVisible()
  await expect(tracker).not.toContainText('Funds added Oct')

  await page.goto('/people/notifications')
  await page.getByRole('button', { name: /please confirm funds are added/ }).click()
  await expect(page.getByRole('heading', { name: 'October: please confirm funds are added' })).toBeVisible({
    timeout: 20000,
  })
  await expect(page.getByText('Noah Grant, Fund manager').first()).toBeVisible()
  await page.getByTestId('funding-yes').click()
  await expect(page.getByText('Funds added Oct 24')).toBeVisible()

  await page.goto('/payroll/overview')
  await expect(tracker.getByText('Funds added Oct 24 · Noah Grant ✓')).toBeVisible()
})
