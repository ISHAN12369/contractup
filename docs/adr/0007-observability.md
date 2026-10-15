# ADR 0007: Metadata-only observability

Status: accepted for Phase 3, 12 October 2026.

Emit allowlisted JSON events with UTC time, sanitized route, request ID, status and duration. Request duration is measured until response headers; for SSE this is not total generation time. Provider spans measure the full call/stream duration. Content, tokens, arbitrary paths and library exception messages are excluded. Restrict infrastructure/proxy access logs separately: application filtering does not configure third-party infrastructure.

Langfuse and Sentry are opt-in (`TELEMETRY_ENABLED=true` plus credentials). Langfuse generation observations record configured model/provider, request correlation, measured duration and actual provider token usage when supplied. Configure the model's pricing in Langfuse for inferred cost; missing usage/pricing means cost is unavailable, not free. No prompt, answer, filename, source text or user identifier is exported. Sentry's automatic integrations, PII, request bodies and trace sampling are disabled; manual events are reconstructed from an allowlist of generic message, exception type and request ID. Shutdown flushes exporters without failing the application on exporter errors.

This sacrifices full prompt replay and rich exception stacks to reduce disclosure. Local formatting/scrubbing and SDK calls are tested; live dashboards require separately supplied accounts and must be checked with synthetic documents first. These integrations are not an audit ledger or a billing reconciliation system.

Reference: [Langfuse Python instrumentation](https://langfuse.com/docs/observability/sdk/instrumentation).
