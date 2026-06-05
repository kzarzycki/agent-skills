Local multi-dimension code review of the working-tree diff against {{BASE}}.
Run `git diff {{BASE}}...HEAD` for the net change. Honor these project rules:
{{RULES_BUNDLE}}

Five reviewers (run as a panel), each returning findings with a flag reason:
1. CLAUDE.md adherence — violations of the rules bundle above.
2. Bug scan — logic errors, missing cases, broken types introduced by the diff.
3. Git-history context — issues visible from blame/history of the touched lines.
4. Prior-PR-comment compliance — recurring review points from past PRs on these files.
5. Code-comment compliance — changes that contradict guidance in nearby comments.

Score each finding 0-100 for confidence it is a REAL, must-fix issue (not a
pre-existing issue, not a nitpick a linter would catch, not a false positive).
Return only findings scored >= 80, each with file, line, description (concrete fix), confidence.

To replace this phase with an external reviewer: rewrite this file to invoke it
and map its output onto { findings: [{file, line, severity, desc, confidence}], verdict }.
