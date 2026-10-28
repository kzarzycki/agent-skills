# Orchestrating with Omnigent

Start each worker or verifier with its own background command, whose exit wakes you; keep
working meanwhile:

```bash
python3 scripts/omnigent_agent.py run <claude|codex|AGENT> <title> <brief-file> <report-path> --role <role-file>
```

Run it from the worktree the child works in, because the script makes its current
directory the session's workspace; `--workspace <dir>` names another, such as the parent of
several repos for a lead whose change spans them. The report path goes in a gitignored directory of that
workspace (under the engineering loop, `tmp/loop/`): outside its workspace a Codex child's sandbox refuses the write and a Claude Code
child is prompted for a read (denied in auto mode), which nobody answers, so the script refuses
such a path. Titles look like `s120-parser-worker`,
`pr182-verifier-p1`: the issue or PR, then the role. The brief (a file, or the text itself, as
every brief and message argument here takes) holds only the task specifics; the script writes it, under a fixed preamble (owner-authorized imperative, the
role file, long runs started detached and polled, write the report to the path, reply with only
the path), to `<report>.brief` and sends the child one line naming the title and that file.
Omnigent labels a child in the UI by a summary of that line, not by its title, so a title
that names the issue or PR is what makes the label say what the child works on. Build the brief with a quoted heredoc
(`<<'EOF'`): an unquoted one runs each backticked name as a command, and the script
refuses a brief left with an empty `` `` `` span. Exit 0 prints the report path. Exit 1
prints the reason and the child's last message; for a session that failed, also its
`last_task_error` and its runner log. With a verifier's role file, the report
counts only once it has its `SATISFIED:` line, so a report written in stages does not end
the wait early. Any report counts only once the child's turn has ended and the file is
unchanged since, which takes 30 seconds out of its turn at every look (a session can read idle
mid-turn), and is read again before `run` returns it: until then a child can rewrite it (a
verifier revising its verdict). Omnigent can lose a turn end and leave the session
`running` (kzarzycki/omnigent#4), so a report that is quiet, with its session's history,
for 10 minutes counts too. The report path is the final report, written once at the end:
a child keeps progress in another file, since the first report the waiter takes is its
answer. A session is filed under the Omnigent project `OMNIGENT_PROJECT` names, else the
calling session's (its own, then its primary's), since a scheduled run is filed in its task's
project whatever its repo is called, else the project named like the repo, when one exists.
Names match loosely: case, spaces and punctuation don't count, so `voice_note` files under
"Voice note". An exact name wins, and two loose matches with no exact one fail until
`OMNIGENT_PROJECT` names one. A top-level session none of these finds is left unfiled, with a
stderr line saying so.

**Questions.** A child never asks the owner. It writes `<report>.question` and stops;
exit 3 prints that path. Answer from the spec and the owner's stated intent, or ask the
owner only when neither settles it, then run
`python3 scripts/omnigent_agent.py send <session> <answer-file> <report>` in the
background. It continues the same session while its cache is warm and waits as `run`
does; add `--verdict` when the child is a verifier, because `send` and `wait` are not
given the role. A child still in a turn gets the answer at its next tool boundary; until
then `send` reports it queued and waits, and a rerun of the same `send` waits for the
first copy instead of delivering a second. A report left from the earlier turn does not
end the wait: only one written after the send counts. A session whose runner Omnigent
reaped (idle over an hour) is revived in place first (`retry_session`, operating-omnigent
skill), keeping its conversation. Exit 4 means the revive failed or the answer did not
land: start a fresh run whose brief carries the question and the answer.

**Follow-ups** (a fix pass, a rebase) are a fresh run whose brief points at the earlier
report: after an idle hour the cache is cold, so the report is cheaper than the old
transcript. A `run` may reuse the report path: a report already there counts only once
rewritten after the launch. `start` refuses one, since the `wait` after it has no launch
time to compare.

**Model.** A child runs on `--model`, else `OMNIGENT_MODEL_<AGENT>` (`OMNIGENT_MODEL_CODEX`,
`OMNIGENT_MODEL_CLAUDE`), else its harness's default (Codex: `~/.codex/config.toml`), a
verifier included. `start` refuses a model the agent's harness doesn't list on the host the child runs on
(`GET /v1/hosts/<host>/harnesses/<harness>/model-options`: each row's `id` and `model`, so `sonnet` and
`claude-sonnet-5-5` both pass), naming the ids it does, and one it can't check because the list doesn't load:
Omnigent launches an unlisted id on the harness default with no error. Pass `--model` only when the owner asked for that model or the project's instructions
name it: a lead never picks one on its own, so the user's configuration decides model and cost in one place. A
tier the project names resolves against the family's lineup (engineering-loop SKILL.md, Models): Codex lists
its models in `~/.codex/models_cache.json`, each `slug` naming its generation and its `description` its role; a Claude Code
lead's own instructions name its family's newest models, and `sys_list_models` lists none for Claude. A
launch that fails on capacity (`server_overloaded`, a rate limit) is retried later with
backoff on the same model, never on another, which would leave the work on a model nobody
chose.

**Permission mode.** A Claude child starts in `--permission-mode <mode>`, else
`OMNIGENT_PERMISSION_MODE`, else the harness default; the mode is the project's or owner's
choice, set in the environment once. Omnigent applies it as the session's
`terminal_launch_args` when it launches the terminal, so `info` shows it. A Codex child takes
none: codex-native hands the flag to the `codex` CLI, whose terminal then never starts, so
`start` refuses the flag for Codex and ignores the variable.

