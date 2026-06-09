# Playbook — interviewing in HTML

When you need a lot of structured information, a chat Q&A is slow and lossy:
questions scroll away, the user can't see the whole shape, answers arrive
piecemeal. A single HTML form fixes all three — the user sees every question at
once, answers in any order, and hands it all back in one paste.

## Channel check

Use a form only for **>~3 pieces of structured info** (intake, brief,
requirements, onboarding, config). For 1-3 quick choices, use `AskUserQuestion`
rounds — don't build a form.

## The two-way problem → copy-paste-back

A standalone `.html` file can't POST answers back to the agent (the browser tab
has no link to the chat). So:

1. The form gathers answers **in the browser**.
2. `../assets/copy-back.js` serializes them into a fenced token and shows a
   sticky **"Copy answers"** panel (disabled until required fields are filled).
3. The user clicks copy and **pastes the token into the chat**.
4. You parse it — it's wrapped in `ANSWERS<<< … >>>ANSWERS` — and continue.

**Fallback:** no browser / can't render → batched `AskUserQuestion` rounds (3-4
each). Offer the form; degrade gracefully, never trap the user.

**Optional escalation — served two-way mode:** if a local server *is* reachable
from the user's browser (rare on Claude Code web; common on local CLI), you can
skip the paste: serve the form, capture submits as JSON lines, read them
directly. This is the superpowers "visual companion" pattern. More seamless,
more setup — keep copy-paste-back as the default.

## Build steps

1. **Design the questionnaire before the HTML.** Every field must change what
   you do next; if an answer wouldn't, cut it.
2. **Group into sections** (`<h2>`) so the form has shape.
3. **Right input per question** (see `../assets/form-template.html`):
   short fact → `input`; one-of-many → radio choice cards or `<select>` if >6;
   many-of-many → checkbox cards; open-ended → `<textarea>`; amount → `range`.
   Always add an **"Other / not sure"** escape on constrained questions.
4. **Inline help** (`.help`) exposing the tradeoff or what you'll do with it.
5. **Pre-fill smart defaults** so the user edits rather than authors; label them.
6. Mark required fields → `CopyBack.init({ required: [...] })`.
7. Inline the CSS + copy-back.js, write the `.html`, surface it, and tell the
   user: *fill it in, click Copy, paste back here.*

## After the paste-back

- Parse the JSON inside the `ANSWERS<<< … >>>ANSWERS` fence.
- **Reflect a 3-5 bullet recap** of what you heard before acting (catches a
  mis-paste or misread).
- If a required field is still blank, ask only for that — don't re-send the form.
