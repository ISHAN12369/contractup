import { randomUUID } from 'node:crypto';
import { NextRequest, NextResponse } from 'next/server';
import { extractText, ExtractionError, MAX_UPLOAD_BYTES } from './extract';

// Vercel instances cannot share memory. This is a per-instance safety budget, not a distributed limiter.
let windowEnd = 0;
let requests = 0;

export async function handleExtract(req: NextRequest): Promise<NextResponse> {
  const requestId = randomUUID();
  const headers = { 'X-Request-ID': requestId, 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff' };
  const fail = (detail: string, status: number) => NextResponse.json(
    { error: detail, request_id: requestId }, { status, headers },
  );
  const origin = req.headers.get('origin');
  if (origin && origin !== req.nextUrl.origin) return fail('Origin is not allowed.', 403);
  if (Date.now() >= windowEnd) { windowEnd = Date.now() + 60_000; requests = 0; }
  if (++requests > 30) {
    const response = fail('Too many extraction requests. Try later.', 429);
    response.headers.set('Retry-After', '60');
    return response;
  }
  const limit = MAX_UPLOAD_BYTES + 65536;
  const declared = Number(req.headers.get('content-length') || '0');
  if (!Number.isFinite(declared) || declared < 0) return fail('Invalid content length.', 400);
  if (declared > limit) return fail('Request exceeds the upload limit.', 413);
  try {
    const reader = req.body?.getReader();
    if (!reader) return fail('No file uploaded.', 400);
    const chunks: Uint8Array[] = [];
    let size = 0;
    try {
      while (true) {
        const chunk = await reader.read();
        if (chunk.done) break;
        size += chunk.value.length;
        if (size > limit) { await reader.cancel(); return fail('Request exceeds the upload limit.', 413); }
        chunks.push(chunk.value);
      }
    } finally { reader.releaseLock(); }
    const form = await new Response(Buffer.concat(chunks), {
      headers: { 'Content-Type': req.headers.get('content-type') || '' },
    }).formData();
    const file = form.get('file');
    if (!file || typeof file === 'string') return fail('No file uploaded.', 400);
    if (file.size > MAX_UPLOAD_BYTES) return fail('File exceeds the 2 MiB upload limit.', 413);
    const text = await extractText(file.name, Buffer.from(await file.arrayBuffer()));
    return NextResponse.json({ text, chars: text.length }, { headers });
  } catch (error) {
    if (error instanceof ExtractionError) return fail(error.message, error.status);
    return fail('The document could not be parsed safely.', 422);
  }
}
