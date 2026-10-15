import { afterEach, expect, it, vi } from 'vitest';
import { POST } from '@/app/api/extract/route';
import { NextRequest } from 'next/server';

afterEach(() => vi.unstubAllEnvs());

it('disables standalone extraction when authentication is required', async () => {
  vi.stubEnv('NEXT_PUBLIC_AUTH_REQUIRED', 'true');
  const response = await POST(new NextRequest('http://localhost/api/extract', { method: 'POST' }));
  expect(response.status).toBe(410);
  expect(await response.json()).toEqual({ error: 'Use the authenticated document upload service.' });
});
