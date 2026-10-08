import { z } from 'zod';
import { benefitsSchema, chatSchema, documentSchema, Message } from './contracts';
import { auditSchema, comparisonSchema, IndiaContext, sourceDocumentSchema } from './audit-contracts';
import { consumeChatStream, StreamError } from './sse';

const BASE_URL = (process.env.NEXT_PUBLIC_RAG_API_URL || 'http://localhost:8000').replace(/\/$/, '');

export class ApiError extends Error {
  constructor(message: string, public status: number, public requestId?: string) {
    super(requestId ? `${message} (Request: ${requestId})` : message);
  }
}

async function request<S extends z.ZodTypeAny>(path: string, schema: S, init: RequestInit = {}): Promise<z.output<S>> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), path === '/compare' ? 600_000 : 300_000);
  try {
    const response = await fetch(`${BASE_URL}${path}`, { ...init, signal: controller.signal, cache: 'no-store' });
    const requestId = response.headers.get('X-Request-ID') || undefined;
    const data: unknown = await response.json().catch(() => null);
    if (!response.ok) {
      const error = z.object({ detail: z.string() }).safeParse(data);
      throw new ApiError(error.success ? error.data.detail : 'The server could not process this request.', response.status, requestId);
    }
    const parsed = schema.safeParse(data);
    if (!parsed.success) throw new ApiError('The server returned an invalid response.', 502, requestId);
    return parsed.data;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (error instanceof Error && error.name === 'AbortError') {
      throw new ApiError('The request timed out. Try a smaller document.', 504);
    }
    throw new ApiError('Unable to reach the backend. Check that the service is running.', 0);
  } finally {
    clearTimeout(timer);
  }
}

function json(value: unknown): RequestInit {
  return { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(value) };
}

export const api = {
  upload(file: File) {
    const body = new FormData();
    body.append('file', file);
    return request('/upload', documentSchema, { method: 'POST', body });
  },
  document(id: string) { return request(`/document/${encodeURIComponent(id)}`, documentSchema); },
  remove(id: string) {
    return request(`/document/${encodeURIComponent(id)}`, z.object({ deleted: z.string().uuid() }), { method: 'DELETE' });
  },
  benefits(id: string) { return request('/benefits', benefitsSchema, json({ doc_id: id })); },
  audit(id: string, india: IndiaContext) { return request('/audit', auditSchema, json({ doc_id: id, india })); },
  compare(beforeId: string, afterId: string) { return request('/compare', comparisonSchema, json({ before_id: beforeId, after_id: afterId })); },
  source(id: string) { return request(`/document/${encodeURIComponent(id)}/source`, sourceDocumentSchema); },
  async pdf(id: string, signal: AbortSignal): Promise<Uint8Array> {
    const response = await fetch(`${BASE_URL}/document/${encodeURIComponent(id)}/file`, { signal, cache: 'no-store' });
    if (!response.ok) throw new ApiError('The original PDF is unavailable or expired.', response.status);
    return new Uint8Array(await response.arrayBuffer());
  },
  async chat(id: string, question: string, messages: Message[], streaming?: { onDraft: (text: string) => void; signal: AbortSignal }) {
    if (streaming) {
      const controller = new AbortController();
      const abort = () => controller.abort();
      streaming.signal.addEventListener('abort', abort, { once: true });
      if (streaming.signal.aborted) controller.abort();
      const timeout = setTimeout(abort, 300_000);
      try {
        const response = await fetch(`${BASE_URL}/chat/stream`, {
          ...json({ doc_id: id, question, history: messages.slice(-6).map(({ role, content }) => ({ role, content })) }),
          signal: controller.signal, cache: 'no-store',
        });
        if (!response.ok || !response.body) throw new ApiError('The streamed request could not start.', response.status, response.headers.get('X-Request-ID') || undefined);
        return await consumeChatStream(response.body, streaming.onDraft);
      } catch (error) {
        if (error instanceof ApiError) throw error;
        if (error instanceof StreamError) throw new ApiError(error.message, error.status, error.requestId);
        throw new ApiError(controller.signal.aborted ? 'The answer was cancelled or timed out.' : 'The answer stream failed validation or disconnected. Please retry.', 502);
      } finally {
        clearTimeout(timeout);
        streaming.signal.removeEventListener('abort', abort);
        streaming.onDraft('');
      }
    }
    return request('/chat', chatSchema, json({
      doc_id: id, question,
      history: messages.slice(-6).map(({ role, content }) => ({ role, content })),
    }));
  },
};
