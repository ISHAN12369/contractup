import { describe, expect, it } from 'vitest';
import { doc } from '@/test/fixtures';
import { HISTORY_KEY, loadHistory, saveHistory } from './history';

describe('metadata-only history', () => {
  it('deletes legacy text and keys, strips unknown fields, and removes expired records', () => {
    localStorage.setItem('contractiq_history', JSON.stringify([{ fullText: 'private old contract' }]));
    localStorage.setItem('hf_api_key', 'hf_secret');
    localStorage.setItem('groq_api_key', 'secret');
    localStorage.setItem(HISTORY_KEY, JSON.stringify([
      { ...doc, fullText: 'private', preview: 'also private' }, { ...doc, expires_at: 1 }, { wrong: true },
    ]));
    expect(loadHistory()).toEqual([doc]);
    expect(localStorage.getItem('contractiq_history')).toBeNull();
    expect(localStorage.getItem('groq_api_key')).toBeNull();
    expect(localStorage.getItem('hf_api_key')).toBeNull();
    expect(localStorage.getItem(HISTORY_KEY)).not.toContain('private');
  });

  it('does not crash when storage is blocked or malformed', () => {
    const blocked = { getItem() { throw new Error('blocked'); }, setItem() { throw new Error('blocked'); }, removeItem() { throw new Error('blocked'); } } as unknown as Storage;
    expect(loadHistory(blocked)).toEqual([]);
    expect(() => saveHistory([doc], blocked)).not.toThrow();
    localStorage.setItem(HISTORY_KEY, 'invalid JSON');
    expect(loadHistory()).toEqual([]);
  });
});
