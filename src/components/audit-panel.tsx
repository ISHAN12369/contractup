'use client';

import { useState } from 'react';
import { Loader2 } from 'lucide-react';
import { Audit, IndiaContext, SourceSelection } from '@/lib/audit-contracts';
import { LegalNotice } from './legal-notice';

const RULES = ['applicability', 'deposit', 'lock_in', 'notice', 'stamp', 'registration', 'escalation'];
const DEFAULT_INDIA: IndiaContext = { enabled: false, state: '', premises: 'unknown', model_act_applicable: false, monthly_rent: null, deposit: null, enabled_rules: RULES };
interface Props { result: Audit | null; available: boolean; busy: boolean; analyzing: boolean; onAnalyze: (india: IndiaContext) => Promise<void>; onSource: (selection: SourceSelection) => void }

export function AuditPanel({ result, available, busy, analyzing, onAnalyze, onSource }: Props) {
  const [india, setIndia] = useState<IndiaContext>(DEFAULT_INDIA);
  const [filter, setFilter] = useState('all');
  return <section id="audit" className="studio-section dark-theme">
    <p className="text-xs uppercase tracking-widest mb-6">04 / Evidence & review priorities</p>
    <h2 className="heading-display text-4xl md:text-6xl mb-6">Know what needs a closer look.</h2>
    <p className="text-sm max-w-2xl mb-6">Review CUAD clause types with source locations, a published priority rubric, and draft negotiation language. An extracted quotation supports its location; it does not establish a legal conclusion.</p>
    <details className="border border-white/20 p-4 mb-6">
      <summary className="cursor-pointer">India rent / lease checklist (optional)</summary>
      <label className="flex gap-2 mt-4 text-sm"><input type="checkbox" checked={india.enabled} disabled={busy} onChange={e => setIndia({ ...india, enabled: e.target.checked })} />Include the informational India checklist</label>
      {india.enabled && <div className="grid md:grid-cols-2 gap-4 mt-4 text-sm">
        <label>State / Union Territory<input aria-label="State or Union Territory" value={india.state} maxLength={80} className="audit-input" onChange={e => setIndia({ ...india, state: e.target.value })} /></label>
        <label>Premises<select aria-label="Premises type" className="audit-input" value={india.premises} onChange={e => setIndia({ ...india, premises: e.target.value as IndiaContext['premises'] })}><option value="unknown">Not specified</option><option value="residential">Residential</option><option value="commercial">Commercial</option></select></label>
        <label>Monthly rent (INR)<input className="audit-input" type="number" min="1" max="1000000000" value={india.monthly_rent ?? ''} onChange={e => setIndia({ ...india, monthly_rent: e.target.value ? Number(e.target.value) : null })} /></label>
        <label>Deposit (INR)<input className="audit-input" type="number" min="0" max="10000000000" value={india.deposit ?? ''} onChange={e => setIndia({ ...india, deposit: e.target.value ? Number(e.target.value) : null })} /></label>
        <label className="md:col-span-2 flex gap-2"><input type="checkbox" checked={india.model_act_applicable} onChange={e => setIndia({ ...india, model_act_applicable: e.target.checked })} />Compare my figures against the Model Tenancy Act benchmark as an assumption. This does not establish which state law applies.</label>
        <div className="md:col-span-2 flex flex-wrap gap-3">{RULES.map(rule => <label key={rule} className="flex gap-1"><input type="checkbox" checked={india.enabled_rules.includes(rule)} onChange={e => setIndia({ ...india, enabled_rules: e.target.checked ? [...india.enabled_rules, rule] : india.enabled_rules.filter(item => item !== rule) })} />{rule.replace('_', ' ')}</label>)}</div>
      </div>}
    </details>
    <button className="studio-btn self-start" disabled={!available || busy} onClick={() => void onAnalyze(india)}>{analyzing && <Loader2 className="w-4 h-4 animate-spin" />} {analyzing ? 'Reviewing every chunk…' : 'Run clause audit'}</button>
    {result && <div className="mt-8 space-y-6">
      <div className="border border-coral p-5">
        <p className="uppercase text-xs tracking-widest">Overall review priority · {result.contract_type}</p>
        <p className="text-3xl my-3">{result.overall_risk ? `${result.overall_risk.level.toUpperCase()} · ${result.overall_risk.score}/100` : 'Not scored — no verified passages'}</p>
        <p className="text-sm">{result.summary}</p>
        {result.overall_risk && <p className="text-xs opacity-70 mt-3">{result.overall_risk.why}</p>}
        <p className="text-xs mt-3">Coverage: {result.analyzed_chunks}/{result.total_chunks} chunks processed · {result.dropped_claims} unsupported claims dropped. Coverage is not recall.</p>
        <details className="mt-4 text-xs"><summary className="cursor-pointer">How the score works</summary><p className="mt-2">High 80: uncapped liability, non-compete, perpetual licence, covenant not to sue, or restrictive wording. Medium 50: material control/continuing-obligation types. Low 20: remaining extracted types. Overall = maximum clause score. Missing clauses never count as safe. Rule: review-priority-v1.</p></details>
      </div>
      <div className="flex gap-2 flex-wrap" aria-label="Filter review priority">{['all', 'high', 'medium', 'low'].map(value => <button key={value} aria-pressed={filter === value} className={`border px-3 py-2 text-xs ${filter === value ? 'border-coral text-coral' : 'border-white/30'}`} onClick={() => setFilter(value)}>{value.toUpperCase()}</button>)}</div>
      {result.clauses.filter(clause => filter === 'all' || clause.risk.level === filter).map(clause => <article key={clause.id} className="border border-white/20 p-5 space-y-3">
        <div className="flex flex-wrap justify-between gap-2"><h3 className="font-bold">{clause.type}</h3><span className="text-xs uppercase text-coral">{clause.risk.level} · {clause.risk.score}</span></div>
        <p className="text-xs opacity-70">Party: {clause.party} · Model confidence: {clause.confidence.toFixed(2)} (uncalibrated)</p>
        <blockquote className="border-l-2 border-coral pl-3 text-sm whitespace-pre-wrap">{clause.quoted_text}</blockquote>
        <button className="text-xs underline" onClick={() => onSource({ docId: result.doc_id, location: clause.location, quote: clause.quoted_text })}>View source · {clause.location.page ? `page ${clause.location.page} · ` : ''}{clause.location.section_id}</button>
        <p className="text-sm">{clause.risk.why}</p>
        {clause.redline && <details className="bg-white/5 p-3 text-sm"><summary className="cursor-pointer">Negotiation draft — review before use</summary><p className="text-xs uppercase mt-3">Original</p><p className="mt-1 whitespace-pre-wrap">{clause.redline.original}</p><p className="text-xs uppercase mt-3">Suggested replacement</p><p className="mt-1 whitespace-pre-wrap">{clause.redline.suggested}</p><p className="text-xs opacity-80 mt-3">{clause.redline.rationale}</p><LegalNotice /></details>}
      </article>)}
      {result.clauses.length === 0 && <p>No source-located CUAD clauses were returned. This does not establish absence or low risk.</p>}
      {result.rule_checks.length > 0 && <div className="space-y-4"><h3 className="text-2xl">India checklist</h3>{result.rule_checks.map(check => <article key={check.id} className="border border-white/20 p-4 text-sm"><h4 className="font-bold">{check.title} · {check.status.replaceAll('_', ' ')}</h4><p className="my-3">{check.detail}</p><a className="underline text-coral" href={check.source_url} target="_blank" rel="noreferrer">{check.source_title} · {check.section}</a>{check.evidence.map((location, index) => <button key={index} className="block underline text-xs mt-2" onClick={() => onSource({ docId: result.doc_id, location, quote: '' })}>Inspect checklist evidence {index + 1}</button>)}<LegalNotice /></article>)}</div>}
      <details className="text-xs opacity-80"><summary className="cursor-pointer">Coverage and limitations</summary><ul className="list-disc pl-5 mt-3 space-y-2">{result.warnings.map(warning => <li key={warning}>{warning}</li>)}</ul><p className="mt-3">Workflow: {result.steps.join(' → ')}</p></details>
    </div>}
    <LegalNotice />
  </section>;
}
