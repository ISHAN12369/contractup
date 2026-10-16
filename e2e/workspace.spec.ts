import { test, expect, Page } from '@playwright/test';
import { mkdirSync, readFileSync } from 'node:fs';

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

test('workspace citations, PDF export, risk map and revocable public audit', async ({ page, browser }) => {
  await page.goto('/'); await signIn(page, 'alice');
  for (const filename of ['phase4-one.txt', 'phase4-two.txt']) {
    await page.getByLabel('Upload contract', { exact: true }).setInputFiles({ name: filename, mimeType: 'text/plain', buffer: Buffer.from('1. Liability\nLiability is unlimited.\n2. Rent\nThe tenant pays monthly rent of INR 24000.') });
    await expect(page.locator('#upload').getByText(filename, { exact: true })).toBeVisible();
    await expect(page.locator('#workspace').getByRole('checkbox', { name: new RegExp(filename) })).toBeVisible();
  }
  await page.locator('#workspace').getByLabel(/phase4-one.txt/).check();
  await page.locator('#workspace').getByLabel(/phase4-two.txt/).check();
  await page.getByLabel('Question across selected documents').fill('Compare the obligations.');
  await page.getByRole('button', { name: 'Ask across documents' }).click();
  await expect(page.getByLabel('Workspace answer')).toContainText('Document 2');
  await page.getByLabel('Workspace answer').locator('summary').first().click();
  await page.getByRole('button', { name: 'View workspace source 1' }).click();
  await expect(page.getByRole('dialog')).toContainText('Liability');
  await page.keyboard.press('Escape');
  await page.locator('#audit').getByRole('button', { name: /Run.*audit/i }).click();
  await expect(page.getByLabel('Contract risk heatmap')).toContainText('Uncapped Liability');
  const downloadEvent = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Export PDF report' }).click();
  const download = await downloadEvent;
  expect(readFileSync((await download.path())!).subarray(0, 5).toString()).toBe('%PDF-');
  await page.getByRole('button', { name: 'Create read-only link' }).click();
  const share = await page.getByLabel('Copy this link').inputValue();
  const guest = await browser.newContext();
  try {
    const publicPage = await guest.newPage();
    await publicPage.goto(share);
    await expect(publicPage.getByRole('heading', { name: 'phase4-two.txt', exact: true })).toBeVisible();
    await expect(publicPage.getByLabel('Contract risk heatmap')).toBeVisible();
    expect(new URL(publicPage.url()).hash).toBe('');
    expect(await publicPage.getByRole('button', { name: 'Export PDF report' }).count()).toBe(0);
    if (process.env.CAPTURE_DOCS === '1') {
      mkdirSync('docs/images', { recursive: true });
      await page.locator('#workspace').screenshot({ path: 'docs/images/workspace.png' });
      await page.getByLabel('Contract risk heatmap').screenshot({ path: 'docs/images/risk-map.png' });
      await publicPage.screenshot({ path: 'docs/images/shared-audit.png', fullPage: true });
    }
    await page.getByRole('button', { name: 'Revoke all links' }).click();
    await expect(page.getByRole('status').filter({ hasText: 'revoked' })).toBeVisible();
    // A fragment-only navigation preserves the already viewed copy; a fresh fetch must fail.
    await publicPage.goto('about:blank');
    await publicPage.goto(share);
    await expect(publicPage.getByRole('main').getByRole('alert')).toContainText('unavailable, expired, or revoked');
  } finally { await guest.close(); }
});
