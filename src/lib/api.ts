import { z } from 'zod';
import { benefitsSchema, chatSchema, documentSchema, Message } from './contracts';
import { auditSchema, comparisonSchema, IndiaContext, sourceDocumentSchema } from './audit-contracts';
import { consumeChatStream, StreamError } from './sse';
import { authenticatedHeaders, authEpoch } from './auth-session';
import { savedAuditSchema, shareSchema, workspaceAnswerSchema } from './product-contracts';

const BASE_URL = (process.env.NEXT_PUBLIC_RAG_API_URL || 'http://localhost:8000').replace(/\/$/, '');

export class ApiError extends Error {
  constructor(message: string, public status: number, public requestId?: string) {
    super(requestId ? `${message} (Request: ${requestId})` : message);
  }
}

async function request<S extends z.ZodTypeAny>(path: string, schema: S, init: RequestInit = {}): Promise<z.output<S>> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), path === '/compare' ? 600_000 : 300_000);
  const epoch = authEpoch();
  try {
    const response = await fetch(`${BASE_URL}${path}`, { ...init, headers: await authenticatedHeaders(init.headers), signal: controller.signal, cache: 'no-store' });
    if (epoch !== authEpoch()) throw new ApiError('Your session changed. Please retry.', 401);
    const requestId = response.headers.get('X-Request-ID') || undefined;
    const data: unknown = await response.json().catch(() => null);
    if (epoch !== authEpoch()) throw new ApiError('Your session changed. Please retry.', 401);
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

const ingestionSchema = z.object({ doc_id: z.string().uuid(), status: z.enum(['uploading', 'queued', 'processing', 'ready', 'failed']), document: documentSchema.optional(), detail: z.string().optional() });

export const api = {
  documents() { return request('/documents', z.array(documentSchema)); },
  savedAudit(id: string) { return request(`/document/${encodeURIComponent(id)}/audit`, savedAuditSchema); },
  workspaceChat(docIds: string[], question: string) { return request('/workspace/chat', workspaceAnswerSchema, json({ doc_ids: docIds, question })); },
  createShare(id: string, ttl: number) { return request(`/document/${encodeURIComponent(id)}/shares`, shareSchema, json({ ttl_seconds: ttl })); },
  revokeShares(id: string) { return request(`/document/${encodeURIComponent(id)}/shares`, z.object({ revoked: z.boolean() }), { method: 'DELETE' }); },
  readShare(token: string) { return request('/share/read', savedAuditSchema, json({ token })); },
  async report(id: string): Promise<Blob> {
    const epoch = authEpoch();
    const response = await fetch(`${BASE_URL}/document/${encodeURIComponent(id)}/report`, { headers: await authenticatedHeaders(), cache: 'no-store', signal: AbortSignal.timeout(60_000) });
    if (!response.ok) throw new ApiError(response.status === 409 ? 'Run an audit before exporting it.' : 'The report is unavailable or expired.', response.status);
    const blob = await response.blob();
    if (epoch !== authEpoch()) throw new ApiError('Your session changed.', 401);
    if (!response.headers.get('Content-Type')?.startsWith('application/pdf')) throw new ApiError('Invalid report response.', 502);
    return blob;
  },
  async upload(file: File, onStatus?: (status: string) => void) {
    const body = new FormData();
    body.append('file', file);
    const epoch = authEpoch();
    const result = await request('/upload', z.union([documentSchema, ingestionSchema]), { method: 'POST', body });
    if (!('status' in result)) return result;
    const deadline = Date.now() + 12 * 60_000;
    while (Date.now() < deadline) {
      if (authEpoch() !== epoch) throw new ApiError('Your session changed. Please retry.', 401);
      const progress = await request(`/ingestion/${encodeURIComponent(result.doc_id)}`, ingestionSchema);
      if (progress.status === 'ready' && progress.document) return progress.document;
      if (progress.status === 'failed') throw new ApiError(progress.detail || 'Document processing failed. Please retry.', 422);
      onStatus?.(progress.status === 'processing' ? 'Reading and indexing your document…' : 'Waiting for a processing slot…');
      await new Promise(resolve => setTimeout(resolve, 3000));
    }
    throw new ApiError(`Processing has not finished. Document ID: ${result.doc_id}. Please retry later.`, 504);
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
    const epoch = authEpoch();
    const response = await fetch(`${BASE_URL}/document/${encodeURIComponent(id)}/file`, { signal, headers: await authenticatedHeaders(), cache: 'no-store' });
    if (epoch !== authEpoch()) throw new ApiError('Your session changed.', 401);
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
        const epoch = authEpoch();
        const response = await fetch(`${BASE_URL}/chat/stream`, {
          ...json({ doc_id: id, question, history: messages.slice(-6).map(({ role, content }) => ({ role, content })) }),
          headers: await authenticatedHeaders({ 'Content-Type': 'application/json' }), signal: controller.signal, cache: 'no-store',
        });
        if (epoch !== authEpoch()) throw new ApiError('Your session changed.', 401);
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
