# Ticket templates

Issue bodies and milestone descriptions are read twice: by the owner, to accept the intent, and by an agent, to implement it. Human sections come first; implementer facts sit in a final section of their own. Same issue, two audiences, no mixing.

Voice: plain technical English, short sentences, bullets over lists-in-sentences, a term the reader may not know gets a short reminder in brackets the first time. No openers, no sentences about the text itself, no aphorisms. If the owner has a writing-style guide, it governs the voice; this file governs the structure.

Fixed sections, same titles, same order, every time. An empty section says "none" instead of disappearing — a missing section reads as forgotten.

Reference numbers (finding ids, other issues) always come with a plain phrase: *duplicate WebSocket connection (CH03)*.

Every path, symbol, command, load order or runtime behaviour written into a body is checked against the tree or observed first. If it can't be checked, write it as an open question together with what would settle it.

## Epic

```
Title field: Exx — <imperative summary> (<milestone>)   ← not repeated in the body

## Problem
Where (component, file) and when (trigger), then what goes wrong. Bullets for known causes. Link to the evidence.

## Scope
**In** — bullets.
**Out** — bullets, each with why it is out and where it lives instead.

## Rules for stories
Constraints every sub-issue inherits, each with its reason.

## Done when
Checklist. Each line is something a reviewer can check literally.

## Not now
What is deferred, why the risk is acceptable today, and what event makes it not acceptable.

## For the implementer
Paths, symbols, commands, environment facts, evidence format. Only what this epic needs beyond the project's contributor docs.
```

## Story, task, bug

```
Title field: Exx-yy · <imperative summary>   ← not repeated in the body

## Problem
Where and when, then what goes wrong. For a bug: what happened, what was expected, how to reproduce.

## Change
What becomes true after the change. Not how.

## Acceptance
Checklist, literally checkable. Includes the test that fails before the change and passes after.

## Proof
What evidence goes on the PR: unit test, live run log, screenshot, recording.

## For the implementer
Paths, symbols, related issues, and what not to touch here. Open questions together with what would settle them.
```

## Milestone description

Theme in one sentence; the outcome a user sees; the epics in it; exit criteria as a checklist; one sentence on why it sits at this point in the order.

## Pull request

A PR body describes the branch as it will be merged. Re-read it after every push that changes scope; a body that still describes a deleted file is a bug.

```
## Why
Link to the story or epic. One or two sentences on the problem, in plain words.

## What changed
Bullets by behaviour, not by file.

## Proof
What was run and what it showed: gates, unit tests, and live evidence (log, screenshot, recording) where the change depends on the real host.

## Not in this PR
What a reviewer might expect here but is deliberately elsewhere, and where.
```
