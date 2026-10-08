'use client';

import { useEffect, useRef, useState } from 'react';
import { Loader2, Send } from 'lucide-react';
import { Message } from '@/lib/contracts';
import { SourceSelection } from '@/lib/audit-contracts';
import { LegalNotice } from './legal-notice';

const QUESTIONS = [
  ['Who benefits most?', 'Which party benefits most from the available excerpts and why?'],
  ['Breach consequences', 'What happens if either party breaches this agreement?'],
  ['Liability & risks', 'What are the liability clauses and who bears the most risk?'],
  ['Termination', 'Under what conditions can this agreement be terminated, and by whom?'],
  ['Unfair clauses', 'Are there any potentially one-sided clauses in the retrieved excerpts?'],
  ['Plain summary', 'Summarize the available contract excerpts in plain English.'],
  ['Key obligations', 'What are the key obligations for each party?'],
  ['Dispute resolution', 'How are disputes handled between the parties?'],
];

interface Props { messages: Message[]; available: boolean; busy: boolean; sending: boolean; onSend: (question: string) => Promise<boolean>; draft?: string; docId?: string; onSource?: (selection: SourceSelection) => void }

export function ChatPanel({ messages, available, busy, sending, onSend, draft, docId, onSource }: Props) {
  const [input, setInput] = useState('');
  const [expanded, setExpanded] = useState(false);
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => { if (messages.length) end.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' }); }, [messages]);
  async function submit(question: string) {
    if (!question.trim() || busy || !available) return;
    if (await onSend(question)) setInput('');
  }
  return <section id="chat" className="studio-section cream-theme">
    <p className="text-xs uppercase tracking-widest mb-6">03 / Ask your contract</p>
    <h2 className="heading-display text-4xl md:text-6xl mb-6">Clarity in context.</h2>
    <div className={`${expanded ? 'fixed inset-4 z-[60] bg-[#f4ead4] p-6 overflow-auto shadow-2xl' : 'w-full'}`}>
      <div className="flex justify-between items-center mb-4"><h3 className="font-bold">AI auditor</h3>
        <button className="text-xs underline" onClick={() => setExpanded(value => !value)}>{expanded ? 'Exit full screen' : 'Full screen'}</button>
      </div>
      <div className="flex flex-wrap gap-2 mb-4">{QUESTIONS.map(([label, question]) =>
        <button key={label} disabled={!available || busy} className="text-xs border border-current/30 px-3 py-2 hover:bg-black/5" onClick={() => void submit(question)}>{label}</button>)}
      </div>
      <div className="border border-current/20 p-5 min-h-[220px] max-h-[55vh] overflow-y-auto" aria-live="polite" role="log" aria-label="Contract chat">
        {messages.length === 0 && <p className="text-sm opacity-60">{available ? 'Ask a question. Answers use four retrieved excerpts and stream as an unverified draft until validation finishes.' : 'Upload a contract to start chatting.'}</p>}
        {messages.map((message, index) => <article key={index} className={`mb-6 ${message.role === 'user' ? 'pl-8' : ''}`}>
          <p className="text-xs uppercase tracking-wider font-bold mb-2">{message.role === 'user' ? 'You' : 'ContractIQ'}</p>
          <p className="text-sm leading-relaxed whitespace-pre-wrap">{message.content}</p>
          {message.sources?.map(source => <details key={source.excerpt} className="mt-3 text-xs border-l-2 border-coral pl-3">
            <summary className="cursor-pointer">Excerpt {source.excerpt}{source.page ? ` · Page ${source.page}` : ''} · {source.chunk_id}</summary>
            <blockquote className="mt-2 whitespace-pre-wrap leading-relaxed">{source.preview}</blockquote>
            {docId && onSource && <button className="underline mt-2" onClick={() => onSource({ docId, location: source, quote: source.preview })}>Highlight on source</button>}
          </details>)}
          {message.role === 'assistant' && <LegalNotice />}
        </article>)}
        {sending && <p className="flex items-center gap-2 text-sm"><Loader2 className="w-4 h-4 animate-spin" /> {draft ? 'Unverified draft — checking citations before saving' : 'Retrieving and checking excerpts…'}</p>}
        {sending && draft && <div className="border border-dashed border-current/30 p-3 mt-3"><p className="text-sm whitespace-pre-wrap">{draft}</p><LegalNotice /></div>}
        <div ref={end} />
      </div>
      <form className="flex gap-2 mt-4" onSubmit={event => { event.preventDefault(); void submit(input); }}>
        <input aria-label="Question about contract" value={input} onChange={event => setInput(event.target.value)} maxLength={2000}
          disabled={!available || busy} placeholder="Ask about a clause, obligation, or consequence…" className="flex-1 min-w-0 border border-current/30 bg-transparent p-3 text-sm" />
        <button aria-label="Send question" disabled={!available || busy || !input.trim()} className="studio-btn px-4"><Send className="w-4 h-4" /></button>
      </form>
      <LegalNotice />
    </div>
  </section>;
}
