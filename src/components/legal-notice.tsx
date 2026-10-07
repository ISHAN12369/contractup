import { DISCLAIMER } from '@/lib/contracts';

export function LegalNotice() {
  return <p className="text-xs opacity-75 leading-relaxed mt-4">{DISCLAIMER}</p>;
}
