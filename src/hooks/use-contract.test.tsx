import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import { api, ApiError } from '@/lib/api';
import { loadHistory, saveHistory } from '@/lib/history';
import { doc } from '@/test/fixtures';
import { useContract } from './use-contract';

vi.mock('@/lib/api', async importOriginal => {
  const actual = await importOriginal<typeof import('@/lib/api')>();
  return { ...actual, api: { upload: vi.fn(), document: vi.fn(), remove: vi.fn(), benefits: vi.fn(), chat: vi.fn(), audit: vi.fn(), compare: vi.fn() } };
});
beforeEach(() => { vi.mocked(api.upload).mockResolvedValue(doc); });

it('restores using doc_id without uploading stored text', async () => {
  saveHistory([doc]);
  vi.mocked(api.document).mockResolvedValue(doc);
  const { result } = renderHook(() => useContract());
  await act(() => result.current.restore(doc));
  expect(api.document).toHaveBeenCalledWith(doc.doc_id);
  expect(api.upload).not.toHaveBeenCalled();
  expect(result.current.document).toEqual(doc);
});

it('removes expired history and prompts for upload', async () => {
  saveHistory([doc]);
  vi.mocked(api.document).mockRejectedValue(new ApiError('Document expired.', 404));
  const { result } = renderHook(() => useContract());
  await act(() => result.current.restore(doc));
  expect(result.current.document).toBeNull();
  expect(loadHistory()).toEqual([]);
  expect(result.current.error).toContain('expired');
});

it('retains history when server deletion fails', async () => {
  saveHistory([doc]);
  vi.mocked(api.remove).mockRejectedValue(new ApiError('Deletion pending.', 503));
  const { result } = renderHook(() => useContract());
  await act(() => result.current.remove(doc.doc_id));
  expect(loadHistory()).toEqual([doc]);
  expect(result.current.error).toContain('pending');
});

it('does not restore stale chat after reset', async () => {
  const { result } = renderHook(() => useContract());
  await act(() => result.current.upload(new File(['contract'], 'lease.txt')));
  let complete!: (value: Awaited<ReturnType<typeof api.chat>>) => void;
  vi.mocked(api.chat).mockImplementation(() => new Promise(resolve => { complete = resolve; }));
  let pending!: Promise<boolean>;
  act(() => { pending = result.current.chat('Who pays?'); });
  act(() => result.current.reset());
  await act(async () => { complete({ answer: 'Old contract', sources: [], disclaimer: 'test', strategy: 'dense' }); await pending; });
  expect(result.current.document).toBeNull();
  expect(result.current.messages).toEqual([]);
  await waitFor(() => expect(result.current.busy).toBeNull());
});

it('does not clear the active document when restoring a different expired ID', async () => {
  const { result } = renderHook(() => useContract());
  await act(() => result.current.upload(new File(['contract'], 'lease.txt')));
  vi.mocked(api.document).mockRejectedValue(new ApiError('Document expired.', 404));
  await act(() => result.current.restore({ ...doc, doc_id: 'cc47b7e8-f9d5-4e25-9c19-8315b8c56a84' }));
  expect(result.current.document?.doc_id).toEqual(doc.doc_id);
});

it('clears an existing audit when the active document expires on the server', async () => {
  const { result } = renderHook(() => useContract());
  await act(() => result.current.upload(new File(['contract'], 'lease.txt')));
  vi.mocked(api.audit).mockResolvedValue({
    doc_id: doc.doc_id, contract_type: 'other', checklist: [], clauses: [], overall_risk: null,
    summary: 'No clauses found', dropped_claims: 0, analyzed_chunks: 1, total_chunks: 1,
    rule_checks: [], warnings: [], steps: [], disclaimer: 'Informational',
  });
  await act(() => result.current.runAudit({ enabled: false, state: '', premises: 'unknown', model_act_applicable: false, monthly_rent: null, deposit: null, enabled_rules: [] }));
  expect(result.current.audit).not.toBeNull();
  vi.mocked(api.benefits).mockRejectedValue(new ApiError('Document expired.', 404));
  await act(() => result.current.analyze());
  expect(result.current.document).toBeNull();
  expect(result.current.audit).toBeNull();
  expect(result.current.comparison).toBeNull();
});
