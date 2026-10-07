'use client';

import { Trash2, X } from 'lucide-react';
import { StoredDocument } from '@/lib/contracts';

interface Props {
  open: boolean; documents: StoredDocument[]; busy: boolean; onClose: () => void;
  onRestore: (document: StoredDocument) => Promise<void>;
  onRemove: (id: string) => Promise<void>; onClear: () => Promise<void>;
}

export function HistoryPanel({ open, documents, busy, onClose, onRestore, onRemove, onClear }: Props) {
  if (!open) return null;
  return <>
    <button aria-label="Close document history" className="studio-overlay open" onClick={onClose} />
    <aside role="dialog" aria-label="Document history" aria-modal="true" className="studio-sidebar-panel open">
      <div className="flex justify-between mb-6"><h2 className="heading-display text-xl">Documents</h2>
        <button aria-label="Close history" onClick={onClose}><X className="w-5 h-5" /></button>
      </div>
      <p className="text-xs opacity-70 mb-6">This browser remembers up to 10 IDs and metadata. Documents expire on the backend. Delete removes server data too.</p>
      {documents.length > 0 && <button disabled={busy} className="text-xs underline mb-4" onClick={() => void onClear()}>Delete all remembered documents</button>}
      {documents.length === 0 && <p className="text-sm opacity-60">No active document history.</p>}
      <div className="space-y-3">{documents.map(document => <div key={document.doc_id} className="border border-white/20 p-4 flex gap-2">
        <button disabled={busy} className="text-left min-w-0 flex-1" onClick={() => { void onRestore(document); onClose(); }}>
          <span className="block truncate font-semibold text-sm">{document.filename}</span>
          <span className="block text-xs opacity-60 mt-2">{document.chars.toLocaleString()} characters · {document.num_chunks} chunks</span>
          <span className="block text-xs opacity-60 mt-1">Expires {new Date(document.expires_at * 1000).toLocaleString()}</span>
        </button>
        <button disabled={busy} aria-label={`Delete ${document.filename}`} onClick={() => void onRemove(document.doc_id)}><Trash2 className="w-4 h-4" /></button>
      </div>)}</div>
    </aside>
  </>;
}
