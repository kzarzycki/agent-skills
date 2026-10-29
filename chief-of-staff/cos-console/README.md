# cos-console

An optional Claude Code mod for a chief-of-staff (CoS) session. It reads what the supervisor writes under `--console` and puts it in front of the CoS, so "how's it going?" costs no tool calls.

- **Status line:** `cos: leads 5: 3 running, 1 blocked, 0 failed`. It shows `cos: STALE <n>s` when the state file is more than 120 s old, and `cos: no state file` when it cannot be read.
- **`/leads`:** every live lead's title and status line, in a pane.
- **Owner messages:** each one gets every live lead's status line, plus the supervisor's events since the previous owner message, attached as context. A message starting with `Supervisor` or `/` passes through untouched. If either file is broken, the message goes through without the digest. The mod drops nothing and does no routing.

## What it reads

The supervisor, run with `--console` on a registry, writes two files beside that registry:

- `<registry stem>.state.json`: schema `cos-state/1`, one entry per lead with `title`, `state` and `label: {line, at}`.
- `<registry stem>.events.jsonl`: one event per line, each with `at` (seconds) and `line`.

The `registry` option names the registry. Its default is `leads.registry`, relative to the session's folder. The two files' types are in `types/index.d.ts`.

## Enable it in the CoS home only

Enable it in the CoS home's project settings and nowhere else, so it loads only in sessions started there. In `<CoS home>/.claude/settings.json`:

```json
{
  "enabledPlugins": { "cos-console@kzarzycki-agent-skills": true }
}
```

This needs the `kzarzycki-agent-skills` marketplace added (`/plugin marketplace add kzarzycki/agent-skills`).

## Check it

```sh
claude plugin validate cos-console
claude plugin test cos-console
```
