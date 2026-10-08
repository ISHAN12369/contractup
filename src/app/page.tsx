'use client';

import { useCallback, useState } from 'react';
import { AlertCircle, ArrowRight, History } from 'lucide-react';
import { BenefitsPanel } from '@/components/benefits-panel';
import { ChatPanel } from '@/components/chat-panel';
import { HistoryPanel } from '@/components/history-panel';
import { LegalNotice } from '@/components/legal-notice';
import { UploadPanel } from '@/components/upload-panel';
import { useContract } from '@/hooks/use-contract';
import { AuditPanel } from '@/components/audit-panel';
import { ComparisonPanel } from '@/components/comparison-panel';
import { SourceViewer } from '@/components/source-viewer';
import { SourceSelection } from '@/lib/audit-contracts';

export default function HomePage() {
  const contract = useContract();
  const [historyOpen, setHistoryOpen] = useState(false);
  const [source, setSource] = useState<SourceSelection | null>(null);
  const closeSource = useCallback(() => setSource(null), []);
  const busy = contract.busy !== null;
  return <div className="studio-container relative">
    <aside className="studio-sidebar">
      <a href="#intro" className="studio-logo" onClick={() => { contract.reset(); setSource(null); }} aria-label="ContractIQ home">IQ</a>
      <nav className="studio-nav-links" aria-label="Main navigation">
        {['intro', 'upload', 'benefits', 'chat', 'audit', 'compare'].map(section => <a key={section} href={`#${section}`} className="studio-nav-item">{section}</a>)}
      </nav>
      <button aria-label="Open history" onClick={() => setHistoryOpen(true)}><History className="w-5 h-5 text-coral" /></button>
    </aside>
    <HistoryPanel open={historyOpen} documents={contract.history} busy={busy} onClose={() => setHistoryOpen(false)}
      onRestore={contract.restore} onRemove={contract.remove} onClear={contract.clearHistory} />
    <main className="studio-main">
      <section id="intro" className="studio-section dark-theme justify-between">
        <div className="bg-text-grid"><div>REAL ESTATE</div><div>PROPERTY AGREEMENTS</div><div>CONTRACT CLARITY</div></div>
        <div className="z-10 mt-12">
          {['REAL ESTATE', 'CONTRACTS', 'DEMYSTIFIED', 'BY CONTRACTIQ'].map((line, index) => <div key={line} className="mask-container block">
            <h1 className="kinetic-header mask-text" style={{ animationDelay: `${index * 0.2}s` }}>{line}</h1>
          </div>)}
          <p className="max-w-md text-sm leading-relaxed text-studio-gray mt-6">Explore benefits, obligations, and source quotations in leases and property agreements. Ask questions in plain English.</p>
          <LegalNotice />
        </div>
        <div className="z-10 mt-8"><a href="#upload" className="studio-btn">Get started <ArrowRight className="w-4 h-4" /></a></div>
        <div className="marquee-container w-full mt-12"><div className="marquee-content">CONTRACT CLARITY · BENEFITS & OBLIGATIONS · SOURCE QUOTATIONS · CONTRACT CLARITY · BENEFITS & OBLIGATIONS · SOURCE QUOTATIONS ·</div></div>
      </section>
      <UploadPanel document={contract.document} busy={busy} onUpload={contract.upload} />
      <BenefitsPanel result={contract.benefits} available={!!contract.document} busy={busy} analyzing={contract.busy === 'benefits'} onAnalyze={contract.analyze} />
      <ChatPanel messages={contract.messages} available={!!contract.document} busy={busy} sending={contract.busy === 'chat'} onSend={contract.chat} draft={contract.draft} docId={contract.document?.doc_id} onSource={setSource} />
      <AuditPanel result={contract.audit} available={!!contract.document} busy={busy} analyzing={contract.busy === 'audit'} onAnalyze={contract.runAudit} onSource={setSource} />
      <ComparisonPanel documents={contract.history} result={contract.comparison} busy={busy} comparing={contract.busy === 'compare'} onCompare={contract.compare} onSource={setSource} />
    </main>
    {source && <SourceViewer selection={source} onClose={closeSource} />}
    {contract.error && <div role="alert" className="fixed bottom-4 left-24 right-4 z-[80] border border-coral bg-[#151515] text-white p-4 text-sm flex gap-3 shadow-xl">
      <AlertCircle className="w-5 h-5 text-coral shrink-0" /><span>{contract.error}</span>
    </div>}
  </div>;
}
