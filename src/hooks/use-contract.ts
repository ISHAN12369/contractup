'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { api, ApiError } from '@/lib/api';
import { BenefitsResult, Message, StoredDocument } from '@/lib/contracts';
import { loadHistory, saveHistory } from '@/lib/history';

export function useContract() {
  const [document, setDocument] = useState<StoredDocument | null>(null);
  const [history, setHistory] = useState<StoredDocument[]>([]);
  const [messages, setMessages] = useState<Message[]>([]);
  const [benefits, setBenefits] = useState<BenefitsResult | null>(null);
  const [busy, setBusy] = useState<'upload' | 'chat' | 'benefits' | 'history' | null>(null);
  const [error, setError] = useState('');
  const generation = useRef(0);
  const pending = useRef(false);

  useEffect(() => { setHistory(loadHistory()); }, []);

  const remember = useCallback((docs: StoredDocument[]) => {
    saveHistory(docs);
    setHistory(docs);
  }, []);

  const reset = useCallback(() => {
    generation.current += 1;
    pending.current = false;
    setDocument(null); setMessages([]); setBenefits(null); setBusy(null); setError('');
  }, []);

  useEffect(() => {
    if (!document) return;
    const timer = setTimeout(() => {
      reset();
      remember(loadHistory());
      setError('This document has expired. Please upload it again.');
    }, Math.max(0, document.expires_at * 1000 - Date.now()));
    return () => clearTimeout(timer);
  }, [document, remember, reset]);

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
          remember(loadHistory().filter(item => item.doc_id !== document.doc_id));
          setDocument(null); setMessages([]); setBenefits(null);
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
      const result = await api.upload(file);
      // Always remember successful uploads, including one whose view was reset while indexing.
      remember([result, ...loadHistory().filter(item => item.doc_id !== result.doc_id)].slice(0, 10));
      if (generation.current !== version) return;
      setDocument(result); setMessages([]); setBenefits(null);
    });
  }

  async function restore(item: StoredDocument) {
    await run('history', async version => {
      try {
        const result = await api.document(item.doc_id);
        if (generation.current !== version) return;
        setDocument(result); setMessages([]); setBenefits(null);
      } catch (failure) {
        if (failure instanceof ApiError && failure.status === 404) {
          remember(loadHistory().filter(doc => doc.doc_id !== item.doc_id));
        }
        throw failure;
      }
    });
  }

  async function remove(id: string) {
    await run('history', async () => {
      await api.remove(id);
      remember(loadHistory().filter(item => item.doc_id !== id));
      if (document?.doc_id === id) reset();
    });
  }

  async function clearHistory() {
    await run('history', async () => {
      // Forget only after server deletion succeeds, preserving a retry handle on failure.
      for (const item of loadHistory()) {
        await api.remove(item.doc_id);
        remember(loadHistory().filter(doc => doc.doc_id !== item.doc_id));
        if (document?.doc_id === item.doc_id) {
          setDocument(null); setMessages([]); setBenefits(null);
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
      const result = await api.chat(document.doc_id, question.trim(), messages);
      if (generation.current === version) setMessages(previous => [
        ...previous, { role: 'user', content: question.trim() },
        { role: 'assistant', content: result.answer, sources: result.sources },
      ]);
    }, document.doc_id);
  }

  return { document, history, messages, benefits, busy, error, upload, restore, remove, clearHistory, analyze, chat, reset };
}
