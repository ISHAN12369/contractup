'use client';

import { Audit, Clause } from '@/lib/audit-contracts';

const shades = { high: 'bg-[#f8b4a5] text-[#572519]', medium: 'bg-[#f1d592] text-[#493711]', low: 'bg-[#bedbd0] text-[#183c31]' };

export function RiskHeatmap({ audit, onSelect }: { audit: Audit; onSelect?: (clause: Clause) => void }) {
  return <section aria-label="Contract risk heatmap" className="border border-current/20 p-5 space-y-4">
    <div className="flex flex-wrap justify-between gap-4"><h3 className="text-xl">Review-priority map</h3>
      <p className="text-sm">{audit.clauses.length} extracted clauses · {audit.analyzed_chunks}/{audit.total_chunks} chunks reviewed</p></div>
    <div className="flex flex-wrap gap-3 text-xs">{(['high', 'medium', 'low'] as const).map(level => <span key={level} className={`px-3 py-2 ${shades[level]}`}>{level.toUpperCase()} {audit.clauses.filter(c => c.risk.level === level).length}</span>)}</div>
    <div className="grid grid-cols-2 md:grid-cols-4 gap-2">{audit.clauses.map((clause, index) => {
      const label = `${index + 1}. ${clause.type}: ${clause.risk.level} priority, ${clause.risk.score}/100`;
      const content = <><span className="block font-semibold">{index + 1}. {clause.type}</span><span className="block mt-2 uppercase text-xs">{clause.risk.level} · {clause.risk.score}/100</span><span className="block mt-2 text-xs">{clause.location.page ? `Page ${clause.location.page}` : clause.location.section_id}</span></>;
      return onSelect ? <button key={clause.id} aria-label={label} onClick={() => onSelect(clause)} className={`p-3 text-left text-sm focus-visible:outline focus-visible:outline-2 ${shades[clause.risk.level]}`}>{content}</button> : <div key={clause.id} aria-label={label} className={`p-3 text-sm ${shades[clause.risk.level]}`}>{content}</div>;
    })}</div>
    {!audit.clauses.length && <p>No extracted clauses to map. This does not establish low risk.</p>}
    <p className="text-xs opacity-80">Colors show the review-priority rubric for extracted clauses, not legal conclusions. Unextracted clauses are not scored.</p>
  </section>;
}
