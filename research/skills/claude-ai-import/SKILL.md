---
name: claude-ai-import
description: >
  Import a claude.ai chat or project into local files (read-only): transcript.md plus
  assets/ with attachments, artifacts, produced files and tool images, so a local agent
  session can pick up where the chat left off. Trigger on "import this claude.ai chat",
  "pull this chat", "continue the claude.ai conversation here", or a claude.ai/chat or
  claude.ai/project link the user wants carried into the session.
metadata:
  requires: "uv"
---

# Import a claude.ai chat or project

Read-only: the script sends GET requests only and has no write path. It attaches over CDP
(the Chrome DevTools port) to a browser that is already logged in to claude.ai, opens its
own background tab and closes it at the end. It never launches a browser, never types
credentials and never opens a foreground tab, so other tabs and your focus stay alone.

## Run

```bash
uv run --with playwright python scripts/claude_ai_import.py chat    <url|id> <out-dir>
uv run --with playwright python scripts/claude_ai_import.py project <url|id> <out-dir>
```

- The port is `--port=N` or `CLAUDE_CDP_PORT`, default 9333. Use the project's own rule
  for which browser holds the claude.ai login; not logged in → the script stops with a
  message, and the login is the owner's to do.
- A chat's `<out-dir>` holds `transcript.md` and `assets/`. A project's holds
  `instructions.md`, `knowledge/` and `chats/<name>-<id8>/`, one chat folder (with its own
  `transcript.md` and `assets/`) each.
- It prints one JSON line of counts (messages, assets, failed downloads). Files that could
  not be downloaded are listed at the end of the transcript, never skipped silently.
- A chat's other branches (edited messages) are counted but not rendered: the transcript
  follows the branch the chat ended on.
- Chats are private. Write the output outside any repo, or into a folder that is not
  committed.

`scripts/claude_ai_import.py self-test` parses a made-up chat with no network or browser;
`test/test_import.py` runs it under pytest.

## What the API gives (checked against a live chat)

- `GET /api/organizations` → org id (the one with the `chat` capability).
- `GET /api/organizations/<org>/chat_conversations/<id>?tree=True&rendering_mode=messages&render_all_tools=true`
  → every message with `content` blocks `text`, `thinking`, `tool_use`, `tool_result`.
  Without `render_all_tools=true` tool calls are missing; `rendering_mode=raw` is worse
  (tool blocks become placeholder text).
- `GET /api/organizations/<org>/files/<file-uuid>/contents` → the file's bytes, for all
  of: message `files` (user and produced), tool-result images (`file_uuid` in the result
  content) and `file_deliveries` (STLs, PNGs, zips the assistant sent). `.../preview` and
  `.../thumbnail` exist only for images; `.../download` is 404.
- Thinking text is not returned, only step `summaries`; the transcript keeps those.
- Attachments carry their text inline (`extracted_content`).
- Projects: `GET .../projects` (list), `.../projects/<id>` (name, description,
  `prompt_template` = instructions), `.../projects/<id>/conversations`, `.../docs`,
  `.../files`. `docs` and `files` answered `[]` on the account probed, so the field names
  the script reads from their items (`file_name`, `content`, `file_uuid`) are unverified.
- Artifacts: the script saves a `tool_use` named `artifacts` whose input has `content`
  and applies later `old_str`/`new_str` updates to it; not observed in a real chat yet.

## Extending

All network access sits in `Fetcher` (`get_json`, `get_bytes`). A later write path adds a
method there; the rendering code does not change.
