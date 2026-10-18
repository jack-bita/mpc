---
paths:
  - "backend/**/migrations/**"
---

# Migrations

<!-- Source: 03 §5.6, §9; 04 BP5. Loads when Claude reads or edits a migration. -->

- Read every generated migration line by line before committing it, and explain it to Jack in one sentence.
- A migration that is on `main` is never edited — write a new one. (The guard hook refuses the edit.)
- No `migrate` on any database before PPL-1 — the custom `User` — is merged (ADR-0012). (The guard hook refuses it.)
- Ledger and dated-rule tables get the append-only trigger operation from `core`; payments, money movements and attendance events get the void-stamp variant (ADR-0021).
- Rules the database can enforce go into the migration: check constraints, partial unique indexes, `PROTECT` foreign keys.
- A change old devices may still rely on goes "add the new → move over → remove the old", across releases.
- Global seed data (units) is a data migration. Role templates are not: they live in code and `create_shop` copies them into each shop.
- `makemigrations --check` must be clean before the PR.
