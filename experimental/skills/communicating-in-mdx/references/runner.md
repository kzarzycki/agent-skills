# The runner

A Vite + React app bundled at `runner/`. It renders `.mdx` from any directory
locally — zero network calls.

## Install (once)

```bash
cd <skill>/runner && npm install
```

## Run

```bash
node <skill>/runner/bin/mdx-runner.mjs --dir <project>/.work --open
```

Serves every `.mdx` under `--dir` at `http://localhost:5173` with a sidebar
index and hot reload. Edit a `.mdx`, the browser updates.

### Flags

| Flag | Effect |
|---|---|
| `--dir <path>` | Directory of `.mdx` to serve. Default: `.work/` if present in cwd, else `docs/`, else cwd. |
| `--open` | Open the browser on start. |
| `--port <n>` | Override port (default 5173). |
| `--check` | Resolve the dir, create the `.docs` symlink, print the path, and exit 0 — no server. For headless verification. |

## How it finds docs

The CLI creates a `.docs` symlink in the runner root pointing at `--dir`, and
sets `MDX_DOCS_DIR` so Vite's `server.fs.allow` admits that path. The app globs
`../.docs/**/*.mdx`. The symlink is git-ignored and refreshed on each run.

## Lifecycle — run it in the background

Start it as a detached background process so it survives across turns. The agent
launches it directly (e.g. a backgrounded shell command) and starts/stops/
restarts it autonomously — no tmux required:

```bash
node <skill>/runner/bin/mdx-runner.mjs --dir <project>/.work > /tmp/mdx-runner.log 2>&1 &
```

Restart after dependency changes: kill the process and relaunch.

**tmux (optional).** If the user wants a window they can attach to and watch:

```bash
tmux new-window -t mdx-runner -n server \
  'node <skill>/runner/bin/mdx-runner.mjs --dir <project>/.work'
```

**One runner at a time.** The CLI points a single shared `.docs` symlink at
`--dir`, so launching a second runner for a different directory repoints the
first. Run one instance; restart it with a new `--dir` to switch projects.

## Troubleshooting

- **Port in use** — pass `--port`, or kill the stale process on 5173.
- **Stale `.docs` symlink** — harmless; the next run replaces it. Delete
  `runner/.docs` to reset manually.
- **"not allowed" / blocked file** — Vite is refusing a path outside
  `fs.allow`. Confirm you launched via the CLI (it sets `MDX_DOCS_DIR`); running
  `vite` directly skips that.
- **Blank doc list** — the `--dir` has no `.mdx` files, or you pointed at the
  wrong directory.
