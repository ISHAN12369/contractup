import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './e2e', testMatch: '*.spec.ts', workers: 1,
  timeout: 120_000, expect: { timeout: 30_000 },
  // Keep the ephemeral auth fixture outside Playwright's cleaned output directory.
  outputDir: 'test-results/browser',
  use: { baseURL: 'http://127.0.0.1:3013', trace: 'retain-on-failure' },
  webServer: [
    { command: process.platform === 'win32' ? '.\\.venv\\Scripts\\python.exe e2e/server.py' : 'python e2e/server.py',
      url: 'http://127.0.0.1:8013/health', timeout: 180_000, reuseExistingServer: !process.env.CI },
    { command: 'npm run dev -- --hostname 127.0.0.1 --port 3013', url: 'http://127.0.0.1:3013',
      timeout: 180_000, reuseExistingServer: !process.env.CI,
      env: { NEXT_PUBLIC_AUTH_REQUIRED: 'true', NEXT_PUBLIC_SUPABASE_URL: 'https://test.supabase.co',
        NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY: 'test-publishable-key', NEXT_PUBLIC_RAG_API_URL: 'http://127.0.0.1:8013',
        NEXT_TELEMETRY_DISABLED: '1' } },
  ],
});
