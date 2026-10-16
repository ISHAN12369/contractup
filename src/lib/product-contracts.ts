import { z } from 'zod';
import { auditSchema } from './audit-contracts';
import { sourceSchema } from './contracts';

export const savedAuditSchema = z.object({ audit: auditSchema, filename: z.string(), generated_at: z.number(), expires_at: z.number() });
export const shareSchema = z.object({ token: z.string().regex(/^[A-Za-z0-9_-]{43}$/), expires_at: z.number() });
export const workspaceAnswerSchema = z.object({ answer: z.string(), disclaimer: z.string(), sources: z.array(sourceSchema.extend({ doc_id: z.string().uuid(), filename: z.string() })) });
export type SavedAudit = z.infer<typeof savedAuditSchema>;
export type WorkspaceAnswer = z.infer<typeof workspaceAnswerSchema>;
