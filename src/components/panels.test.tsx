import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { BenefitsPanel } from './benefits-panel';
import { ChatPanel } from './chat-panel';
import { UploadPanel } from './upload-panel';

it('renders every party and finding, including later clauses, with click-to-quote', () => {
  const items = Array.from({ length: 14 }, (_, i) => ({
    party: `Party ${i % 3}`, benefit: `Finding ${i}`, kind: 'benefit' as const,
    clause: `Clause ${i}`, score: 7, chunk_ids: [`c${i}`],
  }));
  render(<BenefitsPanel result={{ items, analyzed_chunks: 20, total_chunks: 20, disclaimer: 'test' }} available busy={false} analyzing={false} onAnalyze={vi.fn()} />);
  expect(screen.getByText('Party 2')).toBeInTheDocument();
  fireEvent.click(screen.getByText('Finding 13'));
  expect(screen.getByLabelText('Source quotation')).toHaveTextContent('Clause 13');
  expect(screen.getByText(/Informational only, not legal advice/)).toBeInTheDocument();
  expect(screen.getByRole('status')).toHaveTextContent('20 / 20');
});

it('preserves source quotations and pages in chat', () => {
  render(<ChatPanel messages={[{ role: 'assistant', content: 'Answer [Excerpt 1]', sources: [{
    excerpt: 1, chunk_id: 'c0', preview: 'Original clause text', page: 3, distance: 0.1,
    section_id: '1.', start: 0, end: 20, page_start: 0, page_end: 20, ocr: false,
  }] }]} available busy={false} sending={false} onSend={vi.fn()} />);
  expect(screen.getByText('Excerpt 1 · Page 3 · c0')).toBeInTheDocument();
  expect(screen.getByText('Original clause text')).toBeInTheDocument();
});

it('keeps pasted text on a failed upload and clears it only on success', async () => {
  const upload = vi.fn().mockResolvedValueOnce(false).mockResolvedValueOnce(true);
  render(<UploadPanel document={null} busy={false} onUpload={upload} />);
  const textarea = screen.getByLabelText('Or paste contract text');
  fireEvent.change(textarea, { target: { value: 'Private pasted contract' } });
  fireEvent.click(screen.getByRole('button', { name: 'Load text' }));
  await waitFor(() => expect(upload).toHaveBeenCalledTimes(1));
  expect(textarea).toHaveValue('Private pasted contract');
  fireEvent.click(screen.getByRole('button', { name: 'Load text' }));
  await waitFor(() => expect(textarea).toHaveValue(''));
});
