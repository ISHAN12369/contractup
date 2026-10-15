import { test, expect, Page } from '@playwright/test';
import { readFileSync } from 'node:fs';

async function signIn(page: Page, name: string) {
  const sessions = JSON.parse(readFileSync('test-results/e2e-auth.json', 'utf8'));
  await page.route('https://test.supabase.co/auth/v1/**', async route => {
    const email = route.request().postDataJSON()?.email || '';
    await route.fulfill({ status: 200, contentType: 'application/json',
      body: JSON.stringify(route.request().url().includes('/token') ? sessions[email.startsWith('bob') ? 'bob' : 'alice'] : {}) });
  });
  await page.getByLabel('Email', { exact: true }).fill(`${name}@example.test`);
  await page.getByLabel('Password', { exact: true }).fill('test-password-only');
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Sign out' })).toBeVisible();
}

test('authenticated upload, queued ingestion, grounded chat, source, and account isolation', async ({ page, request }) => {
  await page.goto('/');
  await signIn(page, 'alice');
  const upload = page.waitForResponse(response => response.url().endsWith('/upload') && response.status() === 202);
  await page.getByLabel('Upload contract', { exact: true }).setInputFiles({ name: 'lease.txt', mimeType: 'text/plain',
    buffer: Buffer.from('1. Rent\nThe tenant pays monthly rent of INR 24000 on the fifth day of each month.\n2. Exit\nEither party gives 45 days of written notice.') });
  const ticket = await (await upload).json();
  await expect(page.locator('#upload').getByText('lease.txt', { exact: true })).toBeVisible();
  await page.getByRole('textbox', { name: 'Question about contract' }).fill('What is the monthly rent?');
  await page.getByRole('button', { name: 'Send question' }).click();
  await expect(page.getByRole('log', { name: 'Contract chat' })).toContainText('Monthly rent is INR 24000. [Excerpt 1]');
  await page.locator('summary').filter({ hasText: 'Excerpt 1' }).first().click();
  await page.getByRole('button', { name: 'Highlight on source' }).first().click();
  await expect(page.getByRole('dialog')).toContainText('24000');
  await page.keyboard.press('Escape');
  await page.getByRole('button', { name: 'Sign out' }).click();
  await signIn(page, 'bob');
  await expect(page.locator('#upload')).not.toContainText('lease.txt');
  await expect(page.getByRole('log', { name: 'Contract chat' })).not.toContainText('24000');
  const sessions = JSON.parse(readFileSync('test-results/e2e-auth.json', 'utf8'));
  const foreign = await request.get(`http://127.0.0.1:8013/document/${ticket.doc_id}`, {
    headers: { Authorization: `Bearer ${sessions.bob.access_token}` },
  });
  expect(foreign.status()).toBe(404);
  const storage = await page.evaluate(() => Object.values(localStorage).join(' '));
  expect(storage).not.toContain(sessions.alice.access_token);
  expect(storage).not.toContain('tenant pays');
});

test('malformed PDF surfaces a durable ingestion failure', async ({ page }) => {
  await page.goto('/'); await signIn(page, 'alice');
  await page.getByLabel('Upload contract', { exact: true }).setInputFiles({ name: 'invalid.pdf', mimeType: 'application/pdf', buffer: Buffer.from('not a PDF') });
  await expect(page.getByRole('alert').filter({ hasText: /failed|could not/i })).toBeVisible();
});
