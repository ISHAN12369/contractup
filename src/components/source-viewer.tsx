'use client';

import { useEffect, useRef, useState } from 'react';
import type { PDFDocumentProxy, RenderTask, TextLayer } from 'pdfjs-dist';
import { api } from '@/lib/api';
import { SourceDocument, SourceSelection } from '@/lib/audit-contracts';
import { markPdfText, normalizedPositions, sourceSlice } from '@/lib/source-highlight';
import { LegalNotice } from './legal-notice';

interface Props { selection: SourceSelection; onClose: () => void }

export function SourceViewer({ selection, onClose }: Props) {
  const [source, setSource] = useState<SourceDocument | null>(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('Loading source…');
  const canvas = useRef<HTMLCanvasElement>(null);
  const layer = useRef<HTMLDivElement>(null);
  const overlay = useRef<HTMLDivElement>(null);
  const close = useRef<HTMLButtonElement>(null);
  const dialog = useRef<HTMLDivElement>(null);
  const location = selection.location;
  const page = source?.pages.find(item => item.page === location.page);
  const quote = page ? sourceSlice(page.text, location.page_start, location.page_end) : selection.quote;

  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    close.current?.focus();
    const key = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
      if (event.key === 'Tab') {
        const nodes = Array.from(dialog.current?.querySelectorAll<HTMLElement>('button, a[href], summary, [tabindex="0"]') || []);
        const first = nodes[0], last = nodes.at(-1);
        if (event.shiftKey && document.activeElement === first && last) { event.preventDefault(); last.focus(); }
        if (!event.shiftKey && document.activeElement === last && first) { event.preventDefault(); first.focus(); }
      }
    };
    document.addEventListener('keydown', key);
    return () => { document.removeEventListener('keydown', key); previous?.focus(); };
  }, [onClose]);

  useEffect(() => {
    if (!source) return;
    const timer = setTimeout(onClose, Math.max(0, source.metadata.expires_at * 1000 - Date.now()));
    return () => clearTimeout(timer);
  }, [source, onClose]);

  useEffect(() => {
    const controller = new AbortController();
    let disposed = false;
    setSource(null); setError(''); setNotice('Loading source…');
    let pdf: PDFDocumentProxy | undefined;
    let render: RenderTask | undefined;
    let textLayer: TextLayer | undefined;
    const host = layer.current;
    const marks = overlay.current;
    host?.replaceChildren(); marks?.replaceChildren();
    async function load() {
      const record = await api.source(selection.docId);
      if (disposed) return;
      setSource(record);
      const currentPage = record.pages.find(item => item.page === location.page);
      if (!currentPage || location.page_start < 0 || location.page_end > Array.from(currentPage.text).length || location.page_end <= location.page_start) {
        throw new Error('This source location is unavailable. Re-run the audit on a fresh upload.');
      }
      if (!record.metadata.has_pdf || location.page === null) { setNotice('Highlighted in canonical extracted text.'); return; }
      const pdfjs = await import('pdfjs-dist');
      pdfjs.GlobalWorkerOptions.workerSrc = new URL('pdfjs-dist/build/pdf.worker.min.mjs', import.meta.url).toString();
      const data = await api.pdf(selection.docId, controller.signal);
      if (disposed) return;
      pdf = await pdfjs.getDocument({ data, isEvalSupported: false, disableFontFace: true }).promise;
      if (disposed) { await pdf.destroy(); return; }
      const pdfPage = await pdf.getPage(location.page);
      const base = pdfPage.getViewport({ scale: 1 });
      const scale = Math.min(1.5, 800 / base.width);
      const viewport = pdfPage.getViewport({ scale });
      const element = canvas.current;
      if (!element || !host || !marks || disposed) return;
      element.width = viewport.width; element.height = viewport.height;
      element.style.width = `${viewport.width}px`; element.style.height = `${viewport.height}px`;
      host.style.setProperty('--scale-factor', String(scale));
      host.style.setProperty('--total-scale-factor', String(scale));
      host.style.width = `${viewport.width}px`; host.style.height = `${viewport.height}px`;
      render = pdfPage.render({ canvas: element, viewport });
      await render.promise;
      if (disposed) return;
      const addMark = (left: number, top: number, width: number, height: number) => {
        const mark = document.createElement('span');
        mark.className = 'source-mark';
        Object.assign(mark.style, { left: `${left}px`, top: `${top}px`, width: `${width}px`, height: `${height}px` });
        marks.appendChild(mark);
      };
      if (currentPage.ocr) {
        const words = currentPage.words.filter(word => word.start < location.page_end && word.end > location.page_start);
        words.forEach(word => addMark(word.box[0] * viewport.width, word.box[1] * viewport.height, word.box[2] * viewport.width, word.box[3] * viewport.height));
        setNotice(words.length ? 'OCR word locations highlighted. Verify recognition against the image.' : 'OCR location could not be highlighted; use the extracted text below.');
      } else {
        textLayer = new pdfjs.TextLayer({ textContentSource: await pdfPage.getTextContent(), container: host, viewport });
        await textLayer.render();
        if (disposed) return;
        const selectedText = sourceSlice(currentPage.text, location.page_start, location.page_end);
        const needle = normalizedPositions(selectedText).text;
        const prefix = normalizedPositions(sourceSlice(currentPage.text, 0, location.page_start)).text;
        const occurrence = needle ? prefix.split(needle).length - 1 : 0;
        const boxes = markPdfText(host, selectedText, currentPage.text, occurrence);
        const bounds = host.getBoundingClientRect();
        boxes.forEach(box => addMark(box.left - bounds.left, box.top - bounds.top, box.width, box.height));
        setNotice(boxes.length ? 'Matched quotation highlighted on the original PDF.' : 'PDF text order differs from extraction; use the exact extracted passage below. No approximate highlight is shown.');
      }
    }
    void load().catch(failure => { if (!disposed) { setError(failure instanceof Error ? failure.message : 'Source could not be loaded.'); setNotice(''); } });
    return () => {
      disposed = true; controller.abort(); render?.cancel(); textLayer?.cancel();
      if (pdf) void pdf.destroy();
      host?.replaceChildren(); marks?.replaceChildren();
    };
  }, [selection.docId, location.page, location.page_start, location.page_end]);

  return <div ref={dialog} className="fixed inset-0 z-[90] bg-black/70 p-3 md:p-8 overflow-auto" role="dialog" aria-modal="true" aria-label="Document source viewer">
    <div className="max-w-5xl mx-auto bg-[#f4ead4] text-[#151515] p-5 md:p-8">
      <div className="flex justify-between gap-4"><h2 className="text-xl font-bold">{source?.metadata.filename || 'Document source'}</h2><button ref={close} onClick={onClose} className="underline">Close source</button></div>
      <p className="text-xs my-3">{location.page ? `Page ${location.page} · ` : ''}{location.section_id} · characters {location.start}–{location.end} (extracted text)</p>
      {notice && <p role="status" className="text-sm mb-4">{notice}</p>}
      {error && <p role="alert" className="text-red-800 mb-4">{error}</p>}
      <div className={`${source?.metadata.has_pdf ? '' : 'hidden'} overflow-auto max-h-[65vh] border border-black/20`}>
        <div className="relative w-fit"><canvas ref={canvas} aria-label="Original PDF page" /><div ref={layer} className="pdf-text-layer" /><div ref={overlay} className="absolute inset-0 pointer-events-none" /></div>
      </div>
      {page && <details open className="mt-5"><summary className="cursor-pointer text-sm font-bold">Canonical extracted passage</summary><pre className="whitespace-pre-wrap text-sm leading-relaxed mt-3 max-h-64 overflow-auto">{sourceSlice(page.text, Math.max(0, location.page_start - 120), location.page_start)}<mark className="bg-yellow-200">{quote}</mark>{sourceSlice(page.text, location.page_end, location.page_end + 120)}</pre></details>}
      <LegalNotice />
    </div>
  </div>;
}
