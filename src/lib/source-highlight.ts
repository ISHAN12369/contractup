/** Normalize PDF text while retaining UTF-16 positions for DOM Range offsets. */
export function normalizedPositions(text: string): { text: string; positions: number[] } {
  const characters: string[] = [];
  const positions: number[] = [];
  let index = 0;
  for (const char of Array.from(text)) {
    if (/\s/.test(char)) {
      if (characters.length && characters.at(-1) !== ' ') { characters.push(' '); positions.push(index); }
    } else {
      const folded = char.toLowerCase();
      for (let unit = 0; unit < folded.length; unit += 1) { characters.push(folded[unit]); positions.push(index); }
    }
    index += char.length;
  }
  if (characters.at(-1) === ' ') { characters.pop(); positions.pop(); }
  return { text: characters.join(''), positions };
}

export function findQuote(text: string, quote: string, occurrence = 0): [number, number] | null {
  const haystack = normalizedPositions(text);
  const needle = normalizedPositions(quote).text;
  if (!needle) return null;
  let start = -1;
  for (let count = 0; count <= occurrence; count += 1) {
    start = haystack.text.indexOf(needle, start + 1);
    if (start < 0) return null;
  }
  if (start < 0) return null;
  const last = haystack.positions[start + needle.length - 1];
  return [haystack.positions[start], last + (text.codePointAt(last)! > 0xffff ? 2 : 1)];
}

/** Backend offsets use Python Unicode code points, not JavaScript UTF-16 units. */
export function sourceSlice(text: string, start: number, end?: number) {
  return Array.from(text).slice(start, end).join('');
}

/** Repeated quotes need matching page order to identify the intended occurrence. */
export function findPdfQuote(text: string, quote: string, canonical: string, occurrence = 0): [number, number] | null {
  const needle = normalizedPositions(quote).text;
  if (!needle) return null;
  const extracted = normalizedPositions(canonical).text;
  const rendered = normalizedPositions(text).text;
  const repeated = extracted.indexOf(needle) !== extracted.lastIndexOf(needle)
    || rendered.indexOf(needle) !== rendered.lastIndexOf(needle);
  if (repeated && extracted !== rendered) return null;
  return findQuote(text, quote, occurrence);
}

export function markPdfText(layer: HTMLElement, quote: string, canonical: string, occurrence = 0): DOMRect[] {
  const walker = document.createTreeWalker(layer, NodeFilter.SHOW_TEXT);
  const nodes: { node: Text; start: number; end: number }[] = [];
  let text = '';
  let current: Node | null;
  while ((current = walker.nextNode())) {
    const value = current.textContent || '';
    nodes.push({ node: current as Text, start: text.length, end: text.length + value.length });
    text += value + ' '; // PDF.js text items may omit visual whitespace between spans.
  }
  const span = findPdfQuote(text, quote, canonical, occurrence);
  if (!span) return [];
  const first = nodes.find(item => span[0] >= item.start && span[0] < item.end);
  const last = nodes.find(item => span[1] > item.start && span[1] <= item.end);
  if (!first || !last) return [];
  const range = document.createRange();
  range.setStart(first.node, span[0] - first.start);
  range.setEnd(last.node, span[1] - last.start);
  return Array.from(range.getClientRects()).filter(rect => rect.width > 0 && rect.height > 0);
}
