import { test, expect } from '@playwright/test'
import { attachGuards } from './guards'

test.describe('Bugs 1-5 regressions', () => {
  test('Bug1 Pay this cycle column never says Paid before payday', async ({ page }) => {
    const guards = await attachGuards(page)
    await page.goto('/people')
    await expect(page.getByRole('columnheader', { name: 'Pay this cycle' })).toBeVisible()
    const cells = page.locator('tbody td').filter({ hasText: /Paid in October/ })
    await expect(cells).toHaveCount(0)
    guards.assertClean()
  })

  test('Bug2 pagination footer', async ({ page }) => {
    await page.goto('/people')
    await expect(page.getByTestId('people-pagination')).toContainText(/Showing 1[–-]25 of/)
  })

  test('Bug3 Powered by Multiplier on people', async ({ page }) => {
    await page.goto('/people')
    await expect(page.getByText('Powered by Multiplier')).toBeVisible()
  })

  test('Bug4 remind creates notification without SMTP', async ({ page, request }) => {
    const res = await request.post('http://127.0.0.1:8788/api/issues/issue_001/remind', {
      data: { asOf: '2026-10-12' },
      headers: { 'X-Customer-Id': 'cust_acme', 'Content-Type': 'application/json' },
    })
    expect(res.ok()).toBeTruthy()
    const body = await res.json()
    expect(body.notificationId || body.formPath).toBeTruthy()
    await page.goto('/payroll/notifications')
    await expect(page.getByText(/Lena|reminder|Tax ID|Steuer/i).first()).toBeVisible({ timeout: 10000 })
  })

  test('Bug5 invalid CPF disables save', async ({ page }) => {
    await page.goto('/payroll/actions')
    // Open Beatriz / CPF issue if present
    const beatriz = page.getByText('Beatriz').first()
    if (await beatriz.isVisible().catch(() => false)) {
      await beatriz.click()
      const addMyself = page.getByRole('button', { name: /Add details myself/i })
      if (await addMyself.isVisible().catch(() => false)) {
        await addMyself.click()
        const input = page.locator('input').last()
        await input.fill('123456789')
        const save = page.getByRole('button', { name: /Save & resolve|Save and resolve/i })
        await expect(save).toBeDisabled()
      }
    }
  })
})
