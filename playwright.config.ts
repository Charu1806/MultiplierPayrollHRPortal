import os from 'node:os'
import path from 'node:path'
import { defineConfig, devices } from '@playwright/test'

/**
 * E2E runs against an isolated stack so the demo DB is never touched:
 *   - Clarity API on :8788 with a freshly seeded SQLite copy in the OS tmp dir
 *   - Vite on :5174 pointed at that API
 */
const API_PORT = 8788
const WEB_PORT = 5174
const E2E_DB = path.join(os.tmpdir(), 'payroll_clarity_e2e.db')

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 60_000,
  expect: { timeout: 8_000 },
  reporter: [['list']],
  use: {
    baseURL: `http://localhost:${WEB_PORT}`,
    viewport: { width: 1440, height: 900 },
    trace: 'retain-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: [
    {
      command: `python3 data/seed_db.py --db "${E2E_DB}" --seed 42 && python3 -m server.app`,
      url: `http://127.0.0.1:${API_PORT}/health`,
      reuseExistingServer: false,
      timeout: 30_000,
      env: {
        CLARITY_DB_PATH: E2E_DB,
        CLARITY_PORT: String(API_PORT),
        CLARITY_DEBUG: '0',
      },
    },
    {
      command: `npm run dev:web -- --port ${WEB_PORT} --strictPort`,
      url: `http://localhost:${WEB_PORT}`,
      reuseExistingServer: false,
      timeout: 30_000,
      env: {
        VITE_CLARITY_API_BASE: `http://127.0.0.1:${API_PORT}/api`,
      },
    },
  ],
})
