# Chief-of-staff console spike

Throwaway proof for `docs/superpowers/specs/2026-10-20-chief-of-staff-console-design.md`. Not loaded by any plugin; not for merge as is.

- `status_snapshot.py <board> <status.json> [status.html]`: the shared status file (`cos-status/1`) built from a board's Live leads table plus Omnigent's live session state; read-only on Omnigent. Set `COS_UI_BASE` to the web UI's `/c/` prefix to get session links.
- `mod/`: a Claude Code mod (`claude --plugin-dir mod`). A status line and a `/leads` pane from the status file, with a stale warning; a `prompt.submit` hook that drops routine `Supervisor:` notices with no model turn, sends unclear ones to a small model (`$.model.complete`, default `haiku`), and hands escalated ones and the next owner message what it handled. `claude plugin validate mod`, `claude plugin test mod`.
