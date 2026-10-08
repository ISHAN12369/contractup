import { z } from 'zod';

export const DISCLAIMER = 'Informational only, not legal advice. Verify findings against the contract with a qualified professional.';

export const documentSchema = z.object({
  doc_id: z.string().uuid(), filename: z.string(), chars: z.number().int().nonnegative(),
  num_chunks: z.number().int().positive(), created_at: z.number(), expires_at: z.number(),
  has_pdf: z.boolean().default(false), ocr_pages: z.number().int().default(0),
  chunking_strategy: z.string().default('recursive'),
});
export const findingSchema = z.object({
  party: z.string().min(1), benefit: z.string().min(1), kind: z.enum(['benefit', 'obligation']),
  clause: z.string().min(1), score: z.number().int().min(1).max(10), chunk_ids: z.array(z.string()).min(1),
});
export const sourceSchema = z.object({
  excerpt: z.number().int().positive(), chunk_id: z.string(), preview: z.string(),
  page: z.number().int().positive().nullable(), distance: z.number().nullable(),
  section_id: z.string().default('unsectioned'), start: z.number().int().default(0), end: z.number().int().default(0),
  page_start: z.number().int().default(0), page_end: z.number().int().default(0), ocr: z.boolean().default(false),
  retrieval_score: z.number().nullable().optional(),
});
export const chatSchema = z.object({
  answer: z.string().min(1), sources: z.array(sourceSchema), disclaimer: z.string(),
  strategy: z.string().default('dense'),
});
export const benefitsSchema = z.object({
  items: z.array(findingSchema), analyzed_chunks: z.number().int(), total_chunks: z.number().int(),
  disclaimer: z.string(),
}).refine(value => value.analyzed_chunks === value.total_chunks, 'Analysis is incomplete');

export type StoredDocument = z.infer<typeof documentSchema>;
export type Finding = z.infer<typeof findingSchema>;
export type Source = z.infer<typeof sourceSchema>;
export type BenefitsResult = z.infer<typeof benefitsSchema>;
export interface Message {
  role: 'user' | 'assistant';
  content: string;
  sources?: Source[];
}
