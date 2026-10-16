'use client';

import { useEffect, useRef, useState } from 'react';
import { api } from '@/lib/api';

export function ReportActions({ docId, sharing }: { docId: string; sharing: boolean }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [link, setLink] = useState('');
  const [expiry, setExpiry] = useState(0);
  const [ttl, setTtl] = useState(900);
  const mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  async function run(action: () => Promise<void>) {
    if (busy) return;
    setBusy(true); setError('');
    try { await action(); } catch (failure) { if (mounted.current) setError(failure instanceof Error ? failure.message : 'The request failed.'); }
    finally { if (mounted.current) setBusy(false); }
  }
  return <section aria-label="Export and share audit" className="border border-white/20 p-5 space-y-4">
    <h3 className="text-xl">Keep or share this review</h3>
    <button className="studio-btn" disabled={busy} onClick={() => void run(async () => {
      const blob = await api.report(docId);
      if (!mounted.current) return;
      const url = URL.createObjectURL(blob); const anchor = document.createElement('a');
      anchor.href = url; anchor.download = 'contractiq-audit.pdf'; anchor.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    })}>Export PDF report</button>
    <p className="text-xs opacity-80">Reports contain quotations and possible personal information. Downloaded copies do not expire.</p>
    {sharing ? <>
      <p className="text-sm">Anyone with the link can read a saved copy of this audit, including quotations and names. It does not give access to the original file or your workspace.</p>
      <label className="block text-sm">Link lifetime <select className="audit-input" value={ttl} onChange={e => setTtl(Number(e.target.value))} disabled={busy}>
        <option value={900}>15 minutes</option><option value={3600}>1 hour</option><option value={86400}>24 hours</option>
      </select></label>
      <p className="text-xs">Links also expire when the source document expires or is deleted. Later audit runs do not change a shared copy.</p>
      <div className="flex flex-wrap gap-4"><button disabled={busy} className="underline" onClick={() => void run(async () => {
        const result = await api.createShare(docId, ttl);
        if (mounted.current) { setLink(`${window.location.origin}/share#${result.token}`); setExpiry(result.expires_at); }
      })}>Create read-only link</button>
      <button disabled={busy} className="underline" onClick={() => void run(async () => { await api.revokeShares(docId); if (mounted.current) { setLink(''); setError('All links for this document have been revoked.'); } })}>Revoke all links</button></div>
      {link && <div><label className="text-sm">Copy this link<input className="audit-input" readOnly value={link} onFocus={e => e.target.select()} /></label><p className="text-xs mt-2">Expires {new Date(expiry * 1000).toLocaleString()}</p></div>}
    </> : <p className="text-sm">Read-only sharing is available in an authenticated production workspace.</p>}
    {error && <p role="status" className="text-sm">{error}</p>}
  </section>;
}
