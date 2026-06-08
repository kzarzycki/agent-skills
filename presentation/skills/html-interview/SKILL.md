---
name: html-interview
description: >
  Interview the user through a real HTML form instead of back-and-forth chat
  Q&A — grouped sections, the right input per question (text, select, radio
  cards, checkboxes, sliders), inline help, and required-field validation. The
  page collects everything in one pass and produces a copy-paste-back token the
  user drops into the chat. Use when you need to gather more than ~3 pieces of
  structured information: intake, onboarding, a brief, requirements, a
  questionnaire, a config, preferences, or scoping a project. Trigger on
  "interview me", "ask me a bunch of questions", "intake form", "gather
  requirements", "fill out a brief", "onboard me", "questionnaire", "collect my
  preferences", or any multi-field information-gathering where a form beats a
  chat interrogation. Output is one self-contained .html form.
---

# HTML Interview — gather input through a form, not an interrogation

When you need a lot of structured information from the user, a chat Q&A is slow
and lossy: questions scroll away, the user can't see the whole shape, answers
arrive piecemeal. A single HTML form fixes all three — the user sees every
question at once, answers in any order, and hands it all back in one paste.

## Channel check first

Read `../../references/when-html.md` — the shared "HTML vs Markdown" doctrine.
An HTML form is the *interaction* case: the user will fill something in. That's
squarely where HTML beats a chat interrogation — but only past ~3 fields; below
that, `AskUserQuestion` is lighter.

## When to fire

You need **more than ~3 pieces of structured information** before you can
proceed: intake, a creative/product brief, requirements, onboarding, a config,
preferences, scoping. For **1-3 quick choices**, just use `AskUserQuestion`
rounds — don't build a form for that.

Sibling skills: **html-options** (pick among rich visual choices),
**html-report** (write findings back up). Shared design system at
`../../assets/design-system.css`.

## The two-way problem and how this solves it

A standalone `.html` file can't POST answers back to you. So:

1. The form gathers answers **in the browser**.
2. `../../assets/copy-back.js` serializes them into a fenced token and shows a
   sticky **"Copy answers"** panel (disabled until required fields are filled).
3. The user clicks copy and **pastes the token into the chat**.
4. You parse the token (it's wrapped in `ANSWERS<<< … >>>ANSWERS`) and continue.

**Fallback:** if the user can't open a browser (pure terminal, no file
surfacing), don't force it — fall back to batched `AskUserQuestion` rounds
(3-4 questions each). Offer the form; degrade gracefully.

## Build steps

1. **Design the questionnaire before the HTML.** List the fields you actually
   need. Every field must change what you do next — if an answer wouldn't change
   your output, cut it (same discipline as good clarifying questions).
2. **Group into sections** (`<h2>`) so the form has shape, not a flat wall.
3. **Pick the right input per question** — see `references/form-template.html`:
   - short fact → `input[type=text/email/number]`
   - one-of-many → radio **choice cards** (`.choice`) or `<select>` if >6 options
   - many-of-many → checkbox choice cards
   - open-ended → `<textarea>`
   - amount/scale → `input[type=range]` with a live value
   - Always add an **"Other / not sure"** escape where a fixed list might not fit.
4. **Add inline help** (`.help`) exposing the tradeoff or what you'll do with it —
   the user shouldn't have to ask what a question means.
5. **Mark required fields** and pass their keys to `CopyBack.init({ required: [...] })`.
6. **Inline** the design system CSS and copy-back.js, write the `.html`, surface
   it, and tell the user: *fill it in, click Copy, paste back here.*

## Question design (carry over from good interviewing)

- **Batch, don't drip.** The whole point is one pass — put every question on the page.
- **Each option carries a label *and* a one-line description** of the tradeoff,
  not a bare label.
- **Pre-fill smart defaults** where you can guess, so the user edits rather than
  authors. Mark them as defaults in the help text.
- **Order sections shape-changing first:** what-is-it / scope → semantics →
  preferences → nice-to-haves.
- **Keep it to one screen-ful per section.** If a section has >8 fields, split it.

## After the paste-back

- Parse the JSON inside the `ANSWERS<<< … >>>ANSWERS` fence.
- **Reflect a 3-5 bullet recap** of what you heard before acting, so the user
  can catch a mis-paste or a misread.
- If required answers are still blank (user edited the token), ask just for
  those — don't re-send the whole form.

## Anti-patterns

- Building a form for 1-3 questions (use `AskUserQuestion`).
- Free-text everything — give structured inputs so answers come back clean.
- No required-field validation — you'll get half-empty tokens.
- Forgetting the escape hatch ("Other / not sure") on constrained questions.
- Asking questions whose answers don't change your output.
- Re-sending the entire form when only one field is missing.
