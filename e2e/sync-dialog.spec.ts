import { test, expect } from '@playwright/test'

test('View in Overview closes the sync dialog and opens Overview', async ({ page }) => {
  await page.goto('/payroll/actions')
  const sync = page.getByRole('button', { name: /Sync from connector/ })
  await expect(sync).toBeEnabled({ timeout: 20000 })
  await sync.click()
  const dialog = page.getByRole('dialog')
  await expect(dialog).toBeVisible({ timeout: 20000 })
  await expect(dialog).toContainText(/\+\d+ added, \d+ changed, \d+ exited/)
  await dialog.getByRole('button', { name: 'View in Overview' }).click()
  await expect(dialog).toBeHidden()
  await expect(page).toHaveURL(/\/payroll\/overview$/)
  await expect(page.getByText('Funding', { exact: true })).toBeVisible()

  await page.getByRole('button', { name: /Sync from connector/ }).click()
  const again = page.getByRole('dialog')
  await expect(again).toContainText('Sync complete', { timeout: 20000 })
  await again.getByRole('button', { name: 'View in Overview' }).click()
  await expect(again).toBeHidden()
  await expect(page).toHaveURL(/\/payroll\/overview$/)
})
