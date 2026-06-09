# Platform gotchas (Claude Code web & desktop)

Hard-won notes on how HTML artifacts actually behave on Claude Code surfaces.
Read before promising the user something the client won't do.

1. **Surfaced files download — they never render inline.** `SendUserFile` (web,
   desktop, mobile) hands the file to the client as a download/attachment; no
   Claude Code surface renders agent HTML inline (it's a coding client, not the
   claude.ai Artifacts renderer, and serving untrusted HTML on-origin is an XSS
   risk). Self-contained files render fine once opened via `file://`. Zero-friction
   path: a local or `--teleport`ed session, then `open <file>.html`. Always print
   the absolute path alongside surfacing the file.

2. **AskUserQuestion HTML previews don't render on Claude Code.** The per-option
   `preview` field is an Agent SDK feature gated on
   `toolConfig.askUserQuestion.previewFormat: "html"`. Claude Code's web/desktop
   clients drop it and show only `label` + `description`. So labels/descriptions
   must stand on their own; for genuinely visual choices use a Channel B gallery
   file, not in-chat previews.

3. **Mobile: keep sticky panels thin; never put a big `<textarea>` in the scroll
   path.** A full-width textarea covers the viewport and swallows swipe-scroll
   (it scrolls its own content one line at a time). The copy-back panel is a slim
   stripe with the token collapsed behind a toggle.

4. **The async clipboard API is blocked on `file://`.** `navigator.clipboard`
   often fails for double-clicked local files; `copy-back.js` falls back to
   reveal-select-`execCommand`, and worst case the user copies the token by hand.

5. **Wide tables break vertical scroll on mobile unless wrapped.** Put every
   `<table>` inside `<div class="table-wrap">` (`overflow-x: auto`).
