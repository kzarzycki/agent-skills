# Orchestrating with Omnigent

Start each worker or verifier with its own background command, whose exit wakes you; keep
working meanwhile:

```bash
python3 scripts/omnigent_agent.py run <claude|codex> <title> <brief-file> <report-path> --role <role-file>
```

Run it from the worktree the child works in, because the script makes its current
directory the session's workspace; `--workspace <dir>` names another, such as the parent of
several repos for a lead whose change spans them. The report path goes in a gitignored directory of that
workspace (under the engineering loop, `tmp/loop/`): outside its workspace a Codex child's sandbox refuses the write and a Claude Code
child is prompted for a read (denied in auto mode), which nobody answers, so the script refuses
such a path. Titles look like `s120-parser-worker`,
`pr182-verifier-p1`: the issue or PR, then the role. The brief file holds only the task
specifics; the script writes it, under a fixed preamble (owner-authorized imperative, the
role file, long commands in the foreground, write the report to the path, reply with only
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
answer. Sessions are filed under the Omnigent project named like the repo, when one exists;
case, spaces and punctuation don't count, so `voice_note` files under "Voice note". An
exact name wins, and two loose matches with no exact one fail until `OMNIGENT_PROJECT`,
which overrides the name, names one.

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
verifier included. Pass `--model` only when the owner asked for that model or the project's instructions
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

**Author family.** `--author <claude|codex>` names the family that wrote what the child
reviews. When it matches the child's own family the script refuses unless `--same-family`
is given, so a reviewer of the author's family is always a deliberate choice. Whether a
reviewer must be of the other family is the caller's policy.

`start` and `wait <session> <report>` are the two halves, for a start whose wait runs
elsewhere.

**Host capacity.** `python3 scripts/omnigent_agent.py capacity` prints this host's load per
core and available memory, and exits 0 when it has room for another session, 1 when not.
`start` and `run` wait while it has none, printing a line, and fail after 10 minutes, since
sessions on an overloaded host time out and fail. The limits are knobs set for the hardware:
`OMNIGENT_MAX_LOAD_PER_CORE` (default 4) and `OMNIGENT_MIN_AVAILABLE_MB` (default 1536). A
message `start`, `send` or `relay` posts is not failed when its POST times out on a slow
server: the history decides whether it landed, within `--confirm-seconds`. The supervisor's
own posts, which read no history, still count a timeout as a failure and try again.

**A failed `run` or `wait` is not a failed child.** Its exit 1 can be the launcher's own
failure (a timeout on a loaded server, a killed background command) while the child works
on. Read the child's status first (the session id is the first line `run` printed, else
its title under your session's children); while it is running, or idle with its report
still to come, re-attach with `wait <session> <report>`, adding `--verdict` for a verifier
so a report written in stages does not end it early. `wait` has no launch time, so on a
path a pass before already wrote it returns that report at once: check the report's time
against the run's start before taking it. Start a second only for a child that failed or
is gone: two children on one item write the same branch.

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
- A loaded server times out reads while the child works on. Every `GET` is retried on a
  timeout or reset, with backoff; a `POST` never is, since it may have taken effect.
- A child that reads its brief as pasted text asks for a go-ahead, so the brief is a file
  and the message is one line. One that runs a command in the background ends its turn
  "waiting" and never reports; the preamble covers that, and the first turn that ends
  without a report or a question gets one nudge to finish in the foreground and write the
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

**Top-level leads.** `python3 scripts/omnigent_agent.py start --top-level <claude|codex>
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
`watch`, never `wait`.

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
prompts) holds every message until the question is answered, so `relay` answers each with the
message instead (exit 0), through Omnigent's resolve route: the turn carries on with it as
the answer. An interrupt would drop the inputs pending and, on a Claude lead, hold the
message up to 7 minutes more (kzarzycki/omnigent#14). It never answers an approval prompt.

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
`turn ended`, which a notice has already confirmed.

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
only a sub-agent's parent is told; `start --top-level` subscribes the session it runs in
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
`--silent-seconds` (default 1800, three times the longest foreground command a brief allows)
it sends the `wait` nudge once as its resume line, whatever its status says
(`resume line sent`). A session waiting on its own worker or verifier writes nothing meanwhile,
so a child of it updated within that window (`child_sessions`' `updated_at`) keeps it live:
silence means the whole subtree is quiet. It prints each of those at once and goes on. It exits 0 with one line
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
news. A failed wait keeps it, so the supervisor watches on. A failed arm is a warning, since
the command's own wait still covers the session. Every edit locks the file (`fcntl.flock`), so
an arm and a drop of two sessions at once lose neither line. A drop of the same session keeps
the line when the session was instructed after the event's own instruction (the resume and
revive lines are no instruction): a `send` that
armed it again for the next brief while the event was being posted, which it does only once
that brief is in the history.

A line ending in the field `follow` (`<session>=<report>`, the brief file, `follow`: what `start
--top-level` writes with a registry) is a lead the supervisor follows, which owes no report and is
never revived, nudged or given up on. Its lines go to `--notify` as the others do, but only
when they are news, so the notified session is not woken for a turn that changed nothing:
a turn end whose last message starts a line with `DONE`, `USER NEEDED` or `PARKED`, once it holds
as `watch` counts an end; any other turn end only once the lead and its live children wrote
nothing for 300 s since it (`turn ended, quiet <n>s`, which covers a stall, a lead waiting on
another's merge and a question with no ending), since a lead briefed or active again within that
time was not stuck; a prompt or a failure, each once per occurrence; and `archived`, which is the
only event that drops the line, so a relay needs no re-arm. Each is posted once per message.
A restart posts an end it finds again.

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
  "PATH=$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin exec /usr/bin/python3 <abs-path>/scripts/omnigent_agent.py supervise --registry <file> --notify <session>"
```

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

**Finished sessions.** `run` and `wait` finish the session whose report or verdict they
return, which ends its agent process and keeps its transcript; a session that asked a
question stays, since the answer goes to it. Finishing archives the session, a sub-agent
too: Omnigent leaves the runner it shares with its parent up, on a build with
kzarzycki/omnigent 4dd0af32; an older build stops that runner and the parent with it.
`python3 scripts/omnigent_agent.py reap [<session>...] [--children <parent>]` finishes each
session that is done (not running, no prompt or input waiting), printing `archived` for
each, and prints which it kept. A finish that fails is printed and the rest still run, and
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
