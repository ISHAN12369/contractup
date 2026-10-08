import { z } from 'zod';
import { documentSchema } from './contracts';

export const locationSchema = z.object({
  chunk_id: z.string(), page: z.number().int().positive().nullable(), section_id: z.string(),
  start: z.number().int().nonnegative(), end: z.number().int().nonnegative(),
  page_start: z.number().int().nonnegative(), page_end: z.number().int().nonnegative(), ocr: z.boolean(),
});
export const riskSchema = z.object({ level: z.enum(['low', 'medium', 'high']), score: z.number().int().min(0).max(100), why: z.string(), rubric_id: z.string() });
export const clauseSchema = z.object({
  id: z.string(), type: z.string(), quoted_text: z.string(), chunk_id: z.string(), party: z.string(),
  confidence: z.number().min(0).max(1), location: locationSchema, risk: riskSchema,
  redline: z.object({ original: z.string(), suggested: z.string(), rationale: z.string(), disclaimer: z.string() }).nullable(),
});
export const auditSchema = z.object({
  doc_id: z.string().uuid(), contract_type: z.string(), checklist: z.array(z.string()), clauses: z.array(clauseSchema),
  overall_risk: riskSchema.nullable(), summary: z.string(), dropped_claims: z.number().int().nonnegative(),
  analyzed_chunks: z.number().int(), total_chunks: z.number().int(), warnings: z.array(z.string()),
  steps: z.array(z.string()), disclaimer: z.string(),
  rule_checks: z.array(z.object({
    id: z.string(), title: z.string(), status: z.enum(['review', 'not_found', 'context_needed', 'attention', 'within_reference']),
    detail: z.string(), source_title: z.string(), source_url: z.string().url().refine(value => value.startsWith('https://')),
    section: z.string(), evidence: z.array(locationSchema), disclaimer: z.string(),
  })),
}).refine(value => value.analyzed_chunks === value.total_chunks, 'Audit coverage is incomplete');
export const comparisonSchema = z.object({
  before_id: z.string().uuid(), after_id: z.string().uuid(), unchanged: z.number().int(),
  overall_risk_delta: z.number().nullable(), warnings: z.array(z.string()), disclaimer: z.string(),
  changes: z.array(z.object({
    kind: z.enum(['added', 'removed', 'changed']), before: clauseSchema.nullable(), after: clauseSchema.nullable(),
    similarity: z.number().nullable(), risk_delta: z.number(), explanation: z.string(),
  })),
});
export const sourceDocumentSchema = z.object({
  metadata: documentSchema,
  pages: z.array(z.object({
    page: z.number().nullable(), text: z.string(), start: z.number(), ocr: z.boolean(),
    words: z.array(z.object({ start: z.number(), end: z.number(), box: z.tuple([z.number(), z.number(), z.number(), z.number()]) })),
  })),
  chunks: z.array(z.object({ id: z.string(), text: z.string() }).passthrough()),
});
export type Location = z.infer<typeof locationSchema>;
export type Audit = z.infer<typeof auditSchema>;
export type Clause = z.infer<typeof clauseSchema>;
export type Comparison = z.infer<typeof comparisonSchema>;
export type SourceDocument = z.infer<typeof sourceDocumentSchema>;
export interface SourceSelection { docId: string; location: Location; quote: string }
export interface IndiaContext {
  enabled: boolean;
  state: string;
  premises: 'residential' | 'commercial' | 'unknown';
  model_act_applicable: boolean;
  monthly_rent: number | null;
  deposit: number | null;
  enabled_rules: string[];
}
