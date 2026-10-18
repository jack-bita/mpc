---
name: start-task
description: Start one build-plan task from its card in docs/04-build-plan.md — check it is Ready, then plan it in small steps that each end in a commit. Only when Jack types /start-task <ID>.
argument-hint: <task ID, e.g. CORE-2>
disable-model-invocation: true
---

# Start task $ARGUMENTS

Current branch: !`git branch --show-current`
Uncommitted changes: !`git status --short`

Work through these steps in order. Explain each finding to Jack in one or two plain sentences.

1. **Find the card.** It is the heading `### $ARGUMENTS ·` in `docs/04-build-plan.md`. If the task is only a one-line table row, stop: say its card must be written first (BP2) and offer to draft one for Jack to approve.
2. **Check it is Ready** (04 §3.2):
   - every task in **after** is merged — `gh issue list --state closed --search "<ID> in:title"` for each one; if `gh` isn't available, ask Jack;
   - every **needs** answer from the owner is in, or a default is agreed;
   - it fits one sitting (`S` 1–2 h, `M` 2–4 h).
   If any check fails, say which one and stop.
3. **Check the branch.** It must be the branch named on the card, made from an up-to-date `main`, with no stray changes. If not, give Jack the exact commands from 04 §3.4, steps 1–2, and wait.
4. **Read what the card points to:** the ADRs and doc sections it names, and the `.claude/rules/` file for each area it touches.
5. **Jack-led cards:** give the 15-minute drill on the card's **Learn** line first — a short explanation, one tiny example, then two or three questions for Jack. Wait for his answers and correct them kindly before planning.
6. **Plan** in small steps. For each step: what changes, which test proves it, and its commit — the subject line (follow the card's **Commits**) and the `Why:` line giving a strong reason. On Jack-led cards, mark the steps where Jack writes the code. Remind Jack that each commit will wait for his yes.
7. **End the plan** with the card's *Done when* list. Write no code until Jack approves the plan.
