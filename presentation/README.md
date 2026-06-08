# presentation

Make the agent communicate in **HTML instead of Markdown** when a rendered page
beats a chat dump — for reports, for interviewing the user, and for offering
choices. Three skills over one small, dependency-free design system.

| Skill | Use it when | Output |
|---|---|---|
| **html-report** | The user wants a report / summary / analysis / dashboard / scorecard with structure, tables, and visuals. | One self-contained `.html`: KPI cards, tables, inline-SVG charts, callouts. Opens offline. |
| **html-interview** | You need >~3 pieces of structured info: intake, brief, requirements, onboarding, config. | One `.html` form (right input per question, validation) that emits a copy-paste-back token. |
| **html-options** | You're offering a choice between approaches, layouts, designs, or color schemes. | Native `AskUserQuestion` HTML previews for compact picks, or a standalone side-by-side gallery. |

## How HTML reaches the user

Everything is a **single self-contained `.html` file** — design system CSS and
any JS inlined, system fonts, inline SVG charts. No CDN, no build, no server; it
opens by double-click, offline. The agent writes the file and surfaces it (e.g.
`SendUserFile` on Claude Code web/mobile, or prints the path).

A static file can't POST back to the agent, so the two interactive skills use a
**copy-paste-back token**: the page collects input in the browser, shows a
sticky "Copy answers" button (disabled until required fields are filled), and
the user pastes the fenced `ANSWERS<<< … >>>ANSWERS` token into the chat. When
no browser is available, both skills degrade to batched `AskUserQuestion` rounds.

## Shared assets

- `assets/design-system.css` — tokens + components (cards, KPI, tables, badges,
  callouts, form fields, choice/option cards, copy-back panel). Dark + light.
- `assets/base-template.html` — page skeleton to start from.
- `assets/copy-back.js` — turns a static page into a one-paste channel back to the agent.

Inline these into each generated file; don't ship multi-file output — it won't travel.

## Install

```bash
# In Claude Code:
/plugin marketplace add kzarzycki/agent-skills
/plugin install presentation@kzarzycki-agent-skills
```
