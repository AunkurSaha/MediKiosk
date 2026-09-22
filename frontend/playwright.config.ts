import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  globalSetup: './e2e/require-mock.ts',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: process.env.MEDIKIOSK_SUPABASE_DEMO_QA === '1' ? 300000 : 60000,
  expect: { timeout: process.env.MEDIKIOSK_SUPABASE_DEMO_QA === '1' ? 60000 : 5000 },
  use: {
    baseURL: 'http://127.0.0.1:5175',
    headless: true,
    trace: process.env.PLAYWRIGHT_TRACE === '1' ? 'retain-on-failure' : 'off',
  },
  outputDir: '../.runtime/playwright-results',
});
