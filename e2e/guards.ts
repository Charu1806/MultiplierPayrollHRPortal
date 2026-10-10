import type { Page } from '@playwright/test'

/** Attach global e2e guards. Unexpected errors fail the test. */
export async function attachGuards(page: Page, opts?: { allowStatus?: number[] }) {
  const allow = new Set(opts?.allowStatus || [])
  const consoleErrors: string[] = []
  const networkErrors: string[] = []

  page.on('console', (msg) => {
    if (msg.type() === 'error') {
      const t = msg.text()
      if (/Download the React DevTools|favicon/i.test(t)) return
      consoleErrors.push(t)
    }
  })
  page.on('pageerror', (err) => {
    consoleErrors.push(String(err))
  })
  page.on('response', (res) => {
    const status = res.status()
    if (status >= 400 && !allow.has(status)) {
      const url = res.url()
      if (/\/api\//.test(url)) {
        networkErrors.push(`${status} ${url}`)
      }
    }
  })

  return {
    assertClean() {
      if (consoleErrors.length) {
        throw new Error(`Console errors:\n${consoleErrors.join('\n')}`)
      }
      if (networkErrors.length) {
        throw new Error(`Unexpected HTTP errors:\n${networkErrors.join('\n')}`)
      }
    },
  }
}

export async function assertNoHorizontalOverflow(page: Page) {
  const overflow = await page.evaluate(() => {
    const doc = document.documentElement
    return doc.scrollWidth > doc.clientWidth + 2
  })
  if (overflow) throw new Error('Horizontal scrollbar detected on page')
}
