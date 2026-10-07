import { unzipSync } from 'fflate';

export const MAX_UPLOAD_BYTES = 2 * 1024 * 1024;
export const MAX_TEXT_CHARS = 100_000;

export class ExtractionError extends Error {
  constructor(message: string, public status = 422) { super(message); }
}

export function validateFile(name: string, buffer: Buffer): string {
  if (buffer.length > MAX_UPLOAD_BYTES) throw new ExtractionError('File exceeds the 2 MiB upload limit.', 413);
  if (!buffer.length) throw new ExtractionError('The file is empty.');
  const ext = name.slice(name.lastIndexOf('.')).toLowerCase();
  const prefix = buffer.subarray(0, 5).toString('latin1');
  if (ext === '.pdf') {
    if (prefix !== '%PDF-') throw new ExtractionError('The file does not have a PDF signature.');
  } else if (ext === '.docx') {
    if (!prefix.startsWith('PK\x03\x04')) throw new ExtractionError('The file does not have a DOCX signature.');
    let bytes = 0;
    let count = 0;
    const names = new Set<string>();
    try {
      const files = unzipSync(buffer, { filter: file => {
        count += 1;
        bytes += file.originalSize;
        if (names.has(file.name) || count > 1000 || bytes > 10 * 1024 * 1024 || file.originalSize > Math.max(file.size, 1) * 200) {
          throw new ExtractionError('The DOCX archive exceeds the safety limit.');
        }
        names.add(file.name);
        return true;
      } });
      if (!files['[Content_Types].xml'] || !files['word/document.xml']) throw new ExtractionError('The archive is not a Word document.');
    } catch (error) {
      if (error instanceof ExtractionError) throw error;
      throw new ExtractionError('The Word document could not be parsed safely.');
    }
  } else if (ext === '.txt' || ext === '.md') {
    let text: string;
    try { text = new TextDecoder('utf-8', { fatal: true }).decode(buffer); }
    catch { throw new ExtractionError('Text files must use UTF-8 encoding.'); }
    if (Array.from(text).some(char => char.charCodeAt(0) < 32 && !'\n\r\t'.includes(char)) ||
      ['%PDF-', 'PK\x03\x04', 'MZ', '\x7fELF'].some(magic => prefix.startsWith(magic))) {
      throw new ExtractionError('File contents do not match the text extension.');
    }
  } else { throw new ExtractionError('Unsupported file type. Use PDF, DOCX, TXT, or MD.', 415); }
  return ext;
}

export async function extractText(name: string, buffer: Buffer): Promise<string> {
  const ext = validateFile(name, buffer);
  let text: string;
  if (ext === '.pdf') {
    const { PDFParse } = await import('pdf-parse');
    const parser = new PDFParse({ data: new Uint8Array(buffer), isEvalSupported: false });
    try {
      const info = await parser.getInfo();
      if (info.total > 60) throw new ExtractionError('PDFs above 60 pages are unsupported.');
      text = '';
      for (let page = 1; page <= info.total; page += 1) {
        const result = await parser.getText({ partial: [page], pageJoiner: '' });
        text += result.text;
        if (text.length > MAX_TEXT_CHARS) throw new ExtractionError('Extracted text exceeds the 100,000 character limit.');
      }
    } finally { await parser.destroy(); }
  } else if (ext === '.docx') {
    const mammoth = await import('mammoth');
    text = (await mammoth.extractRawText({ buffer })).value;
  } else { text = new TextDecoder('utf-8', { fatal: true }).decode(buffer); }
  if (text.length > MAX_TEXT_CHARS) throw new ExtractionError('Extracted text exceeds the 100,000 character limit.');
  if (!text.trim()) throw new ExtractionError('No extractable text found. Scanned PDFs need OCR.');
  return text.trim();
}
