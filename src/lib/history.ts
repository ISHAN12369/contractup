import { documentSchema, StoredDocument } from './contracts';

export const HISTORY_KEY = 'contractiq_documents_v2';
const LEGACY_KEYS = ['contractiq_history', 'hf_api_key', 'groq_api_key'];

function metadataOnly(docs: unknown[], now: number): StoredDocument[] {
  return docs.flatMap(value => {
    const result = documentSchema.safeParse(value);
    return result.success && result.data.expires_at * 1000 > now ? [result.data] : [];
  }).slice(0, 10);
}

export function saveHistory(docs: StoredDocument[], storage: Storage = localStorage, now = Date.now(), account = 'local'): void {
  try {
    // Parsing strips unknown properties: callers cannot accidentally persist text, previews or keys.
    storage.setItem(account === 'local' ? HISTORY_KEY : `${HISTORY_KEY}:${account}`, JSON.stringify(metadataOnly(docs, now)));
  } catch { /* A blocked/quota-limited storage must not prevent using an in-memory document. */ }
}

export function loadHistory(storage: Storage = localStorage, now = Date.now(), account = 'local'): StoredDocument[] {
  try {
    LEGACY_KEYS.forEach(key => storage.removeItem(key));
    const raw: unknown = JSON.parse(storage.getItem(account === 'local' ? HISTORY_KEY : `${HISTORY_KEY}:${account}`) || '[]');
    const docs = metadataOnly(Array.isArray(raw) ? raw : [], now);
    saveHistory(docs, storage, now, account);
    return docs;
  } catch { return []; }
}
