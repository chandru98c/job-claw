import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: 1,
  reporter: 'html',
  use: {
    baseURL: 'http://localhost:3000',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  globalSetup: './e2e/global-setup.ts',
  webServer: [
    {
      command: 'npm run dev',
      url: 'http://localhost:3000',
      reuseExistingServer: false,
      timeout: 120 * 1000,
      env: {
        NEXT_PUBLIC_API_URL: 'http://127.0.0.1:8000'
      }
    },
    {
      command: 'python -m uvicorn app.e2e_main:app --port 8000',
      cwd: '../backend',
      port: 8000,
      reuseExistingServer: !process.env.CI,
      timeout: 120 * 1000,
      env: {
        DATABASE_URL: 'postgresql+asyncpg://postgres:Postpass123@localhost:5432/jobclaw_test',
        REDIS_URL: 'redis://localhost:6379/1',
        E2E_MODE: '1'
      }
    },
    {
      command: 'python -m arq app.e2e_worker.WorkerSettings',
      cwd: '../backend',
      reuseExistingServer: !process.env.CI,
      env: {
        DATABASE_URL: 'postgresql+asyncpg://postgres:Postpass123@localhost:5432/jobclaw_test',
        REDIS_URL: 'redis://localhost:6379/1',
        E2E_MODE: '1'
      }
    }
  ],
});
