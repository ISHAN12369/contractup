import { z } from 'zod';
import { benefitsSchema, chatSchema, documentSchema, Message } from './contracts';

const BASE_URL = (process.env.NEXT_PUBLIC_RAG_API_URL || 'http://localhost:8000').replace(/\/$/, '');

export class ApiError extends Error {
  constructor(message: string, public status: number, public requestId?: string) {
    super(requestId ? `${message} (Request: ${requestId})` : message);
  }
}

async function request<T>(path: string, schema: z.ZodType<T>, init: RequestInit = {}): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 300_000);
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
  chat(id: string, question: string, messages: Message[]) {
    return request('/chat', chatSchema, json({
      doc_id: id, question,
      history: messages.slice(-6).map(({ role, content }) => ({ role, content })),
    }));
  },
};
