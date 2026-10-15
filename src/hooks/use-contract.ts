'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { api, ApiError } from '@/lib/api';
import { BenefitsResult, Message, StoredDocument } from '@/lib/contracts';
import { loadHistory, saveHistory } from '@/lib/history';
import { Audit, Comparison, IndiaContext } from '@/lib/audit-contracts';

export function useContract(account = 'local') {
  const readHistory = useCallback(() => loadHistory(localStorage, Date.now(), account), [account]);
  const [uploadStatus, setUploadStatus] = useState('');
  const [document, setDocument] = useState<StoredDocument | null>(null);
  const [history, setHistory] = useState<StoredDocument[]>([]);
  const [messages, setMessages] = useState<Message[]>([]);
  const [benefits, setBenefits] = useState<BenefitsResult | null>(null);
  const [audit, setAudit] = useState<Audit | null>(null);
  const [comparison, setComparison] = useState<Comparison | null>(null);
  const [draft, setDraft] = useState('');
  const streamController = useRef<AbortController | null>(null);
  const [busy, setBusy] = useState<'upload' | 'chat' | 'benefits' | 'audit' | 'compare' | 'history' | null>(null);
  const [error, setError] = useState('');
  const generation = useRef(0);
  const pending = useRef(false);

  useEffect(() => { setHistory(readHistory()); }, [readHistory]);

  const remember = useCallback((docs: StoredDocument[]) => {
    saveHistory(docs, localStorage, Date.now(), account);
    setHistory(docs);
  }, [account]);

  const reset = useCallback(() => {
    generation.current += 1;
    pending.current = false;
    streamController.current?.abort();
    setAudit(null); setComparison(null); setDraft('');
    setDocument(null); setMessages([]); setBenefits(null); setBusy(null); setError('');
  }, []);

  useEffect(() => () => { generation.current += 1; streamController.current?.abort(); }, []);

  useEffect(() => {
    if (!document) return;
    const timer = setTimeout(() => {
      reset();
      remember(readHistory());
      setError('This document has expired. Please upload it again.');
    }, Math.max(0, document.expires_at * 1000 - Date.now()));
    return () => clearTimeout(timer);
  }, [document, remember, reset, readHistory]);

  async function run(kind: NonNullable<typeof busy>, operation: (version: number) => Promise<void>, relatedDocId?: string): Promise<boolean> {
    if (pending.current) return false;
    pending.current = true;
    const version = generation.current;
    setBusy(kind); setError('');
    try {
      await operation(version);
      return generation.current === version;
    } catch (failure) {
      if (generation.current === version) {
        if (failure instanceof ApiError && failure.status === 404 && document && document.doc_id === relatedDocId) {
          remember(readHistory().filter(item => item.doc_id !== document.doc_id));
          setDocument(null); setMessages([]); setBenefits(null);
          setAudit(null); setComparison(null); setDraft('');
        }
        setError(failure instanceof Error ? failure.message : 'The request failed.');
      }
      return false;
    } finally {
      if (generation.current === version) { pending.current = false; setBusy(null); }
    }
  }

  async function upload(file: File) {
    return run('upload', async version => {
      setUploadStatus('Uploading…');
      const result = await api.upload(file, status => { if (generation.current === version) setUploadStatus(status); });
      if (generation.current !== version) return;
      remember([result, ...readHistory().filter(item => item.doc_id !== result.doc_id)].slice(0, 10));
      setUploadStatus('');
      setDocument(result); setMessages([]); setBenefits(null);
      setAudit(null); setComparison(null);
    });
  }

  async function restore(item: StoredDocument) {
    await run('history', async version => {
      try {
        const result = await api.document(item.doc_id);
        if (generation.current !== version) return;
        setDocument(result); setMessages([]); setBenefits(null);
        setAudit(null); setComparison(null);
      } catch (failure) {
        if (generation.current === version && failure instanceof ApiError && failure.status === 404) {
          remember(readHistory().filter(doc => doc.doc_id !== item.doc_id));
        }
        throw failure;
      }
    });
  }

  async function remove(id: string) {
    await run('history', async version => {
      await api.remove(id);
      if (generation.current !== version) return;
      remember(readHistory().filter(item => item.doc_id !== id));
      if (document?.doc_id === id && generation.current === version) reset();
    });
  }

  async function clearHistory() {
    await run('history', async version => {
      // Forget only after server deletion succeeds, preserving a retry handle on failure.
      for (const item of readHistory()) {
        await api.remove(item.doc_id);
        if (generation.current !== version) return;
        remember(readHistory().filter(doc => doc.doc_id !== item.doc_id));
        if (document?.doc_id === item.doc_id && generation.current === version) {
          setDocument(null); setMessages([]); setBenefits(null);
          setAudit(null); setComparison(null);
        }
      }
    });
  }

  async function analyze() {
    if (!document) return;
    await run('benefits', async version => {
      const result = await api.benefits(document.doc_id);
      if (generation.current === version) setBenefits(result);
    }, document.doc_id);
  }

  async function chat(question: string) {
    if (!document || !question.trim()) return false;
    return run('chat', async version => {
      const controller = new AbortController();
      streamController.current = controller;
      const result = await api.chat(document.doc_id, question.trim(), messages, {
        signal: controller.signal,
        onDraft: text => { if (generation.current === version) setDraft(text); },
      });
      if (generation.current === version) setMessages(previous => [
        ...previous, { role: 'user', content: question.trim() },
        { role: 'assistant', content: result.answer, sources: result.sources },
      ]);
    }, document.doc_id);
  }

  async function runAudit(india: IndiaContext) {
    if (!document) return;
    await run('audit', async version => {
      const result = await api.audit(document.doc_id, india);
      if (generation.current === version) setAudit(result);
    }, document.doc_id);
  }

  async function compare(beforeId: string, afterId: string) {
    await run('compare', async version => {
      const result = await api.compare(beforeId, afterId);
      if (generation.current === version) setComparison(result);
    });
  }

  return { document, history, messages, benefits, audit, comparison, draft, busy, error, uploadStatus, upload, restore, remove, clearHistory, analyze, chat, runAudit, compare, reset };
}
