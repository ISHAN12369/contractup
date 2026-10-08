import { z } from 'zod';
import { chatSchema } from './contracts';

const draftSchema = z.object({ text: z.string().max(6000), verified: z.literal(false) });
const errorSchema = z.object({ detail: z.string(), status: z.number().int(), request_id: z.string().optional() });
export class StreamError extends Error {
  constructor(message: string, public status = 502, public requestId?: string) { super(message); }
}

export async function consumeChatStream(body: ReadableStream<Uint8Array>, onDraft: (text: string) => void) {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let complete: z.infer<typeof chatSchema> | null = null;
  try {
    while (true) {
      const { value, done } = await reader.read();
      buffer = (buffer + decoder.decode(value, { stream: !done })).replace(/\r\n/g, '\n');
      if (buffer.length > 100_000) throw new StreamError('The answer stream exceeded its safety limit.');
      let boundary: number;
      while ((boundary = buffer.indexOf('\n\n')) >= 0) {
        const frame = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        const lines = frame.split('\n');
        const event = lines.find(line => line.startsWith('event:'))?.slice(6).trim();
        const data = lines.filter(line => line.startsWith('data:')).map(line => line.slice(5).trimStart()).join('\n');
        if (!data || !event) continue;
        const parsed: unknown = JSON.parse(data);
        if (event === 'draft') onDraft(draftSchema.parse(parsed).text);
        else if (event === 'complete') complete = chatSchema.parse(parsed);
        else if (event === 'error') {
          const failure = errorSchema.parse(parsed);
          throw new StreamError(failure.detail, failure.status, failure.request_id);
        }
      }
      if (done) break;
    }
    if (!complete) throw new StreamError('The answer stream ended before validation. Please retry.');
    return complete;
  } finally {
    onDraft('');
    await reader.cancel().catch(() => undefined);
    reader.releaseLock();
  }
}
