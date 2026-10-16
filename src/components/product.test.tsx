import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { api } from '@/lib/api';
import { SavedAudit } from '@/lib/product-contracts';
import { doc } from '@/test/fixtures';
import { DocumentWorkspace } from './document-workspace';
import { ReportActions } from './report-actions';
import { RiskHeatmap } from './risk-heatmap';
import SharedAuditPage from '@/app/share/page';

const report: SavedAudit = { filename: doc.filename, generated_at: Date.now() / 1000, expires_at: Date.now() / 1000 + 60,
  audit: { doc_id: doc.doc_id, contract_type: 'lease', checklist: [], clauses: [], overall_risk: null, summary: 'A saved review.', dropped_claims: 0, analyzed_chunks: 1, total_chunks: 1, rule_checks: [], warnings: [], steps: [], disclaimer: 'Informational only, not legal advice.' } };
afterEach(() => { vi.useRealTimers(); window.history.replaceState(null, '', '/'); });

it('maps an empty audit as unassessed rather than safe', () => {
  render(<RiskHeatmap audit={report.audit} />);
  expect(screen.getByText(/does not establish low risk/)).toBeVisible();
  expect(screen.getByLabelText('Contract risk heatmap')).toHaveTextContent('0 extracted clauses');
});

it('requires two selected documents and clears answers when selection changes', async () => {
  const second = { ...doc, doc_id: 'cc47b7e8-f9d5-4e25-9c19-8315b8c56a84', filename: 'second.txt' };
  vi.spyOn(api, 'documents').mockResolvedValue([doc, second]);
  const ask = vi.spyOn(api, 'workspaceChat').mockResolvedValue({ answer: 'Different rent.', sources: [], disclaimer: 'Informational' });
  render(<DocumentWorkspace revision="" onOpen={vi.fn()} onSource={vi.fn()} />);
  await screen.findByText('second.txt');
  fireEvent.change(screen.getByLabelText('Question across selected documents'), { target: { value: 'Compare rent' } });
  const checks = screen.getAllByRole('checkbox');
  fireEvent.click(checks[0]);
  expect(screen.getByRole('button', { name: 'Ask across documents' })).toBeDisabled();
  fireEvent.click(checks[1]); fireEvent.click(screen.getByRole('button', { name: 'Ask across documents' }));
  await screen.findByText('Different rent.');
  expect(ask).toHaveBeenCalledWith([doc.doc_id, second.doc_id], 'Compare rent');
  fireEvent.click(checks[0]);
  expect(screen.queryByText('Different rent.')).not.toBeInTheDocument();
});

it('does not display a workspace answer after unmount', async () => {
  vi.spyOn(api, 'documents').mockResolvedValue([doc, { ...doc, doc_id: 'cc47b7e8-f9d5-4e25-9c19-8315b8c56a84' }]);
  let resolve!: (value: { answer: string; sources: []; disclaimer: string }) => void;
  vi.spyOn(api, 'workspaceChat').mockImplementation(() => new Promise(done => { resolve = done; }));
  const view = render(<DocumentWorkspace revision="" onOpen={vi.fn()} onSource={vi.fn()} />);
  await waitFor(() => expect(screen.getAllByRole('checkbox')).toHaveLength(2));
  screen.getAllByRole('checkbox').forEach(box => fireEvent.click(box));
  fireEvent.change(screen.getByLabelText('Question across selected documents'), { target: { value: 'Compare' } });
  fireEvent.click(screen.getByRole('button', { name: 'Ask across documents' }));
  view.unmount();
  await act(async () => resolve({ answer: 'Old account answer', sources: [], disclaimer: 'Informational' }));
  expect(screen.queryByText('Old account answer')).not.toBeInTheDocument();
});

it('creates a fragment link and revokes it without persistence', async () => {
  const token = 'a'.repeat(43);
  vi.spyOn(api, 'createShare').mockResolvedValue({ token, expires_at: report.expires_at });
  vi.spyOn(api, 'revokeShares').mockResolvedValue({ revoked: true });
  render(<ReportActions docId={doc.doc_id} sharing />);
  fireEvent.click(screen.getByRole('button', { name: 'Create read-only link' }));
  expect(await screen.findByLabelText('Copy this link')).toHaveValue(`${window.location.origin}/share#${token}`);
  expect(Object.values(localStorage).join('')).not.toContain(token);
  fireEvent.click(screen.getByRole('button', { name: 'Revoke all links' }));
  await waitFor(() => expect(screen.queryByLabelText('Copy this link')).not.toBeInTheDocument());
});

it('keeps local-mode sharing disabled', () => {
  render(<ReportActions docId={doc.doc_id} sharing={false} />);
  expect(screen.queryByRole('button', { name: 'Create read-only link' })).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Export PDF report' })).toBeEnabled();
});

it('clears a shared report at link expiry and removes its fragment', async () => {
  vi.useFakeTimers();
  window.history.replaceState(null, '', '/share#' + 'a'.repeat(43));
  vi.spyOn(api, 'readShare').mockResolvedValue({ ...report, expires_at: Date.now() / 1000 + 2 });
  render(<SharedAuditPage />);
  await act(async () => { await Promise.resolve(); });
  expect(screen.getByText('A saved review.')).toBeInTheDocument();
  expect(window.location.hash).toBe('');
  await act(async () => { await vi.advanceTimersByTimeAsync(2100); });
  expect(screen.queryByText('A saved review.')).not.toBeInTheDocument();
  expect(screen.getByRole('alert')).toHaveTextContent('expired');
});
