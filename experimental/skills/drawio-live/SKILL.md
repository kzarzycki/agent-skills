---
name: drawio-live
description: Use when working on a drawio diagram with a user who views or edits it in a browser — remote/SSH sessions, "let's collaborate on the diagram", "open it in my browser", live review of diagram changes — or whenever the drawio skill is active and the user cannot open local files. Overlay on the drawio skill; check this BEFORE building any export-and-show review loop.
---

# Drawio Live

## Overview

Real-time co-editing of a `.drawio` file: the user edits in a browser (self-hosted
drawio editor in embed mode), every change autosaves through a bridge server into the
file on disk; when the agent edits the file, the user's editor reloads it within ~2 s.
One shared file, no git, no cloud.

```
browser (drawio iframe, embed=1&proto=json)
   ⇅ postMessage: init/load/autosave        [scripts/index.html host page]
bridge server  ⇄  the .drawio file on disk  [scripts/server.py]
   ⇡ agent edits the file directly; page polls /version and reloads
```

## Overlay on the drawio skill

The drawio skill still owns authoring: XML structure, styles, layout rules,
diagram-type presets, `validate.py`. This skill replaces its delivery/review loop
(steps 4–7: preview PNG → vision self-check → show user → final export):

- The user's live editor IS the review loop. Do not export a PNG per edit round.
- Export PNG/SVG (drawio skill step 7) only when the user asks for a deliverable.
- Vision self-check is optional; use it only for large layout changes you cannot
  judge from XML (export a preview PNG without `-e`, as the drawio skill specifies).

## Is the stack running?

The bridge binds the Tailscale IP, not localhost. Check:

```bash
IP=$(hostname -I | tr ' ' '\n' | grep -m1 '^100\.')   # Tailscale 100.64/10
curl -s http://$IP:8765/version    # {"etag":..., "file": "/path/served.drawio"}
```

`file` tells you WHICH diagram this bridge serves — verify it is yours (a host can
run several bridges on different ports; `pgrep -af server.py` lists them all).
If it responds and serves your file: give the user `http://$IP:8765/` and start
editing. Otherwise read [references/setup.md](references/setup.md) (one docker
container + one python script; no other deps).

## Live-editing rules

1. **Re-read the file before every edit.** Each user autosave rewrites the whole
   file canonicalized: attribute order changes, `host=` changes, new cells get
   numeric ids. Your in-context copy is stale the moment the user touches the
   canvas; an Edit-tool "file modified since read" error here is normal, not a bug.
2. **Batch your edits, then write once.** Every write reloads the user's editor and
   resets their zoom/selection. N small writes = N disruptions.
3. **Don't write while the user is drawing.** Last write wins on the whole file.
   Announce big pushes; if in doubt, ask them to pause for a second.
4. **New cells: unique string ids** (e.g. `claude-note-3`), never bare numbers —
   the editor assigns numeric ids and will collide.
5. **Run the drawio skill's `validate.py` after each edit batch.** A malformed file
   load-loops the user's editor. If the drawio skill isn't loaded:
   `find ~/.claude/plugins/cache -path '*drawio-skill/scripts/validate.py'`.
6. **To see what the user changed**: keep `/tmp/drawio-live/last-seen.drawio` —
   refresh it (`mkdir -p /tmp/drawio-live && cp <file> ...`) every time you read or
   write the file, diff against it when the user says "look". `git diff` only works
   if the file is tracked.
7. **diff does not arm the Edit tool.** Only Read refreshes the Edit tool's
   file-state; diffing against last-seen (even when identical) does not. If the
   file's mtime moved since your last Read, Read again (a slice is enough) right
   before an Edit batch — otherwise the whole batch fails with "modified since
   read" and you re-read anyway, at full price.

## Common mistakes

| Mistake | Reality |
|---|---|
| Using the embed `merge` action to push agent edits | `merge` does not apply value/label changes to existing cells. The host page uses `load`; keep it that way. |
| Syncing via git commits or Google Drive | Rejected baseline: not real-time, and Drive MCP can create but not update files. The file on disk is the single source of truth. |
| Binding servers to `0.0.0.0` | The host may have a public IP. Bind the Tailscale IP (100.64/10) — `server.py` autodetects it. |
| `pkill -f` to stop the bridge | The pattern matches your own shell's command line and kills it. Use the background-task id or `kill <pid>`. |
| Port already in use on 8080/8765 | Something else owns it; pick another port (`ss -tlnp | grep <port>`), don't kill the owner. |
| Expecting your XML formatting to survive | The editor canonicalizes on every autosave. Never byte-compare; compare cells/values. |
| Treating every autosave as a user edit | The editor autosaves on pan/zoom too (dx/dy live in the XML). Diff filters the noise; the bridge skips identical-content POSTs so they don't touch mtime. |