**Other agents.** `claude` and `codex` are aliases for the native agents; any other registered
agent's name or id starts that agent, found among the server's agents, then the caller's own
(`scope=user`). `claude` and `codex` take the server's native agent, though the UI may register a
user copy of it. Several user agents can share a name, since each upload of one spec registers
another agent under it. When their records and configs (`GET /v1/agents/{id}/config`) match apart from
identity and bookkeeping (`id`, `version`, `created_at`, `updated_at`, `object`), the name starts the newest by `created_at`: copies of one spec can't be told
apart, and an agent record has no host (`--host` picks that per session), so an id in project
config would only be wrong on another server. Both are compared since each holds fields the other
lacks: the record policies, skills and terminals, the config instructions and model. When they
differ, or a server agent shares the name (only a user agent has a config to compare), the name
fails, listing their ids: pass the id. A native harness (`*-native`) runs in a pane on this host, so it reads its brief
from a file as the aliases do; any other may run its tools on another machine, so its brief goes
inline in the first message. `OMNIGENT_MODEL_<AGENT>` applies to the aliases only (`--model`
works for any), and so does permission mode, except Antigravity: it asks for approval of every
command, and its only other mode skips them all, so `start` refuses it a `--role` unless
`--permission-mode bypassPermissions` (or the variable) opts into that, which it launches with
`--dangerously-skip-permissions`. Antigravity's effort is the user's configuration: agy names it
in the model of its own settings (`Gemini 3.8 Flash (Low)`), which Omnigent copies into each
session, so the launcher passes none. An unknown name fails before a session is created.

**Cloud workers.** A worker whose tools run in a cloud VM can't write a file on this host,
so `run` and `start` take `--pr <n>`: the preamble then has it post its report as one comment
on PR n through REST (`gh api repos/{owner}/{repo}/issues/<n>/comments`, since GitHub's
GraphQL API, and so `gh pr comment`, answers 403 in the VM), naming no host, path or session,
and end its turn with only the comment's URL. A cloud session (harness `acp:claude-cloud`)
runs in the environment its workspace's untracked `.claude/settings.local.json` names in
`remote.defaultEnvironmentId`, so before creating one on this host `start` and `run` copy a
worktree's missing pin from its main checkout (keeping the file's other settings) and refuse
when neither has one. `wait` (and so `run`) with `--pr <n>` fetches
the comment on PR n that the turn's last message links (`gh api`) and writes its body to the
report path, so whatever reads the report reads a file as for any child. The worker pushes
only to the `claude/…` branch its session started on and names it, with its head SHA, in the
report; the lead merges that branch into the PR. A worker whose post fails (the session's token
expires after a while) replies with an `UNPOSTED REPORT` line and the body; `wait` posts that
body on PR n from this host and writes it to the report path. The VM's files never reach this
host either, so a file under `tmp/loop/` the report names (a repro, a log) rides in the comment
as a `<!-- file: tmp/loop/<name> -->` line and a fenced block (a file past GitHub's 65,536
characters goes as its last lines, marked so, and lands as `<name>.tail` with `<name>` listed
missing, since a cut repro would run as the whole one); `wait` writes each beside the report, never through a symlink,
prints where it landed, and lists as missing a named file the comment does not carry (even when
this host has one by that name, which may be another) or that can't be written here, with no
change to the exit code. A question goes in
that report, since `<report>.question` is a path here too. Only a comment GitHub files on
PR n of this checkout's repository (`gh repo view`, checked against the comment's
`issue_url`) counts, since the link is only what the worker typed: another PR's or another
repository's counts for nothing. The nudge asks for the comment, and a second turn ending
without one fails. `run` and `wait` finish a worker once its report is in, unless given
`--keep`: a fresh cloud session is a fresh VM, clone and build, while a kept one, even idle
past its VM's reclaim, revives on the next message with its clone and conversation, so a fix
round goes to it with `send --pr <n>`, else to a fresh `run --pr` (Follow-ups). A cloud
child that fails in setup, before its first turn (`cloud session setup failed` and no assistant
message), `run` starts once more in a fresh session with the same brief, and one that stalls
(`made no progress`, the bridge's `CLAUDE_CLOUD_STALL_TIMEOUT_S`) `wait` sends one continue
message; each is named on stderr, and a second of either fails, naming both. `send --pr <n>`
reaches a worker still open (kept, or one whose turn ended without a report), wherever its
workspace is, since the report is the file `wait` writes here, and takes only a comment
created after the report already there, so a turn that ends on the old comment's link, or on
none, gets the nudge and then fails. `--pr` arms no supervisor registry, since the supervisor reads the report file and
would revive and nudge the worker toward a path it can't write: re-attach a `run` that died
with `wait <session> <report> --pr <n>`. A `--role` path names the role file by its path in
the repo, since the VM has the checkout but not this host's paths. The preamble also tells the
worker two facts about the VM: its checkout is the branch checked out in the workspace the
session started from, not necessarily the PR's, and a foreground command stops at 10 minutes,
so a long one runs detached and is polled within the same turn. It forbids an interactive
question tool and a published page, since each waits on a prompt nobody in the cloud answers,
and ends each commit message with the co-author line and no session link, since the commit
reaches a public repository. A host without the cloud
harness starts the worker on one that has it, with `start --top-level --host <host> --pr <n>`
(Top-level leads, `--host`): `--pr` gives the PR preamble to a top-level session too.

**Author family.** `--author <claude|codex>` names the family that wrote what the child
reviews. When it matches the child's own family the script refuses unless `--same-family`
is given, so a reviewer of the author's family is always a deliberate choice. Whether a
reviewer must be of the other family is the caller's policy.

`start` and `wait <session> <report>` are the two halves, for a start whose wait runs
elsewhere.

**Signature.** `python3 scripts/omnigent_agent.py signature` prints `<harness>/<model>/<effort>` of the session it
runs in, read at runtime (Codex's rollout, Claude Code's `$CLAUDE_EFFORT` and transcript), so it holds
however the session started. It reads the session's Omnigent record first (`llm_model` once the harness has
reported it, and `reasoning_effort`), since a Codex child's rollout sits under a private `CODEX_HOME`. The
`AGENT_SIGNATURE=` line `start` puts atop a brief names the model the server took for the session (its
`model_override`, `?` for the harness default), never the id asked for.
Below it, a child on this host that is not a top-level lead gets `LOOP_HEAVY_LOCK=<path>`, one
lock per lead (the runner's primary session, which a lead's workers and their children share;
`$LOOP_HEAVY_LOCK` when the caller has it), so a lead's parallel workers
take one heavy slot between them (worker.md, Gates and push); a session gets no environment from
its starter, so the path rides in the brief.

