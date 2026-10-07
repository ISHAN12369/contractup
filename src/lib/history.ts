import { documentSchema, StoredDocument } from './contracts';

export const HISTORY_KEY = 'contractiq_documents_v2';
const LEGACY_KEYS = ['contractiq_history', 'hf_api_key', 'groq_api_key'];

function metadataOnly(docs: unknown[], now: number): StoredDocument[] {
  return docs.flatMap(value => {
    const result = documentSchema.safeParse(value);
    return result.success && result.data.expires_at * 1000 > now ? [result.data] : [];
  }).slice(0, 10);
}

export function saveHistory(docs: StoredDocument[], storage: Storage = localStorage, now = Date.now()): void {
  try {
    // Parsing strips unknown properties: callers cannot accidentally persist text, previews or keys.
    storage.setItem(HISTORY_KEY, JSON.stringify(metadataOnly(docs, now)));
  } catch { /* A blocked/quota-limited storage must not prevent using an in-memory document. */ }
}

export function loadHistory(storage: Storage = localStorage, now = Date.now()): StoredDocument[] {
  try {
    LEGACY_KEYS.forEach(key => storage.removeItem(key));
    const raw: unknown = JSON.parse(storage.getItem(HISTORY_KEY) || '[]');
    const docs = metadataOnly(Array.isArray(raw) ? raw : [], now);
    saveHistory(docs, storage, now);
    return docs;
  } catch { return []; }
}
