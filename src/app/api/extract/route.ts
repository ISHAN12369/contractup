import { handleExtract } from '@/lib/extract-route';
import { NextRequest } from 'next/server';

export const runtime = 'nodejs';
export const maxDuration = 30;
export async function POST(request: NextRequest) {
  if (process.env.NEXT_PUBLIC_AUTH_REQUIRED === 'true' || process.env.NEXT_PUBLIC_SUPABASE_URL) {
    return Response.json({ error: 'Use the authenticated document upload service.' }, { status: 410 });
  }
  return handleExtract(request);
}