**Waiting on a run or a PR.** `python3 scripts/omnigent_agent.py wait-for --log <log> [--pid
<n|file>]`, `--pid <n|file>` or `--pr N [--until checks|merged|closed]` blocks up to `--budget`
seconds (default 570, under a 10-minute tool call), printing nothing until it ends: on the log's
`exit <n>` line with that code, the line before it and, on red, the last 30 lines (with `--pid`,
only a log written since that run started, since a reused log path still holds the previous run's
line); on the pid gone; on the PR's condition settled (red checks named, exit 1); else `still running`, exit 6.
It needs no session, so it serves every backend. Its `--notify` runs `$LOOP_NOTIFY <outcome>`
once the run ends, as a merge queue tells a lane, so a detached run's wrapper ends with
`omnigent_agent.py wait-for --log <log> --notify` and the session that set `LOOP_NOTIFY="python3
<this skill>/scripts/omnigent_agent.py relay --from gate <its session id>"` gets one message
when it ends; unset, nothing is sent.

**Waiting on a condition.** `python3 scripts/omnigent_agent.py wait-until --every <s> --limit
<s> -- <cmd>` runs `<cmd>` (no shell unless it is one) every `--every` seconds, at most 60 so
each sleep stays short of any tool timeout, and exits 0 once it exits 0, or 6 once `--limit`
passes; keep a call's `--limit` under the harness's tool timeout, so the call returns rather
than being cut off, and call it again while the budget lasts.

**Host capacity.** `python3 scripts/omnigent_agent.py capacity` prints this host's idle CPU
share over about a second and its available memory, and exits 0 when it has room for another
session, 1 when not. It reads idle CPU, not the load average, which on macOS also counts threads
waiting on I/O and memory and reads several times too high; load per core decides only when idle
cannot be measured. `start` and `run` wait while it has none, except for a session `--host` puts
on another host, whose load lands there, printing a line, and fail after
`OMNIGENT_CAPACITY_WAIT_SECONDS` (default 600), since sessions on an overloaded host time out and
fail; a queue that would rather wait sets it longer. The limits are knobs set for the hardware:
`OMNIGENT_MIN_CPU_IDLE` (percent, default 10), `OMNIGENT_MAX_LOAD_PER_CORE` (default 4, the
fallback) and `OMNIGENT_MIN_AVAILABLE_MB` (default 1536). A
message `start`, `send` or `relay` posts is not failed when its POST times out on a slow
server: the history decides whether it landed, within `--confirm-seconds`. The supervisor's
own posts, which read no history, still count a timeout as a failure and try again.
`relay`, `send`, `status` and `report` take a session id or a unique prefix of one (the six
characters other tools print), looked up among every session you can see, archived ones
included; a prefix several sessions share fails, listing them.

**A child that leaves its tree dirty fails the wait.** When a child on this host reports, `run`
and `wait` fail, naming each path, while its workspace has a tracked change (`git status
--porcelain --untracked-files=no`, with each file's content hash, so a further edit to a file
already changed shows) that was not there when `run` started it or `send` sent it its
follow-up; a standalone `wait` has no start listing, so any tracked change counts. The failure
says the change may be another edit in that tree since the child started, a lead's own in a
shared worktree among them. Untracked files (a verifier's
repros, gate staging) don't count, nor does a cloud child (`--pr`) or one on another host,
whose report says whether its tree was clean.

**A failed `run` or `wait` is not a failed child.** Its exit 1 can be the launcher's own
failure (a timeout on a loaded server, a killed background command) while the child works
on. A `run` that ends without a report, or a `start` whose launch fails, failed or stopped by
SIGTERM, SIGINT or SIGHUP, writes `FAILED: <code>: <message>` to the report path when no report is
there: one the child wrote, or an earlier pass's that a fix pass reuses the path of, stays, and
a later launch's line replaces an earlier one's (`<code>` is
the child's state and its `last_task_error` code, else `interrupted`, `timeout`, `blocked` or
`not-started`), so a wait on that file wakes (a wait on a reused path, on status); `wait`, `send`, `start` and the supervisor never
take that line as a report. Read the child's status first (the session id is the first line `run` printed, else
its title under your session's children); while it is running, or idle with its report
still to come, re-attach with `wait <session> <report>`, adding `--verdict` for a verifier
so a report written in stages does not end it early. `wait` has no launch time, so on a
path a pass before already wrote it returns that report at once: check the report's time
against the run's start before taking it. Start a second only for a child that failed or
is gone: two children on one item write the same branch.
An HTTP failure names the server's reason after its status (`HTTP 400 Bad Request: <message>`),
from at most 2 KB of the body read within 2 s, so a 400 tells a bad brief from a refusal.

**Whoever starts a worker collects it.** Omnigent files every child under the runner's
primary session, so a fork's or a worker's own children notify the lead, not the
session that started them. A session that starts workers keeps each one's background
`run`, or a `watch <session>...` on them, and reads their reports before it reports
itself; it does not end its work while one is still out.

What the script guards against, so do not hand-roll it with `sys_session_*`:

