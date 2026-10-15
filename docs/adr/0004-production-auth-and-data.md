# ADR 0004: Supabase identity, Postgres vectors, private object storage

Status: accepted for Phase 3, 12 October 2026.

Use Supabase Auth for email/password identity. The browser keeps sessions in memory and sends a bearer access token. The API accepts only asymmetric RS256/ES256 tokens from the configured issuer/JWKS, with audience, expiry, authenticated role and UUID subject checks. Legacy shared HS256 signing secrets are intentionally unsupported. Rotate a project to asymmetric signing before deployment. The Supabase publishable key is public; service-role keys never belong in the frontend.

Every HTTP document operation derives its owner from the verified request context. SQL includes the owner and document IDs; foreign/missing IDs have the same 404 behavior. No client-supplied owner is trusted. Composite chunk/document foreign keys prevent mismatched ownership. Server-only cleanup can traverse tenants. The database has no public/browser access and does not rely on Supabase RLS: this repository uses explicit SQL filters, enforced by isolation tests. A future public database interface requires RLS and a separate security review. Use separate migration and least-privilege application database roles in deployment.

Postgres with pgvector replaces file-backed Chroma in production. Exact cosine search over tenant/document-filtered vectors is predictable at the bounded 120-chunk default, avoiding approximate-index filtering recall tradeoffs. MiniLM vectors are 384 dimensions; changing embedding models requires re-indexing and a migration, not only an environment change. The local Chroma adapter remains for Phase 2 reproducibility and offline development.

Original uploads live in private S3/R2-compatible storage; parsed records/vectors live in Postgres. PDF downloads receive short-lived signed URLs after authorization, capped by remaining retention. A signed URL is a bearer capability, usable until expiry even after sign-out; deleting the object revokes normal reads but does not erase downloaded copies, versions, backups or CDN caches. Configure private buckets, TLS, encryption, lifecycle rules for current/noncurrent versions and backups, and tightly scoped backend credentials. Moto is an ephemeral localhost API emulator only, not proof of real cloud access policy or expiry enforcement.

References: [Supabase JWTs](https://supabase.com/docs/guides/auth/jwts), [pgvector](https://github.com/pgvector/pgvector), [S3 signed URLs](https://docs.aws.amazon.com/AmazonS3/latest/userguide/using-presigned-url.html).
