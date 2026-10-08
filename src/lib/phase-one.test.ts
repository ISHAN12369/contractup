// @vitest-environment node
import { expect, it } from 'vitest';
import { consumeChatStream } from './sse';
import { findPdfQuote, findQuote, sourceSlice } from './source-highlight';
import { auditSchema } from './audit-contracts';

function stream(text: string, width = 1) {
  const bytes = new TextEncoder().encode(text);
  return new ReadableStream<Uint8Array>({ start(controller) {
    for (let index = 0; index < bytes.length; index += width) controller.enqueue(bytes.slice(index, index + width));
    controller.close();
  } });
}

it('reads fragmented SSE including UTF-8, CRLF and heartbeat, saving only a validated final result', async () => {
  const drafts: string[] = [];
  const wire = ': keepalive\r\n\r\nevent: draft\r\ndata: {"text":"Rupees ₹","verified":false}\r\n\r\nevent: complete\r\ndata: {"answer":"Final ₹","sources":[],"disclaimer":"Informational only"}\r\n\r\n';
  const result = await consumeChatStream(stream(wire), text => drafts.push(text));
  expect(result.answer).toBe('Final ₹');
  expect(drafts).toEqual(['Rupees ₹', '']);
});

it('clears drafts after server errors, invalid completions, or truncated streams', async () => {
  for (const ending of [
    'event: error\ndata: {"detail":"Expired","status":404}\n\n',
    'event: complete\ndata: {"answer":12}\n\n',
    '',
  ]) {
    const drafts: string[] = [];
    await expect(consumeChatStream(stream('event: draft\ndata: {"text":"Unsaved","verified":false}\n\n' + ending), text => drafts.push(text))).rejects.toThrow();
    expect(drafts.at(-1)).toBe('');
  }
});

it('maps source code points and exact quotation occurrences without approximate matches', () => {
  expect(sourceSlice('😀 rent due', 2, 6)).toBe('rent');
  expect(findQuote('😀 Rent\n due', 'rent due')).toEqual([3, 12]);
  expect(findQuote('Rent. Rent.', 'Rent.', 1)).toEqual([6, 11]);
  expect(findQuote('Rent.', 'Repayment')).toBeNull();
  expect(findPdfQuote('Rent.\n Rent.', 'Rent.', 'Rent. Rent.', 1)).toEqual([7, 12]);
  expect(findPdfQuote('Footer Rent. Body Rent.', 'Rent.', 'Body Rent. Footer Rent.', 1)).toBeNull();
  expect(findPdfQuote('Rent.', 'Rent.', 'Rent. Rent.', 1)).toBeNull();
});

it('rejects incomplete audit coverage and unsafe citation URLs', () => {
  const audit = {
    doc_id: 'c0a3b349-948a-4aef-85c7-685bc3ad45b0', contract_type: 'lease', checklist: [], clauses: [], overall_risk: null,
    summary: '', dropped_claims: 0, analyzed_chunks: 1, total_chunks: 2, rule_checks: [], warnings: [], steps: [], disclaimer: '',
  };
  expect(auditSchema.safeParse(audit).success).toBe(false);
  expect(auditSchema.safeParse({ ...audit, total_chunks: 1 }).success).toBe(true);
  expect(auditSchema.safeParse({ ...audit, total_chunks: 1, rule_checks: [{ id: 'x', title: 'x', status: 'review', detail: 'x', source_title: 'x', source_url: 'javascript:alert(1)', section: '1', evidence: [], disclaimer: '' }] }).success).toBe(false);
});