- A child created with a queued first message can stay idle for good (history holds only
  a `resource_event`, later sends don't reach it). The script creates the session empty,
  then sends.
- A send answers `queued`/`launching` even when the brief never arrives. The script
  counts a start only once that one line is a user message in the history, and otherwise
  abandons the session and retries once with a fresh one, titled `<title>-r<n>`.
- Omnigent refuses (409) a title an earlier child of the same parent holds, archived or
  not, such as a rerun `s120-verifier-p1`. The create then tries the next free
  `<title>-r<n>`, the same sequence the retry above uses, and prints the title it used. A create that fails (a timeout
  on a loaded server) may still have made the session, so the script looks for its title
  among the parent's children made since, and briefs that one instead of a second.
- A second `run` or `start` of a brief a live child of the same parent already holds (titled
  `<title>` or `<title>-r<n>`, and the one the last start for that report briefed with the
  same text, as `<report>.held` records) attaches to that child instead of starting another: one pass is paid for once. A
  failed or archived child doesn't count; one that already wrote the report since it was made
  is refused with the report's path, to read rather than wait on.
- A loaded or restarting server times out reads, drops TLS connections (an SSL EOF), refuses
  them or answers 502/503/504 while the child works on. Every `GET` is retried on those, with
  backoff over about two minutes; a `POST` never is, since it may have taken effect.
- A child that reads its brief as pasted text asks for a go-ahead, so the brief is a file
  and the message is one line. One that runs a command in the background ends its turn
  "waiting" and never reports; the preamble covers that, and the first turn that ends
  without a report or a question gets one nudge to poll its detached runs and write the
  report. `wait` fails when a second turn ends without a report, when the child is blocked on an approval prompt (it prints the
  prompt), or after `--timeout` (default 3h), so the lead still wakes.

**Children are your sub-agents.** Run from an Omnigent session, the script creates each
child under that runner's primary session (the lead), so the owner's sidebar shows
only leads. When a child's turn ends, Omnigent wakes you with "sub-agent …
finished … Call sys_read_inbox". Don't read the inbox; end your turn. The background
command's exit carries the result, with its checks. A child no `run`, `send` or `wait` is
waiting on (its command died, or it was started elsewhere) still wakes only that untitled
notice. One that still owes its report is covered by your supervisor's registry, which `run`
and `send` armed (Supervising sessions, below); for one that owes none, keep
`watch --children "$OMNIGENT_RUNNER_PRIMARY_SESSION_ID"` running in the background.

**Top-level leads.** `python3 scripts/omnigent_agent.py start --top-level <claude|codex|AGENT>
<title> <brief-file> <report-path>` starts a lead with no parent session, still filed under
the repo's project: the owner opens it from the sidebar and talks to it, its own children
report to it, and archiving it ends only its own runner. Its brief opens with the lead
preamble: only the owner's own words, quoted with where they were said, approve, the rest
of the brief is a colleague's guidance, the lead asks the owner in its own session rather
than in a question file, and it writes its final report to the path. How it asks and where
it parks a question is its role's (`--role`; under the engineering loop, `lead.md`). `run --top-level` exits 1, since a lead writes no
question for `run` to return: follow it with `watch <session>`, and once its report is in,
archive it with `reap <session>`.

`--host <name|id>` starts the lead on another Omnigent host (`GET /v1/hosts` lists them).
It needs `--top-level`, since Omnigent runs a child on its parent's runner. On a host other
than this one, `--workspace` is required, and it and the report are absolute paths on that host, never resolved or checked here; the brief goes inline
in the first message, because its file would be on this host, so a Claude lead may read it as
pasted text and ask for a go-ahead; and the report is written there, so follow the lead with
`watch`, never `wait`. With `--pr <n>` (a cloud worker) the report is instead the path here
that `wait --pr <n>` writes the PR comment to.

**Relaying to a lead.** `python3 scripts/omnigent_agent.py relay <session> <message-file>`
posts a message that owes no report, such as the owner's words for a top-level lead, and
returns at once. It reads no file but the message, so the lead may run on another host.
Exit 0: the message is in the lead's history, or a copy it has not replied to already is, so a
rerun sends no second one. Exit 5: queued, held until the lead's current step ends (a long
foreground command) or until a person answers the approval prompt it prints; it lands then
with no further call. Exit 4: not deliverable, and why (archived, a revive that failed, or
neither pending nor in the history within `--confirm-seconds`, default 60). A reaped runner is
revived in place first, as `send` does. A lead blocked only on questions (Claude's
AskUserQuestion, Codex's requestUserInput, both marked `ask_user_question` in its pending
prompts) holds every message until the question is answered, so a plain `relay` waits behind
it (exit 5) and lands once the question is answered: a relay that arrives while a question is
open must not become its answer. `relay --answer` answers each question with the message
instead (exit 0), through Omnigent's resolve route: the turn carries on with it as the
answer. An interrupt would drop the inputs pending and, on a Claude lead, hold the message up
to 7 minutes more (kzarzycki/omnigent#14). It never answers an approval prompt.
`relay --from <name>` is a notice from a task or an agent rather than the owner's words
(a scheduled job's status line to a chief of staff): its first line says so, and it never
answers a question, even with `--answer`. A plain
`relay` sent as a message, every `broadcast` message and every `send` follow-up open with `[relayed by <the relaying session>]`.

**Checking an owner's words.** `python3 scripts/omnigent_agent.py owner-said <session>
<quote or quote-file>` pages through the session's whole history for the newest message holding the
quote (whitespace collapsed) that the owner typed: `role: user` with a `created_by`, not
`is_meta`, and opening with none of the markers an agent or Omnigent posts with (a brief's exact
first line, `Supervisor: ` and `Supervisor [`, the two relay headers, `[System:`, the revive and
nudge lines). Exit 0 prints `owner said it: <server>/c/<session> item <id> at <UTC time> by
<author>` and, on a `> ` line, the whole message, so a fragment of "no, don't …" reads as what it
is; exit 1 says the quote
is only in a posted message, or nowhere. The server stamps an API post with the same
`created_by` as a typed message, so this catches a quote taken from a relay or a post, not an
agent that posts an unmarked message into the session on purpose; that needs the server to stamp
each item's origin.

**Broadcasting.** `python3 scripts/omnigent_agent.py broadcast <message-file> [--registry FILE]
[--active-hours N] [--project NAME ...] [--host NAME ...] [--include ID ...] [--exclude ID ...]
[--dry-run]` relays one message to every followed lead in the registry (default
`$OMNIGENT_SUPERVISE_REGISTRY`), each `--include` session and, with `--active-hours`, every
top-level session of yours (not one shared with you) updated within N hours, all at once rather than one `relay` after another,
each waiting on its own delivery. It never sends to its own session, an archived one or one in a
project whose name contains "automations", nor to one with a question or approval prompt
pending (`skipped: waiting on a question`): the message would wait unread behind it. Answer
that question with `relay --answer`, or send the message with a plain `relay`, which waits behind
it (exit 5) and lands once it is answered. `--project` (matched as `start` matches a
project: exact, else ignoring case and punctuation, two loose matches an error), `--host` and `--exclude` narrow the set. One
line per target: `delivered`, `queued …`, `skipped: <why>` or `failed: <why>` (also a session it could
not read); exit 1 when one failed, `--dry-run` included, which lists the targets and sends
nothing.

**Approving a prompt.** `python3 scripts/omnigent_agent.py approve <session> [--decline]`
accepts, or declines, every approval prompt the session has pending, never a question, and
prints each tool call it answered; exit 1 when none was pending or a resolve failed. It posts
`{"action": "accept"|"decline"}` to `POST /v1/sessions/<id>/elicitations/<elicitation_id>/resolve`,
the call the UI makes. Whether an agent may approve, and on whose word, is the project's
policy.

**Reading a session.** `python3 scripts/omnigent_agent.py status <session>...` prints, per
session, its state (`turn ended`, its running status, `blocked on a prompt: <what it asks>`,
`failed: <error>`, `archived`), how many inputs wait queued, and its last assistant message (`(none)` before its first, never
the brief or an injected reminder): one call
for what a subscription notice names, in place of session info plus history. It is a
snapshot: a native Claude session reads idle while quiet mid-turn, so an idle look reads as
`turn ended`, which a notice has already confirmed. A session Omnigent reports running whose only
live background tasks are `monitor`s (a published Artifact's live updates), its last item a
finished reply at least 30 s old (a running turn persists its narration just before the tool
call that follows), reads `turn ended` here and idle to the supervisor; a shell task keeps it
running. A tool call is persisted only once it returns, so a foreground one past 30 s reads so
too; `wait` and `reap` therefore keep the server's `running`, since there a misread would end
a wait or archive a working session.

**Reading a report.** `python3 scripts/omnigent_agent.py report <session> [<path>]` prints a
file of a session's workspace through Omnigent's file API, from any host, so a lead's report on
another host costs no session. An absolute path is read on the session's host, a relative one in
its workspace; no path is the report in the session's registry line (`--registry`, else
`$OMNIGENT_SUPERVISE_REGISTRY`; neither: exit 2). A directory prints its entries one per line.
Exit 4 is a missing file (a report not yet written), 1 an offline host or any other HTTP status.

**Watching sessions.** `python3 scripts/omnigent_agent.py watch [<session>...] [--children <parent>]`,
run as a background command, exits 0 as soon as one of them ends a turn (an end that has
held for 30s, since a native Claude session reads idle while quiet mid-turn), blocks on an
approval prompt or fails, printing for each the id, title, `turn ended`,
`blocked on a prompt: <the tool call>` or `failed: <error>`, and its last assistant message. A top-level
session tells no parent when its turn ends or it blocks, and the UI's "Completed" reaches
no agent, so a session that follows one without a subscription (below) learns it this way. Handle what it printed, then start `watch` again. States a session is already in when `watch` starts are not news,
except a prompt, which is reported at once; exit 1 after `--timeout` (default 3h). It polls
every few seconds; the session stream pushes the same changes faster but per session and
without replay, which a wake does not need. A watched prompt waits for its answer: a
person's in the UI, or `approve` (Approving a prompt).

**Subscribing to sessions.** A session subscribes to another (Omnigent's
`sys_session_subscribe` tool, or `POST /v1/sessions/<subscriber>/subscriptions` with
`{"session_id": <target>}`) to have Omnigent post `[System: session <title> (<id>) ended its
turn (completed|cancelled|failed). Read it with sys_session_get_history.]` or `[System: session
<title> (<id>) is waiting on a prompt. Read it with sys_session_get_info.]` into it, once per
turn or prompt, reviving the subscriber's runner when it was reaped. A notice carries no text
of the target's, so read what it names. It is how a top-level lead's starter hears it, since
only a sub-agent's parent is told; `start --top-level` subscribes the root of its session's tree, its lead
(`not subscribed` on stderr when the subscribe fails: a server without subscriptions answers
404, a cycle or the 1,000-per-session cap 409, and a shell that does not name its session
(`OMNIGENT_SESSION_ID`, `OMNIGENT_TERMINAL_LAUNCH_SESSION_ID` or
`OMNIGENT_RUNNER_PRIMARY_SESSION_ID`; a native Codex one names none before Omnigent 567625d35)
subscribes nobody;
follow that lead with `watch`). With a registry (`--registry` or `$OMNIGENT_SUPERVISE_REGISTRY`)
it subscribes nobody and arms the lead's line with `follow` instead (Supervising sessions): a
subscription wakes its session with a full-context turn on every turn end, and most of those
change nothing. It says nothing of a session silent
mid-turn, which `supervise` still catches. Archiving or deleting either side drops it.

**Supervising sessions.** A turn end can be lost: a lead that is a sub-agent of a
chief of staff on another runner has its idle status refused (HTTP 503, the runner logging
"parent inbox is missing") until something else wakes it, so its status stays `running`
and nobody hears that it stopped, and Omnigent reaps a runner idle for an hour
(`runner.idle_timeout_s`). `python3 scripts/omnigent_agent.py supervise <session>=<report>...`
checks liveness, not only outcomes, for sessions that each owe a report. A session with no
live runner it revives in place (`revived`), then sends it the revive line, since a revive can
relaunch it with its context dropped: "Your session was restarted and may have lost its
context. Read your brief: <files>. Write your report to <report>." The files are the
registry's brief files in order, else `<report>.brief` when it exists (what `start` writes);
with neither, the line names only the report. A send of it that fails is tried again at the
session's next look. Like the resume line, it is no instruction, so a
report written for the brief still counts after it. One with no history item for
`--silent-seconds` (default 1800, three times the 10-minute limit of one tool call)
it sends the `wait` nudge once as its resume line, whatever its status says
(`resume line sent`). A session waiting on its own worker or verifier writes nothing meanwhile,
so a child of it updated within that window (`child_sessions`' `updated_at`), or a live session it
subscribes to (a top-level helper such as a cloud worker), keeps it live: silence means the whole
subtree and its helpers are quiet. It prints each of those at once and goes on. It exits 0 with one line
as soon as a session wrote its report (`report written: <path>`) or a question
(`asked: <path>`), blocks on a prompt, fails, or is given up on (`gave up`: silent again after
its resume line, which may sit undelivered behind a stuck step; silent with an input already
undelivered; or a failed revive). A report counts once newer than the session's last
instruction, so one written before `supervise` started counts at once and an earlier
phase's at the same path does not, and it counts only once the session's turn has ended,
as `run` counts it. A resume line already in the history counts as sent, so a
supervisor started again gives up on a session still silent after it instead of sending a
second. Exit 1 after `--timeout` (default 3h) with no event.

`supervise --registry <file> [--notify <session>]` runs the same check until it is stopped.
Each poll it re-reads the file: one `<session>=<report>` per line, optionally followed by the
session's brief files, each after a tab, blank lines and `#` comments skipped, a malformed line logged and skipped, the last line winning for a session listed
twice, and a missing file empty. Pairs on its command line are added to the file first. It
prints every line with the local time and, with `--notify`, posts it into that session as
`Supervisor: <line>`, which wakes the session even with no command of its own running; a
notify session whose runner was reaped is revived first, since a message to it would never
arrive. Lines wait in order until posted, and each poll posts them first, so a failed post
delays a line but loses none. A terminal event (report written, asked, blocked, failed, gave
up) drops the session's line once its own line is posted; until then the session is not checked
again. A restart loses the revive and resume lines still waiting, but finds a terminal event
again, since its registry line is still there. An error reading the registry or a session, or
posting, goes to stderr once until it clears, and a `--timeout` window with no event logs
`no event in <n>s: <sessions>`; neither stops it, and one session's error skips no other.

`run`, `start` and `send` arm the registry named by `--registry`, else
`$OMNIGENT_SUPERVISE_REGISTRY`: once their message is in the history, they write
`<session>=<report>`, replacing any line for that session. `start` (and so `run`) puts its
brief file `<report>.brief` on the line; `send` appends its message file to the line's brief
files (else to `<report>.brief` when it exists), so a revived session reads its brief and then
each follow-up in order. Not before, because until the
message lands the turn before's report or question reads as newer than the last instruction,
a false event. `run`, `send` and `wait` remove the line once they return the report or a
question, since their caller has it; a race can still deliver both, and the second line is no
news. `reap` with the registry drops the line of each session it finishes, before finishing it,
so the supervisor posts `archived` only for a session someone else archived. A failed wait keeps it, so the supervisor watches on. A failed arm is a warning, since
the command's own wait still covers the session. Every edit locks the file (`fcntl.flock`), so
an arm and a drop of two sessions at once lose neither line. A drop of the same session keeps
the line when the session was instructed after the event's own instruction (the resume and
revive lines are no instruction): a `send` that
armed it again for the next brief while the event was being posted, which it does only once
that brief is in the history.

A line ending in the field `follow` (`<session>=<report>`, the brief file, `follow`: what `start
--top-level` writes with a registry) is a lead the supervisor follows, which owes no report and is
never given up on, nor revived or sent the resume line as a session owing a report is (with
`--console` its routing may nudge or revive it). Its lines go to `--notify` as the others do, but only
when they are news, so the notified session is not woken for a turn that changed nothing:
a turn end whose last message starts a line with `DONE`, `USER NEEDED` or `PARKED` (a `USER NEEDED`
line wins over an earlier `DONE` or `PARKED` one, since an ask after a `DONE` still needs its answer), once it holds
as `watch` counts an end; any other turn end only once the lead, its live children and the live sessions it
subscribes to wrote nothing for 300 s since it (`turn ended, quiet <n>s`, which covers a stall, a lead waiting on
another's merge and a question with no ending), since a lead briefed or active again within that
time was not stuck; a prompt once it has been pending 120 s across looks, since Omnigent shows each
child's prompt on its parent too and the lead answers it itself, usually within a minute; a failure
at once; each once per occurrence; and `archived`, which is the
only event that drops the line, so a relay needs no re-arm. Each is posted once per message.
A restart posts an end it finds again.

**`--console`**, the chief of staff's console, adds what its supervisor needs and no other: a
state file, an events log, status labels, a progress deadline, settled events kept across
restarts, and routing (below). Without it `supervise --registry` writes none of them, and the paragraphs above are
all it does. With it, each event is routed once, also across a restart, and posted only when its
route sends it to the notified session (Routing, below): a terminal event found again after one
only drops the line it already settled, and a followed lead's failure or prompt is
one event per occurrence (`occurrences` in the state counts each entry into one), so the same
error again after a recovery is news and the one a restart finds again is not.

A followed lead also has a progress deadline, since a lead that reads running for good, or goes
quiet a second time with the same last message, makes none of those events. Its progress,
`progress_at`, is the latest of its own history (any item but a message to it, so a nudge is
none), once it has any, a message to it that is not the supervisor's own (a relay or the owner
typing, which starts a new chain), and the activity of its live children and of the live sessions it subscribes to (its
top-level helpers, a cloud worker for one, which are no children), read on first sight, then once a minute and again when
the deadline falls due, and, once the deadline falls due, its report's last write (from its
folder's listing), so a lead already stuck when the supervisor starts is overdue at once; a
lead with neither counts from first sight. With
no progress for 20 minutes it posts `<session> <title>: no progress <n>m (<wait>)` and the
lead's first line, whatever its status reads; a lead whose wait is unknown and that was nudged
on this chain (`nudged_at`, the `progress_at` its nudge was sent at) gets a second, `no progress
<n>m after a nudge`, 10 minutes later. The
wait comes from the lead's last message: `parked` for a `PARKED` ending, the thing a `STILL
WORKING` names (`verifier`, `CI`, `worker`, `lead`, `merge`, a child's session id, or a
background task id such as `bz3jp5aod`, `b` and 8 lowercase letters and digits with one digit at
least, opening it or after `on`/`for`), else
`unknown`. A `STILL WORKING` naming a UTC time (`until 2026-10-21T23:17Z`, `2026-10-21 23:17
UTC`) is a timed wait, `until <time>`: no deadline before that time plus 20 minutes, then the
named-wait rule. A last message that
is only a report's path takes its ending and wait from the report's first line, read once per
last message (a failed read is logged once and leaves them as the message gave them). None for a
parked lead, which waits on capacity, also while a lost turn end leaves it reading running; and
none while the lead is out of its turn with `DONE` or `USER NEEDED`, blocked or failed, since it
then waits on its follower, who was told. Each deadline is one event per
lead and `progress_at`, so new progress starts a new chain. A lead whose registry line has the
`direct` field (`omnigent_agent.py direct <session>`, `--off` clears it), one the owner drives in
its own session, has no deadline at all: its quiet ends and `USER NEEDED` are recorded, not
routed, since the owner reads them there, and the `no event in <n>s` log line leaves it out; its
`DONE`, failures and prompts route as any lead's.

**Routing.** With `--console` an event is not posted as a line: the supervisor routes it, by
`route`'s table (the design's § Routing an event), and settles what needs no decision itself.

| Event | Settled by | What happens |
|---|---|---|
| `archived` | rule | its line and state entry dropped; no post |
| `PARKED`, a `STILL WORKING` naming its wait, an exact repeat of the lead's last event | rule | recorded; no post |
| a quiet end (no ending, no named wait) | small model | mid-work: recorded; stalled: the nudge; for the owner: queued for them; no answer (a failure, no allowance left): act |
| a quiet end again with no progress since the nudge | rule | act |
| `deadline` | rule | a named wait: act; unknown: the nudge, then act at the deadline after it; parked: none |
| failed | rule | the first time a revive, after it act |
| `DONE` | rule | act, and each lead registered `after=` it is told `Supervisor: <lead>, the lead you wait on, ended: <its first line>` |
| a last message that is only a report path | rule | the report's first line read (`report`'s file API) and routed as the message; no ending: act |
| `USER NEEDED`, also below an earlier `DONE` or `PARKED` line, which it wins over | small model | covered by a standing decision: act; else, or with no `--decisions`, the owner (no model) |
| an approval prompt | rule | the owner; nothing in the supervisor approves |
| a question | rule | act, for one `relay --answer` |
| a session owing a report: its outcome; its revive or resume line | rule | act (a prompt: the owner); recorded |

The small model only routes, since its input holds a lead's own words: one `claude -p --model
<model> --tools "" --setting-sources "" --strict-mcp-config --no-session-persistence
--system-prompt <routing prompt>` call, the model `$OMNIGENT_SMALL_MODEL`, else
`claude-haiku-5-5`, the event (cut to 4,000 characters) on stdin, 200 output tokens
(`CLAUDE_CODE_MAX_OUTPUT_TOKENS`), 20 s. Its answer is one JSON line, `{"route":
"none"|"act"|"owner", "why": …}`; anything else, a missing `claude`, a non-zero exit or the
timeout routes act, never the nudge, which only the model's own `act` on a quiet end sends. The standing decisions it weighs are `--decisions <file>`'s section under a
`## Standing decisions` heading, else the whole file, read at each call. At most 30 calls in a
rolling hour (`rate.model_calls`, written before each call); past them, an event routes act with
no model, a quiet end too.

The supervisor's own actions, the nudge (`Supervisor: your turn ended with no ending and no named
wait. Carry on to your next step, and end your turn with DONE, STILL WORKING naming what you wait
on, USER NEEDED or PARKED.`), the revive and telling a waiting lead, go through `relay`, which
revives a reaped runner and sends no second copy. Each is an intent in the state, written with its
budget counted (`nudges` and `nudged_at`, one nudge per progress chain; `revives`, one per lead)
before the first send (every waiting lead's tell at once) and marked done after each; one to a lead waiting on a prompt is not sent, since
it would wait unread behind the prompt, and a failed send goes to the chief of staff as act. On
a restart an intent still open is looked up in the lead's history: its text there, no older than
the intent less a minute's margin for clock skew, or still pending in its `pending_inputs`, marks
it done,
else it is escalated as act, never sent again. A state write that fails before a small-model call, an
action or a post stops it: nothing is asked or sent, what the event had settled is undone, and it
is settled again at the next poll. A budget already spent stays spent: a model call made before
a later write failed keeps its place in the hour, and the retry acts on its answer.

What needs the notified session waits in the state's `attention` queue and goes out as one post,
at most one per 5 minutes (`rate.next_post_at`, written before the post), so a restart or a
successor keeps the window: `Supervisor [act] b-<id>: <n> events`, or `[owner]` when one is the
owner's, one line per event with why, then each lead's status row and the first 5 lines of its
report (read through the file API, from any host; a failed read is noted). The post is pending in
the state with its batch id before the send and delivered after, and its events leave the queue
only then, so nothing waiting for the owner is dropped; a session owing a report has its event
written to the queue before its registry line is dropped. A pending post (a crash or a failed send
left it) is looked up in the notified session's history by its id, a page of 100 at a time back
to its pending time, and in its `pending_inputs`: found, it was delivered; not found, it is sent again with its id, and that
retry reserves the next 5 minutes as a new post would. The
notified session's own `status.line` reads `needs you: <n>` while owner events wait. Without
`--notify` the post is printed (`would post:`), so a run on a copy of the registry shows the
routing. `--fyi post` posts every line as without `--console` too; the default, `skip`, posts
only what is routed.

A lead that waits on another is started with `start --top-level --after <session>`, which adds
`after=<session>` to its registry line; the state mirrors it as `waits_on`.

`--console` keeps its state next to the registry, named from it (`leads.registry`:
`leads.state.json`, `leads.events.jsonl`), so two supervisors in one directory never share one.

- `<name>.state.json`, schema `cos-state/1`, rewritten every poll through a temp file and a
  rename, so a reader never sees half of one, with `written_at`: under `leads` an entry per
  registry session (title, host, report, brief files, whether it is followed, `waits_on`,
  state, wait, error, ending, first line of its last message, `progress_at`, `nudges`,
  `revives`, `nudged_at`, `occurrences`, the last event, the labels last written); under
  `settled` the ids of the events routed, the newest 20 per session; `intents` (each open, done,
  failed or escalated; the newest 50 closed ones), `attention`, `pending_posts`, `rate`
  (`next_post_at`, `model_calls`: the times of this hour's calls) and `notify_label`. It is
  loaded on start, so a restart re-raises no settled event and keeps `progress_at`, budgets,
  open intents, the queue, a pending post, the rate windows and labels. A session gone from the registry leaves it; an unreadable file or another
  schema is a warning and a fresh start.
- `<name>.events.jsonl`: one JSON line per routed event (`at`, `id`, `session`, `kind`,
  `line`, `settled`: `rule` or `model`, `action`, `why`), so a wrong call can be found and the
  rules tuned.
- Two labels on each session, for the web UI: `status.line`, its state in under 200
  characters (`running · waits on verifier`, `turn ended: DONE …`, `blocked on a prompt`,
  `failed: …`), since Omnigent cuts a label value to its first 256 without an error, and
  `status.at`, the Unix seconds it was observed. They are written (`PATCH /v1/sessions/{id}`
  `labels`) only when the line changed or the last write is a minute old, so `status.at` stays
  fresh while the supervisor runs and the browser can mark a line from a dead one stale past 10
  minutes. Display only: never read back. A failed write is logged once and the poll goes on.

A lead supervises this way a child no `run`, `send` or `wait` waits on any more: one detached supervisor per supervising session (`--notify`
names one), with its own registry, set as `OMNIGENT_SUPERVISE_REGISTRY` for its `run` and
`send`. An in-session background command or a session cron dies when the session restarts,
and with it every wake it owed. The one-shot form serves a single check in the foreground.

**Running the supervisor detached.** The service manager keeps the supervisor running past
the session it wakes. A job starts with a bare `PATH` (launchd's is `/usr/bin:/bin:/usr/sbin:/sbin`),
so it sets one that finds `omnigent`, whose interpreter refreshes the token. Give each
supervisor its own label or unit name. On macOS, until logout:

```bash
launchctl submit -l <label> -o <log>.out -e <log>.err -- /bin/sh -c \
  "PATH=$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin exec /usr/bin/python3 <abs-path>/scripts/omnigent_agent.py --server $RUNNER_SERVER_URL supervise --registry <file> --notify <session>"
```

A job also starts without the session's `RUNNER_SERVER_URL`, so the command names the server
(the shell expands it at submit time). `omnigent_agent.py` acts on the first of `--server`,
`$RUNNER_SERVER_URL` (set by the runner in every session), and the one login in
`auth_tokens.json`. `config.yaml`'s `server:` is not read, because one account runs workloads on
several servers and a single default sends some of them to the wrong one. Outside a session with
several logins and no `--server`, the script refuses rather than guess.

launchd restarts it if it exits; `launchctl print gui/$(id -u)/<label>` shows it and
`launchctl remove <label>` stops it. For one that survives a reboot, write a LaunchAgent
`~/Library/LaunchAgents/<label>.plist` with that command as `ProgramArguments`, `KeepAlive`
and `RunAtLoad` true, `StandardOutPath` and `StandardErrorPath`, and `PATH` under
`EnvironmentVariables`, and load it with `launchctl bootstrap gui/$(id -u) <plist>`
(`launchctl bootout gui/$(id -u)/<label>` stops it). On Linux, a systemd user unit
`~/.config/systemd/user/<name>.service` with `ExecStart=` the command, `Environment=PATH=…`,
`Restart=always` and `WantedBy=default.target`, started with
`systemctl --user enable --now <name>`; `loginctl enable-linger $USER` keeps it running while
the user is logged out, and `journalctl --user -u <name>` shows its log.

An update needs no restart: when `omnigent_agent.py` is replaced on disk (a skills sync
installing a new one), `supervise --registry` re-executes itself in place with the same
arguments, at the top of a poll with nothing waiting to be posted and its state written first,
logging `restarting: <script> changed`. It waits until the file is unchanged for one poll, so a
half-written file is not taken, and a new file that does not compile is logged once while the
running copy carries on.

**Finished sessions.** `run` and `wait` finish the session whose report or verdict they
return, unless given `--keep` (Cloud workers); a session that asked a question stays, since
the answer goes to it. Finishing ends the session's agent process and keeps its transcript.
It archives the session, a sub-agent too: Omnigent leaves the runner it shares with its parent up, on a build with
kzarzycki/omnigent 4dd0af32; an older build stops that runner and the parent with it.
`python3 scripts/omnigent_agent.py reap [<session>...] [--children <parent>] [--registry <file>]` finishes each
session that is done (not running, no prompt or input waiting), printing `archived` for
each and `already archived` for one finished before, and prints which it kept. A finish that fails is printed and the rest still run, and
`reap` then exits 1. It cannot tell an idle child whose report is still
to come from a finished one, so a child whose `run` died is re-attached with `wait` (above),
which finishes it on return, never reaped. Run `reap --children
"$OMNIGENT_RUNNER_PRIMARY_SESSION_ID"` only once every child's report is in or the child is
given up, as the last step before your own report. Never `DELETE` a session: it erases the
transcript.

**Permission prompts.** An agent's workspace is the directory it was started in, so its
reads there, its children's checkouts included, never prompt, in any harness; its writes
there follow the permission mode (Codex's workspace-write allows them). So put each child's
checkout inside the workspace of the agent that starts it, in a directory the project
gitignores (where and how is the project's: under the engineering loop, loop.md § Worktree),
and run the child's command from there. Outside it, Claude Code prompts for a read, or denies it in auto mode (`cd <sibling>; grep ...` or a plain
`cat <sibling>/f`), which nobody answers, and Codex's workspace-write sandbox refuses a write.
No allow rule stands in for the layout: a project rule `Read(/../**)` or `Read(../**)` never
matches a sibling, an absolute `//…` or `~/…` rule names one machine's layout, and a project's
rules are ignored in a workspace nobody has trusted. Nor does an Omnigent policy: its native
hook maps ALLOW to no opinion, so Claude Code's own prompt still runs.

**List:** `sys_session_list`. **Close:** `sys_session_close`; where it refuses with
`session_not_a_sub_agent`, leave the finished session idle.
