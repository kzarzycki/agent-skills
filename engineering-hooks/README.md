# engineering-hooks

The PreToolUse hooks on Bash that the `engineering` pack ships (`hooks/hooks-claude.json`): they refuse a heavy
test run in a host session with a cloud route, a command that prints the environment or a secret, and a `git push`
of a merge of the base into a PR that merges cleanly.

They are a package of their own because APM 0.36 and later send every hook file in a package to every target the
package serves, and refuse to install a package whose hooks would newly reach Codex. `engineering` serves both
agents for its skills, so its hooks live here, in a package whose `apm.yml` says `target: claude`: APM deploys them
into `.claude/` and no Codex file, on every APM from 0.30. A project installs `engineering`, which pulls this in;
it never names this package.

It is an APM package only, with no Claude Code plugin manifest and no marketplace entry: Claude Code never loaded
`hooks-claude.json` (it is not the plugin hook file's name), and a manifest makes apm 0.39 deploy the package as a
native plugin, which would skip `.claude/settings.json`, where these hooks belong.

The hook scripts run on the consumer's own `python3` (macOS ships 3.9).

## A missing script does not block Bash

Each command in `hooks/hooks-claude.json` checks that its script exists and, when it does not, prints one line to
stderr and exits 0; when it does, it runs the script and passes its exit code through, so a real block (exit 2) still
blocks. A PreToolUse hook that exits 2 blocks the call, and `python3 <missing file>` exits 2, so a bare command whose
file a package move deleted refused every Bash call.

`apm install` does not remove the entries a package wrote before it stopped shipping hooks (apm 0.39.1 leaves them
in `.claude/settings.json` and `.claude/apm-hooks.json`). A consumer that upgraded across the move from `engineering`
0.35.10 or earlier, to the release that moved the hooks here, still holds entries for
`.claude/hooks/engineering/hooks/*.py`: delete them from both files. Releases after the move put no such entry in a
consumer, because their commands skip a missing script.
