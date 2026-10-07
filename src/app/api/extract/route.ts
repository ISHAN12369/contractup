import { NextRequest, NextResponse } from 'next/server';

export const runtime = 'nodejs';
export const maxDuration = 30;

export async function POST(req: NextRequest) {
  try {
    const formData = await req.formData();
    const file = formData.get('file') as File | null;

    if (!file) {
      return NextResponse.json({ error: 'No file uploaded' }, { status: 400 });
    }

    const buffer = Buffer.from(await file.arrayBuffer());
    const type = file.type;
    let text = '';

    if (type === 'application/pdf' || file.name.endsWith('.pdf')) {
      const pdfParse = (await import('pdf-parse')).default;
      const data = await pdfParse(buffer);
      text = data.text;
    } else if (
      type === 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' ||
      file.name.endsWith('.docx')
    ) {
      const mammoth = await import('mammoth');
      const result = await mammoth.extractRawText({ buffer });
      text = result.value;
    } else if (type === 'text/plain' || file.name.endsWith('.txt') || file.name.endsWith('.md')) {
      text = buffer.toString('utf-8');
    } else {
      return NextResponse.json({ error: 'Unsupported file type. Use PDF, DOCX, or TXT.' }, { status: 400 });
    }

    if (!text.trim()) {
      return NextResponse.json({ error: 'Could not extract text from file.' }, { status: 422 });
    }

    return NextResponse.json({ text: text.trim(), chars: text.length });
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : 'Extraction failed';
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
