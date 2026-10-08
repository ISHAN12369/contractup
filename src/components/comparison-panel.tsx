'use client';

import { useState } from 'react';
import { Comparison, SourceSelection } from '@/lib/audit-contracts';
import { StoredDocument } from '@/lib/contracts';
import { LegalNotice } from './legal-notice';

interface Props { documents: StoredDocument[]; result: Comparison | null; busy: boolean; comparing: boolean; onCompare: (before: string, after: string) => Promise<void>; onSource: (selection: SourceSelection) => void }
export function ComparisonPanel({ documents, result, busy, comparing, onCompare, onSource }: Props) {
  const [before, setBefore] = useState('');
  const [after, setAfter] = useState('');
  const beforeValid = documents.some(document => document.doc_id === before);
  const afterValid = documents.some(document => document.doc_id === after);
  return <section id="compare" className="studio-section cream-theme">
    <p className="text-xs uppercase tracking-widest mb-6">05 / Compare versions</p>
    <h2 className="heading-display text-4xl md:text-6xl mb-6">See what changed.</h2>
    <p className="text-sm mb-6">Upload both versions, then choose their order. Comparison audits both documents and aligns extracted clauses by exact text and local semantic similarity. This can take longer than a single audit.</p>
    <div className="grid md:grid-cols-2 gap-4 mb-4">{(['before', 'after'] as const).map(side => <label key={side} className="text-sm">{side === 'before' ? 'Earlier version' : 'Later version'}<select aria-label={`${side} version`} className="block w-full border border-black/30 bg-transparent p-3 mt-2" value={side === 'before' ? before : after} disabled={busy} onChange={e => side === 'before' ? setBefore(e.target.value) : setAfter(e.target.value)}><option value="">Select an uploaded document</option>{documents.map(document => <option key={document.doc_id} value={document.doc_id}>{document.filename} · {new Date(document.created_at * 1000).toLocaleTimeString()}</option>)}</select></label>)}</div>
    <button className="studio-btn self-start" disabled={busy || !beforeValid || !afterValid || before === after} onClick={() => void onCompare(before, after)}>{comparing ? 'Comparing both versions…' : 'Compare versions'}</button>
    {result && <div className="space-y-5 mt-8">
      <p>{result.unchanged} unchanged extracted passages · overall priority delta: {result.overall_risk_delta === null ? 'not comparable' : `${result.overall_risk_delta > 0 ? '+' : ''}${result.overall_risk_delta}`}</p>
      {result.changes.map((change, index) => <article key={index} className="border border-black/20 p-5"><h3 className="font-bold uppercase text-sm">{change.kind} · {change.after?.type || change.before?.type} · priority delta {change.risk_delta > 0 ? '+' : ''}{change.risk_delta}</h3><div className="grid md:grid-cols-2 gap-5 mt-4">{(['before', 'after'] as const).map(side => {
        const clause = change[side];
        return <div key={side}><p className="uppercase text-xs mb-2">{side}</p>{clause ? <><blockquote className="text-sm whitespace-pre-wrap border-l-2 border-coral pl-3">{clause.quoted_text}</blockquote><button className="text-xs underline mt-3" onClick={() => onSource({ docId: side === 'before' ? result.before_id : result.after_id, location: clause.location, quote: clause.quoted_text })}>Open {side} source</button></> : <p className="text-sm opacity-60">No matched passage</p>}</div>;
      })}</div><p className="text-xs opacity-70 mt-4">{change.explanation}</p></article>)}
      {result.warnings.map(warning => <p key={warning} className="text-xs opacity-70">{warning}</p>)}
    </div>}
    <LegalNotice />
  </section>;
}
