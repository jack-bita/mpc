---
status: accepted
date: 2026-10-18
source: "03-architecture.md §2 — AD11"
standing: decided
cost-to-change: low
---

# ADR-0025 · The API contract is generated

## Context

The backend and frontend are written in two languages by one developer; they can drift apart silently.

## Decision

DRF → OpenAPI schema (drf-spectacular) → TypeScript types (openapi-typescript) and a typed client (openapi-fetch). CI fails if the schema or the types are out of date. Generated files are never edited by hand.

## Consequences

- **Good:** Type errors at build time instead of surprises at run time.
- **Cost:** One regeneration step after each API change (`pnpm gen:api`).

## Alternatives considered

- **Hand-written TypeScript types** — they drift silently.
- **GraphQL with generated types** — also typed, but a second API style; REST suits DRF and the sync endpoints.

## Enforced by

- CORE-6: the schema builds with no warnings.
- UI-2: `pnpm gen:api` and a CI step that fails on any difference.
- The Claude Code guard refuses edits to `frontend/src/api/schema.d.ts`.

## Related

- [ADR-0032](0032-ui-text-lives-in-the-app-the-api-sends-codes.md) · UI text lives in the app; the API sends codes
- [ADR-0024](0024-exact-numbers-everywhere.md) · Exact numbers everywhere
- Docs: 03 §5.10, §12
