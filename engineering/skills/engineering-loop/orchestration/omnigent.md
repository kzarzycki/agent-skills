# Orchestrating with Omnigent

Start each worker or verifier with its own background command, whose exit wakes you; keep
working meanwhile:

```bash
python3 scripts/omnigent_agent.py run <claude|codex> <title> <brief-file> <report-path> --role <role-file>
```

Run it from the worktree the child works in, because the script makes its current
directory the session's workspace. The report path goes under `tmp/loop/` in that
worktree: a child is prompted for every file it reads outside its workspace, nobody
answers, and the script refuses such a path. Titles look like `s120-parser-worker`,
`s120-verifier-p1`. The brief file holds only the task specifics; the script writes it,
under a fixed preamble (owner-authorized imperative, the role file, long commands in the
foreground, write the report to the path, reply with only the path), to `<report>.brief`
and sends the child one line naming that file. Build the brief with a quoted heredoc
(`<<'EOF'`): an unquoted one runs each backticked name as a command, and the script
refuses a brief left with an empty `` `` `` span. Exit 0 prints the report path. Exit 1
prints the reason and the child's last message; for a session that failed, also its
`last_task_error` and its runner log. With a verifier's role file, the report
counts only once it has its `SATISFIED:` line, so a report written in stages does not end
the wait early. Sessions are filed under the Omnigent project named like the repo, when
one exists; `OMNIGENT_PROJECT` overrides the name.

**Questions.** A child never asks the owner. It writes `<report>.question` and stops;
exit 3 prints that path. Answer from the spec and the owner's stated intent, or ask the
owner only when neither settles it, then run
`python3 scripts/omnigent_agent.py send <session> <answer-file> <report>` in the
background. It continues the same session while its cache is warm and waits as `run`
does; add `--verdict` when the child is a verifier, because `send` and `wait` are not
given the role. A child still in a turn gets the answer at its next tool boundary; until
then `send` reports it queued and waits, and a rerun of the same `send` waits for the
first copy instead of delivering a second. A report left from the earlier turn does not
end the wait: only one written after the send counts. Exit 4 means the answer did not
land, usually because Omnigent reaped the runner (idle over an hour): start a fresh run
whose brief carries the question and the answer.

**Follow-ups** (a fix pass, a rebase) are a fresh run whose brief points at the earlier
report: after an idle hour the cache is cold, so the report is cheaper than the old
transcript, and a send to a reaped session answers `queued` and never arrives. It may
reuse the report path: a report already there counts only once rewritten after the launch.

**Model.** A child runs on `--model`, else `OMNIGENT_MODEL_<AGENT>` (`OMNIGENT_MODEL_CODEX`,
`OMNIGENT_MODEL_CLAUDE`), else its harness's default; a Codex verifier's default is
`gpt-6.1-sol`, so it does not inherit `~/.codex/config.toml`'s model.

**Same-family verifier.** Pass `--author <claude|codex>` when starting a verifier. When
it matches the verifier's family the script refuses unless `--same-family` is given; the
brief stays silent about it, and the PR body says `verifier: same family`.

`start` and `wait <session> <report>` are the two halves, for a start whose wait runs
elsewhere.

What the script guards against, so do not hand-roll it with `sys_session_*`:

- A child created with a queued first message can stay idle for good (history holds only
  a `resource_event`, later sends don't reach it). The script creates the session empty,
  then sends.
- A send answers `queued`/`launching` even when the brief never arrives. The script
  counts a start only once that one line is a user message in the history, and otherwise
  abandons the session and retries once with a fresh one. A create that fails (a timeout
  on a loaded server) may still have made the session, so the script looks for its title
  among the parent's children made since, and briefs that one instead of a second.
- A loaded server times out reads while the child works on. Every `GET` is retried on a
  timeout or reset, with backoff; a `POST` never is, since it may have taken effect.
- A child that reads its brief as pasted text asks for a go-ahead, so the brief is a file
  and the message is one line. One that runs a command in the background ends its turn
  "waiting" and never reports; the preamble covers that, and the first turn that ends
  without a report or a question gets one nudge to finish in the foreground and write the
  report. `wait` fails when a second turn ends without a report, when the child is blocked on an approval prompt (it prints the
  prompt), or after `--timeout` (default 3h), so the coordinator still wakes.

**Children are your sub-agents.** Run from an Omnigent session, the script creates each
child under that runner's primary session (the coordinator), so the owner's sidebar shows
only coordinators. When a child's turn ends, Omnigent wakes you with "sub-agent …
finished … Call sys_read_inbox". Don't read the inbox; end your turn. The background
command's exit carries the result, with its checks.

**List:** `sys_session_list`. **Close:** `sys_session_close`; where it refuses with
`session_not_a_sub_agent`, leave the finished session idle.
