'use client';

import { useEffect, useRef, useState } from 'react';
import { api } from '@/lib/api';
import { SavedAudit } from '@/lib/product-contracts';
import { RiskHeatmap } from '@/components/risk-heatmap';

export default function SharedAuditPage() {
  const [report, setReport] = useState<SavedAudit | null>(null);
  const [error, setError] = useState('');
  const capability = useRef('');
  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    // A fragment avoids putting the secret in HTTP paths, referrers and server logs.
    capability.current ||= window.location.hash.slice(1);
    window.history.replaceState(null, '', window.location.pathname);
    if (!/^[A-Za-z0-9_-]{43}$/.test(capability.current)) { setError('This link is invalid. Open the complete link supplied by its owner.'); return; }
    api.readShare(capability.current).then(value => {
      if (!active) return;
      if (value.expires_at * 1000 <= Date.now()) { setError('This link has expired.'); return; }
      setReport(value);
      timer = setTimeout(() => { setReport(null); setError('This link has expired.'); }, Math.max(0, value.expires_at * 1000 - Date.now()));
    }).catch(() => { if (active) setError('This link is unavailable, expired, or revoked. Ask its owner for a new link.'); });
    return () => { active = false; clearTimeout(timer); };
  }, []);
  return <main className="min-h-screen bg-[#f4f1ea] text-[#151515] p-6 md:p-12"><div className="max-w-4xl mx-auto space-y-6">
    <p className="text-xs uppercase tracking-widest">ContractIQ / Read-only audit</p>
    {!report && !error && <p role="status">Opening shared review…</p>}
    {error && <p role="alert">{error}</p>}
    {report && <><h1 className="text-3xl break-words">{report.filename}</h1><p className="text-xs">Saved {new Date(report.generated_at * 1000).toLocaleString()} · Link expires {new Date(report.expires_at * 1000).toLocaleString()}</p><p className="text-sm">This saved review may contain confidential quotations. Please do not redistribute it. Access revocation cannot erase copies already viewed or saved.</p><p>{report.audit.disclaimer}</p><p>{report.audit.summary}</p><RiskHeatmap audit={report.audit} />
      {report.audit.clauses.map(clause => <article key={clause.id} className="border border-black/20 p-5 space-y-3"><h2 className="text-xl">{clause.type} · {clause.risk.level}</h2><p className="text-xs">{clause.location.page ? `Page ${clause.location.page}` : 'Unpaginated'} · {clause.location.section_id} · Characters {clause.location.start}–{clause.location.end}</p><blockquote className="border-l-2 border-[#a33324] pl-3 whitespace-pre-wrap">{clause.quoted_text}</blockquote><p>{clause.risk.why}</p>{clause.redline && <details><summary>Negotiation draft</summary><p>{clause.redline.suggested}</p><p>{clause.redline.rationale}</p><p className="text-xs">{clause.redline.disclaimer}</p></details>}</article>)}
      {report.audit.rule_checks.map(check => <article key={check.id} className="border border-black/20 p-5"><h2>{check.title} · {check.status}</h2><p>{check.detail}</p><a className="underline" href={check.source_url} rel="noreferrer" target="_blank">{check.source_title} · {check.section}</a></article>)}
      <ul className="list-disc pl-5 text-sm">{report.audit.warnings.map(warning => <li key={warning}>{warning}</li>)}</ul><p className="text-xs">{report.audit.disclaimer}</p></>}
  </div></main>;
}
