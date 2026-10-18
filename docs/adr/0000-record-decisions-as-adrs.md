---
status: accepted
date: 2026-10-18
source: "portion 5 of the planning pack"
standing: decided
cost-to-change: low
---

# ADR-0000 · Record decisions as ADRs

## Context

The planning pack (`01`–`04`) holds 34 key decisions — D1–D14, AD1–AD18, BP7 and BP16 — inside long documents that keep changing. When a paragraph is edited, the reasons behind a decision get lost. Claude Code, a future teammate and a recruiter all need one short place per decision that says what was chosen, why, and what it costs.

## Decision

- One Markdown file per decision in `docs/adr/`, in a light MADR format (`template.md`): front matter, then Context, Decision, Consequences, Alternatives considered, Enforced by, Related.
- Numbered in source order: 0001–0014 = 02 D1–D14; 0015–0032 = 03 AD1–AD18; 0033 = 04 BP7; 0034 = 04 BP16. A new decision takes the next free number.
- **Standing:** `confirmed` = Jack confirmed it in chat; `decided` = agreed in the planning pack; `default` = best guess, safe to change while building (it carries a `revisit` line).
- An accepted ADR is never rewritten. A changed decision is a **new ADR that supersedes the old one**: the old one gets `status: superseded` and a link, and 02, 03 or 04 change in the same `docs:` commit. Typos and broken links may be fixed in place.
- The other build-plan decisions (BP1–BP6, BP8–BP15) are working rules in `CLAUDE.md` and `04-build-plan.md`, not ADRs; BP5 is covered by ADR-0012.

## Consequences

- **Good:** Every big choice keeps its reasons, even after the docs change.
- **Good:** Claude Code reads the ADR before changing what it covers; the reviewer checks changes against it.
- **Good:** A recruiter sees how the system was reasoned about, not only what was built.
- **Cost:** About 35 files to keep honest; superseding instead of editing takes discipline.

## Alternatives considered

- **Decisions only inside 02–04** — the status quo: reasons get edited away, and one decision is hard to link to.
- **One big `decisions.md`** — hard to link, and superseding one decision means editing a long shared file.
- **A wiki** — not versioned with the code, so it drifts from what the code does.

## Enforced by

- 04 §3.2 Done #9 and the *Done means* list in `CLAUDE.md`: a changed decision ships with its ADR.
- `.claude/rules/docs.md` loads whenever `docs/` is edited.
- The `reviewer` subagent checks each branch against the ADRs it touches.

## Related

- Docs: 04 §2 · 03 §0 · 02 §2
