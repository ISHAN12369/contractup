// @vitest-environment node
import { expect, it } from 'vitest';
import { zipSync, strToU8 } from 'fflate';
import { NextRequest } from 'next/server';
import { extractText, MAX_UPLOAD_BYTES, validateFile } from './extract';
import { handleExtract } from './extract-route';
import { contractPdf } from '@/test/pdf-fixture';

it('validates bytes, UTF-8 and size rather than only extension', () => {
  for (const [name, bytes] of [['fake.pdf', Buffer.from('text')], ['fake.docx', Buffer.from('zip')], ['fake.txt', Buffer.from([0, 255])]] as const) {
    expect(() => validateFile(name, bytes)).toThrow();
  }
  expect(() => validateFile('large.txt', Buffer.alloc(MAX_UPLOAD_BYTES + 1, 65))).toThrow('limit');
  expect(validateFile('UPPER.TXT', Buffer.from('valid contract'))).toBe('.txt');
});

it('rejects non-Word ZIP and archive bombs', () => {
  expect(() => validateFile('fake.docx', Buffer.from(zipSync({ 'other.txt': strToU8('text') })))).toThrow('Word');
  const bomb = zipSync({ '[Content_Types].xml': strToU8('<Types/>'), 'word/document.xml': strToU8('x'.repeat(100000)) });
  expect(() => validateFile('bomb.docx', Buffer.from(bomb))).toThrow('limit');
});

it('extracts actual PDF text with the production parser', async () => {
  expect(await extractText('lease.pdf', contractPdf())).toContain('Tenant pays rent.');
}, 30_000);

it('extracts text and DOCX in the fallback route and adds request IDs', async () => {
  expect(await extractText('lease.txt', Buffer.from('  Lease text  '))).toBe('Lease text');
  const word = zipSync({
    '[Content_Types].xml': strToU8('<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>'),
    'word/document.xml': strToU8('<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Tenant pays rent.</w:t></w:r></w:p></w:body></w:document>'),
  });
  expect(await extractText('lease.docx', Buffer.from(word))).toBe('Tenant pays rent.');
  const body = new FormData();
  body.append('file', new File(['Contract text'], 'lease.txt'));
  const response = await handleExtract(new NextRequest('http://localhost:3000/api/extract', { method: 'POST', body }));
  expect(response.status).toBe(200);
  expect(await response.json()).toEqual({ text: 'Contract text', chars: 13 });
  expect(response.headers.get('x-request-id')).toBeTruthy();
}, 30_000); // Cold import of the real DOCX parser can be slow on Windows/OneDrive.

it('rejects a streamed oversized body without trusting Content-Length', async () => {
  const request = new NextRequest('http://localhost:3000/api/extract', { method: 'POST', body: 'x'.repeat(MAX_UPLOAD_BYTES + 65537) });
  expect((await handleExtract(request)).status).toBe(413);
});

it('sanitizes parse errors and disallows cross-origin extraction', async () => {
  const malformed = new NextRequest('http://localhost:3000/api/extract', { method: 'POST', body: 'not multipart' });
  const response = await handleExtract(malformed);
  expect(response.status).toBe(422);
  expect(await response.json()).toMatchObject({ error: 'The document could not be parsed safely.' });
  const crossOrigin = new NextRequest('http://localhost:3000/api/extract', { method: 'POST', headers: { origin: 'https://evil.invalid' } });
  expect((await handleExtract(crossOrigin)).status).toBe(403);
});

it('rate limits repeated extraction attempts in the same instance', async () => {
  let response: Response | undefined;
  for (let index = 0; index < 31; index += 1) {
    response = await handleExtract(new NextRequest('http://localhost:3000/api/extract', { method: 'POST' }));
  }
  expect(response?.status).toBe(429);
  expect(response?.headers.get('retry-after')).toBe('60');
});
