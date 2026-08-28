import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  forbidOnly: true,
  workers: 1,
  timeout: 240_000,
  expect: { timeout: 12_000 },
  outputDir: '/tmp/simverse-option-b-e2e-artifacts/test-results',
  reporter: [
    ['line'],
    ['json', { outputFile: '/tmp/simverse-option-b-e2e-artifacts/report.json' }],
  ],
  use: {
    baseURL: 'http://localhost:4173',
    headless: process.env.PW_HEADFUL !== '1',
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
})
