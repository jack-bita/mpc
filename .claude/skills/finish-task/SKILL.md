---
name: finish-task
description: Finish the current task — run every check, review the branch against its card and CLAUDE.md, help Jack write "What I learned", and draft the pull request. Only when Jack types /finish-task.
disable-model-invocation: true
---

# Finish the task on this branch

Branch: !`git branch --show-current`
Commits on this branch: !`git log --oneline main..HEAD`
Files changed: !`git diff --stat main...HEAD`

1. **Run `make check`.** If anything fails, fix it first — each fix its own commit, with a `Why:` line and Jack's yes. Don't continue while a check is red.
2. **Done list.** Go through *Done means* in `CLAUDE.md` and the card's *Done when*. Mark each item ✓ or ✗ with its evidence — a test name, a command and its output.
3. **Fresh eyes.** Ask the `reviewer` subagent to review this branch. Fix what it finds, or tell Jack plainly why a finding doesn't apply.
4. **What I learned.** Ask Jack three short questions: *What was new to you? What surprised you? How would you explain the main idea in a job interview?* Turn his answers into 3–5 lines in his own words. Don't add learning he didn't say.
5. **Draft the PR.** The title is a conventional commit. The body follows the PR template: task ID and `Closes #…`, what and why, how it was tested, screenshots for screens, *What I learned*, the Done list, and the hours (ask Jack).
6. **Hand over.** Give Jack the commands to push and open the PR (04 §3.4, step 5). Don't push, open the PR or merge unless Jack asks you to.
