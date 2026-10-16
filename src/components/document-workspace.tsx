'use client';

import { FormEvent, useEffect, useRef, useState } from 'react';
import { api } from '@/lib/api';
import { StoredDocument } from '@/lib/contracts';
import { SourceSelection } from '@/lib/audit-contracts';
import { WorkspaceAnswer } from '@/lib/product-contracts';
import { LegalNotice } from './legal-notice';

export function DocumentWorkspace({ revision, onOpen, onSource }: { revision: string; onOpen: (doc: StoredDocument) => Promise<void>; onSource: (value: SourceSelection) => void }) {
  const [documents, setDocuments] = useState<StoredDocument[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [question, setQuestion] = useState('');
  const [answer, setAnswer] = useState<WorkspaceAnswer | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [refresh, setRefresh] = useState(0);
  const generation = useRef(0);
  useEffect(() => {
    const version = ++generation.current;
    setAnswer(null); setBusy(false);
    api.documents().then(result => {
      if (version !== generation.current) return;
      setDocuments(result); setSelected(ids => ids.filter(id => result.some(doc => doc.doc_id === id))); setError('');
    }).catch(failure => { if (version === generation.current) { setDocuments([]); setSelected([]); setError(failure.message); } });
    return () => { generation.current = version + 1; };
  }, [revision, refresh]);
  async function submit(event: FormEvent) {
    event.preventDefault(); if (busy || selected.length < 2 || !question.trim()) return;
    const version = generation.current;
    setBusy(true); setAnswer(null); setError('');
    try { const result = await api.workspaceChat(selected, question.trim()); if (generation.current === version) setAnswer(result); }
    catch (failure) { if (generation.current === version) setError(failure instanceof Error ? failure.message : 'The question failed.'); }
    finally { if (generation.current === version) setBusy(false); }
  }
  return <section id="workspace" className="studio-section bg-[#ece9e0] text-[#151515]">
    <p className="text-xs uppercase tracking-widest mb-6">Workspace / Across your documents</p>
    <h2 className="heading-display text-4xl md:text-6xl mb-6">See the differences together.</h2>
    <p className="text-sm mb-6">Select two to five ready documents. Each answer samples up to two excerpts per document and identifies its sources. Missing evidence does not mean a clause is absent.</p>
    <button className="underline text-sm mb-4 self-start" disabled={busy} onClick={() => setRefresh(n => n + 1)}>Refresh documents</button>
    {!documents.length && <p className="text-sm mb-6">Upload documents to build your workspace. Only ready, unexpired documents appear here.</p>}
    <div className="grid md:grid-cols-2 gap-3 mb-6">{documents.map((doc, index) => <div key={doc.doc_id} className="border border-black/20 p-4">
      <label className="flex items-start gap-3"><input type="checkbox" checked={selected.includes(doc.doc_id)} disabled={busy || (!selected.includes(doc.doc_id) && selected.length >= 5)} onChange={e => {
        setSelected(ids => e.target.checked ? [...ids, doc.doc_id] : ids.filter(id => id !== doc.doc_id)); setAnswer(null);
      }} /><span className="break-all">{doc.filename}<span className="block text-xs opacity-70">{doc.num_chunks} chunks · Expires {new Date(doc.expires_at * 1000).toLocaleString()}</span></span></label>
      <button className="underline text-xs mt-3" disabled={busy} onClick={() => void onOpen(doc)}>Open document {index + 1}</button>
    </div>)}</div>
    <form onSubmit={submit} className="space-y-3"><label className="block text-sm">Question across selected documents<textarea className="block w-full border border-black/30 bg-white p-3 mt-2" maxLength={2000} value={question} onChange={e => setQuestion(e.target.value)} disabled={busy} /></label>
      <button className="studio-btn" disabled={busy || selected.length < 2 || !question.trim()}>{busy ? 'Checking selected documents…' : 'Ask across documents'}</button><span className="ml-3 text-xs">{selected.length}/5 selected</span></form>
    {error && <p role="alert" className="mt-4">{error}</p>}
    {answer && <div aria-label="Workspace answer" className="mt-6 border-t border-black/20 pt-6 space-y-4"><p className="whitespace-pre-wrap">{answer.answer}</p>{answer.sources.map(source => <details key={source.excerpt} className="border border-black/20 p-3"><summary>Excerpt {source.excerpt} · {source.filename}</summary><blockquote className="text-sm my-3 whitespace-pre-wrap">{source.preview}</blockquote><button className="underline text-xs" onClick={() => onSource({ docId: source.doc_id, location: source, quote: source.preview })}>View workspace source {source.excerpt}</button></details>)}<p className="text-xs">{answer.disclaimer}</p></div>}
    <LegalNotice />
  </section>;
}
