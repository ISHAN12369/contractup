import { expect, it, vi } from 'vitest';
import { api } from './api';
import { doc } from '@/test/fixtures';

it('uploads multipart and validates document metadata', async () => {
  const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify(doc)));
  vi.stubGlobal('fetch', fetch);
  expect(await api.upload(new File(['contract'], 'lease.txt'))).toEqual(doc);
  expect(fetch.mock.calls[0][1].body).toBeInstanceOf(FormData);
});

it('rejects free-text benefits, malformed scores and partial coverage', async () => {
  for (const result of [{ answer: '```json []```' }, { items: [], analyzed_chunks: 2, total_chunks: 9, disclaimer: 'test' }]) {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(result))));
    await expect(api.benefits(doc.doc_id)).rejects.toThrow('invalid response');
  }
});

it('includes the request ID in safe backend errors', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: 'Document expired.' }), {
    status: 404, headers: { 'X-Request-ID': 'req-123' },
  })));
  await expect(api.document(doc.doc_id)).rejects.toThrow('Document expired. (Request: req-123)');
});

it('sends only six allowed history messages without source text', async () => {
  const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ answer: 'Answer', sources: [], disclaimer: 'test' })));
  vi.stubGlobal('fetch', fetch);
  await api.chat(doc.doc_id, 'Question', Array.from({ length: 12 }, () => ({ role: 'user' as const, content: 'prior', sources: [] })));
  const body = JSON.parse(fetch.mock.calls[0][1].body);
  expect(body.history).toHaveLength(6);
  expect(body.history[0]).toEqual({ role: 'user', content: 'prior' });
});
