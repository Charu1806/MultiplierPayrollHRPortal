import { expect, test } from '@playwright/test'

test.use({ channel: 'chrome' })

test('Add employee is on the list and hidden once that page is open', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('clarity.asOf', '2026-11-18'))
  await page.goto('/people')
  const retry = page.getByRole('button', { name: 'Retry' })
  if (await retry.isVisible().catch(() => false)) {
    await retry.click()
  }

  const add = page.getByTestId('add-employee')
  await expect(add).toBeVisible({ timeout: 20_000 })
  await add.click()

  await expect(page).toHaveURL(/\/people\/add$/)
  await expect(page.getByRole('heading', { name: 'Add employee' })).toBeVisible()
  await expect(page.getByTestId('add-employee')).toHaveCount(0)
  await expect(page.getByRole('link', { name: 'All employees' })).toBeVisible()
})
