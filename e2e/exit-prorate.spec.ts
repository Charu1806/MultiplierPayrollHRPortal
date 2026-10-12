import { expect, test } from '@playwright/test'

test.use({ channel: 'chrome' })

test('exit after lock-in holds the month and pays prorated days next month', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('clarity.asOf', '2026-11-18'))
  await page.goto('/people/emp_james')
  const retry = page.getByRole('button', { name: 'Retry' })
  if (await retry.isVisible().catch(() => false)) {
    await retry.click()
  }
  await expect(page.getByTestId('record-exit-button')).toBeVisible({ timeout: 20_000 })

  const fullFinal = (await page.getByTestId('salary-summary').innerText()).replace(/\s+/g, ' ')
  await page.getByTestId('record-exit-button').click()
  const dialog = page.getByRole('dialog')
  await expect(dialog).toContainText('on hold')
  await expect(dialog).toContainText('18 days')
  await expect(dialog).toContainText('full monthly salary is not paid')
  await dialog.getByRole('button', { name: 'Remove' }).click()

  const exitCard = page.getByTestId('record-exit')
  await expect(exitCard).toContainText('On hold for November')
  await expect(exitCard).toContainText('Prorated pay for 18 of 30 days')
  await expect(exitCard).toContainText('December')
  await expect(page.getByTestId('exit-pay-note')).toContainText('18 of 30 days')

  const proratedFinal = (await page.getByTestId('salary-summary').innerText()).replace(/\s+/g, ' ')
  expect(proratedFinal).not.toBe(fullFinal)
  expect(proratedFinal.toLowerCase()).toContain('18 days')

  await page.goto('/payroll/review')
  await expect(page.getByText('Exit · prorated 18 days').first()).toBeVisible()
  await expect(page.getByText('On hold for November').first()).toBeVisible()
  await expect(page.getByText('paid in December').first()).toBeVisible()

  await page.goto('/people/emp_james')
  await page.getByTestId('undo-exit').click()
  await page.getByRole('dialog').getByRole('button', { name: 'Undo' }).click()
  await expect(page.getByTestId('record-exit-button')).toBeVisible({ timeout: 20_000 })
})
