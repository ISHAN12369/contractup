'use client';

import { useRef, useState } from 'react';
import { FileText, Loader2, Upload } from 'lucide-react';
import { StoredDocument } from '@/lib/contracts';

interface Props {
  document: StoredDocument | null;
  busy: boolean;
  onUpload: (file: File) => Promise<boolean>;
  status?: string;
}

export function UploadPanel({ document, busy, onUpload, status }: Props) {
  const input = useRef<HTMLInputElement>(null);
  const [paste, setPaste] = useState('');
  const [dragging, setDragging] = useState(false);
  async function loadPaste() {
    if (!paste.trim()) return;
    if (await onUpload(new File([paste.trim()], 'pasted-document.txt', { type: 'text/plain' }))) setPaste('');
  }
  return <section id="upload" className="studio-section cream-theme">
    <p className="text-xs uppercase tracking-widest mb-6">01 / Your document</p>
    <h2 className="heading-display text-4xl md:text-6xl mb-8">Upload. Understand.</h2>
    <div className="grid md:grid-cols-2 gap-8 w-full">
      <div>
        <input ref={input} type="file" aria-label="Upload contract" className="sr-only"
          accept=".pdf,.docx,.txt,.md" disabled={busy}
          onChange={event => {
            const file = event.target.files?.[0];
            if (file) void onUpload(file);
            event.target.value = '';
          }} />
        <button type="button" disabled={busy} onClick={() => input.current?.click()}
          onDragOver={event => { event.preventDefault(); setDragging(true); }}
          onDragLeave={() => setDragging(false)}
          onDrop={event => {
            event.preventDefault(); setDragging(false);
            const file = event.dataTransfer.files[0];
            if (file && !busy) void onUpload(file);
          }}
          className={`w-full border-2 border-dashed p-12 text-center transition-colors ${dragging ? 'border-coral bg-black/10' : 'border-current/30'}`}>
          {busy ? <Loader2 className="w-10 h-10 mx-auto mb-4 animate-spin" /> : <Upload className="w-10 h-10 mx-auto mb-4" />}
          <span className="block font-semibold" role="status">{busy ? (status || 'Processing…') : 'Drop a contract or choose a file'}</span>
          <span className="block text-xs mt-3">PDF, DOCX, TXT, MD · default limit 2 MiB</span>
        </button>
        <p className="text-xs leading-relaxed mt-4 opacity-75">Uploads, extracted text and vectors are retained until expiry or deletion. Local PII detection redacts detected entities before provider analysis; it can miss information. Browser history saves only document IDs and metadata.</p>
      </div>
      <div>
        <label htmlFor="paste-contract" className="block text-xs font-bold uppercase tracking-wider mb-3">Or paste contract text</label>
        <textarea id="paste-contract" value={paste} onChange={event => setPaste(event.target.value)}
          maxLength={100000} disabled={busy} rows={7} placeholder="Paste your contract here…"
          className="w-full bg-transparent border border-current/30 p-4 text-sm resize-y" />
        <button type="button" disabled={busy || !paste.trim()} onClick={() => void loadPaste()} className="studio-btn mt-4">Load text</button>
      </div>
    </div>
    {document && <div className="flex gap-3 items-start p-4 border border-current/30 mt-8 w-full" role="status">
      <FileText className="w-5 h-5 shrink-0" />
      <div><strong>{document.filename}</strong><p className="text-xs mt-1">{document.chars.toLocaleString()} characters · {document.num_chunks} {document.chunking_strategy} chunks · {document.ocr_pages} OCR pages · expires {new Date(document.expires_at * 1000).toLocaleString()}</p></div>
    </div>}
  </section>;
}
