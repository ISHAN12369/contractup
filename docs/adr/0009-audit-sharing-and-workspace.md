# ADR 0009: server-owned audit snapshots and bounded workspace questions

Status: accepted, Phase 4, 16 October 2026.

## Context

A downloadable or shared audit must represent an actual server-generated review, respect account isolation and source retention, and avoid exposing original uploads. Cross-document answers must retain source identity while keeping provider prompts bounded. Review-priority colors must not imply verified legal safety.

## Decision

Save the latest successful audit alongside its document. Render PDF from that saved object with ReportLab 5.0.1, embedded font and escaped paragraphs. Keep PDF generation local and under existing admission limits. Explicit Unicode escapes expose glyph limitations rather than silently losing source characters.

Use PostgreSQL for production-only immutable share snapshots. Generate 32 random bytes, persist only a token hash, cap active links at ten per document, cap link expiry by document expiry, and join the live document on every public fetch. Serialize creation/revocation through the document row lock. Use a URL fragment and POST-body read endpoint to reduce accidental token exposure in path/referrer logs. Revoke all links rather than adding another token-management interface. Deletion cascades to snapshots; a non-ready tombstone denies access before physical deletion finishes.

Owner-check all selected documents before cross-document retrieval and again before returning the answer. Retrieve at most two excerpts from each of two to five selected documents. Prompt with stable selection-order labels, locally redacted text and untrusted-data delimiters. Validate returned citation IDs against available excerpts and preserve document IDs/filenames only in the source mapping. This is partial evidence, not an exhaustive multi-document audit.

Render a text-labelled heatmap of the existing deterministic clause rubric, with counts and coverage. Missing extracted clauses remain unassessed. Restore saved audits when opening documents; browser persistence remains metadata-only.

## Consequences

A holder can copy sensitive audit quotations. No revocation system can erase an already viewed copy. Snapshots intentionally do not update after new audits. Local unauthenticated mode cannot create public links. Original sources remain private. Shared pages clear at advertised expiry but do not poll for revocation. Expired rows can remain until source cleanup or another share creation; authorization never relies on physical cleanup alone.

PDFs have limited non-Latin typography. Client download/account-change guards cannot remove downloads completed earlier. Workspace top-two sampling can omit relevant clauses and its citation validation checks structure, not entailment. Real provider accuracy, hosted service configuration, production p95/cost and memory sizing require separate evidence.

## Alternatives

Client-supplied report JSON would permit misleading exports. Public document IDs would expose broader data. Long-lived signed object URLs would make immediate revocation harder. A full five-document audit per question would increase latency, tokens and failure exposure. A distributed PDF renderer or browser-based print service would add deployment and memory overhead without serving the current bounded reports.
