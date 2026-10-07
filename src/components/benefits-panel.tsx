'use client';

import { useEffect, useRef, useState } from 'react';
import { BarChart3, Loader2 } from 'lucide-react';
import { BenefitsResult, Finding } from '@/lib/contracts';
import { LegalNotice } from './legal-notice';

interface Props { result: BenefitsResult | null; available: boolean; busy: boolean; analyzing: boolean; onAnalyze: () => Promise<void> }

export function BenefitsPanel({ result, available, busy, analyzing, onAnalyze }: Props) {
  const [selected, setSelected] = useState<Finding | null>(null);
  const quote = useRef<HTMLDivElement>(null);
  useEffect(() => { setSelected(null); }, [result]);
  useEffect(() => { if (selected) quote.current?.scrollIntoView({ behavior: 'smooth', block: 'center' }); }, [selected]);
  const parties = Array.from(new Set(result?.items.map(item => item.party) || []));
  return <section id="benefits" className="studio-section dark-theme">
    <p className="text-xs uppercase tracking-widest text-studio-gray mb-6">02 / Benefits & obligations</p>
    <h2 className="heading-display text-4xl md:text-6xl mb-6">Read the balance.</h2>
    <p className="text-sm text-studio-gray max-w-xl mb-6">Analyze every indexed chunk. Scores describe estimated significance, not fairness, enforceability, or legal risk.</p>
    <button disabled={!available || busy} onClick={() => void onAnalyze()} className="studio-btn mb-6">
      {analyzing ? <Loader2 className="w-4 h-4 animate-spin" /> : <BarChart3 className="w-4 h-4" />}
      {analyzing ? 'Analyzing all chunks…' : result ? 'Analyze again' : 'Analyze document'}
    </button>
    {!available && <p className="text-sm text-studio-gray">Upload a document to begin.</p>}
    {result && <>
      <p role="status" className="text-xs mb-6">{result.analyzed_chunks} / {result.total_chunks} chunks processed · {result.items.length} findings. Coverage counts processed chunks; it does not guarantee every clause was identified.</p>
      {result.items.length === 0 && <p>No supported benefits or obligations were identified.</p>}
      <div className="grid md:grid-cols-2 gap-6 w-full">
        {parties.map(party => <div key={party} className="studio-card p-6">
          <h3 className="font-bold text-lg mb-4">{party}</h3>
          <div className="space-y-4">{result.items.filter(item => item.party === party).map((item, index) =>
            <button key={`${item.chunk_ids.join('-')}-${index}`} className="w-full text-left group" onClick={() => setSelected(item)}>
              <span className="flex justify-between gap-4 text-sm"><span>{item.benefit}</span><span>{item.score}/10</span></span>
              <span className="block text-[10px] uppercase text-studio-gray mt-1">{item.kind} · view source quotation</span>
              <span className="block bg-white/10 h-2 mt-2"><span className="block bg-coral h-2 group-hover:bg-white" style={{ width: `${item.score * 10}%` }} /></span>
            </button>)}</div>
        </div>)}
      </div>
      {selected && <div ref={quote} className="studio-card w-full p-6 mt-6 border-l-4 border-coral" aria-label="Source quotation">
        <p className="font-semibold mb-3">{selected.party} — {selected.benefit}</p>
        <blockquote className="whitespace-pre-wrap text-sm leading-relaxed">“{selected.clause}”</blockquote>
        <p className="text-xs text-studio-gray mt-3">Source chunks: {selected.chunk_ids.join(', ')}</p>
      </div>}
    </>}
    <LegalNotice />
  </section>;
}
