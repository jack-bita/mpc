---
paths:
  - "docs/**"
  - "README.md"
  - "CLAUDE.md"
---

# Docs and decisions

<!-- Source: ADR-0000; 04 §3.2 Done #9, §19. Loads when Claude reads or edits the docs. -->

- An accepted ADR is never rewritten. A changed decision is a new ADR (the next number, from `docs/adr/template.md`) that supersedes the old one: set the old one's `status: superseded` with a link, add the new row to `docs/adr/README.md`, and update 02, 03 or 04 in the same `docs:` commit. Typos and broken links may be fixed in place.
- Each planning doc carries a version and a "Changes in vX" line; bump them when the meaning changes.
- Plain English, short sentences; define a term the first time; Swahili UI words as in 02 §21.
- Public docs hold no real shop data and no secrets, and talk about this project only.
- Spike reports go in `docs/spikes/`, runbooks in `docs/runbooks/`, portfolio write-ups in `docs/writeups/`.
