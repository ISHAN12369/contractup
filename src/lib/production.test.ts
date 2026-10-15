import { afterEach, expect, it, vi } from 'vitest';
import { api } from './api';
import { authenticatedHeaders, configureAuth } from './auth-session';
import { loadHistory, saveHistory } from './history';
import { doc } from '@/test/fixtures';

afterEach(() => { configureAuth(null); vi.useRealTimers(); localStorage.clear(); });

it('attaches a current bearer token without browser persistence', async () => {
  configureAuth(async () => 'test-session-token');
  expect((await authenticatedHeaders()).get('Authorization')).toBe('Bearer test-session-token');
  const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify(doc)));
  vi.stubGlobal('fetch', fetch);
  await api.document(doc.doc_id);
  expect(fetch.mock.calls[0][1].headers.get('Authorization')).toBe('Bearer test-session-token');
  expect(localStorage.length).toBe(0);
});

it('keeps document history in its account namespace', () => {
  saveHistory([doc], localStorage, 0, 'alice');
  expect(loadHistory(localStorage, 0, 'bob')).toEqual([]);
  expect(loadHistory(localStorage, 0, 'alice')).toEqual([doc]);
});

it('polls queued ingestion and returns metadata only after ready', async () => {
  vi.useFakeTimers();
  const replies = [
    { doc_id: doc.doc_id, status: 'queued' },
    { doc_id: doc.doc_id, status: 'processing' },
    { doc_id: doc.doc_id, status: 'ready', document: doc },
  ];
  const fetch = vi.fn().mockImplementation(async () => new Response(JSON.stringify(replies.shift())));
  vi.stubGlobal('fetch', fetch);
  const status = vi.fn();
  const promise = api.upload(new File(['example'], 'lease.txt'), status);
  await vi.advanceTimersByTimeAsync(3000);
  expect(await promise).toEqual(doc);
  expect(status).toHaveBeenCalledWith('Reading and indexing your document…');
  expect(fetch).toHaveBeenCalledTimes(3);
});

it('rejects failed ingestion and discards a response after sign out', async () => {
  vi.stubGlobal('fetch', vi.fn().mockImplementation(async () => new Response(JSON.stringify({ doc_id: doc.doc_id, status: 'failed', detail: 'Processing failed.' }))));
  await expect(api.upload(new File(['bad'], 'bad.txt'))).rejects.toThrow('Processing failed');
  vi.stubGlobal('fetch', vi.fn().mockImplementation(async () => {
    configureAuth(null);
    return new Response(JSON.stringify(doc));
  }));
  await expect(api.document(doc.doc_id)).rejects.toThrow('session changed');
});
