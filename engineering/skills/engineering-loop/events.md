# Loop events: the contract

A step's state, written as a small git ref on `origin` where a reader finds it in a typed field instead of reading
prose. Every producer and the supervisor read this file; `scripts/events.py` is its writer and reader (`emit`,
`read`, `wait`, `clear`; its docstring has the flags). Read this when you write a producer, read an event, or add a kind.

## The ref

`refs/loop/<kind>/<branch>` points to a **parentless** commit whose tree holds `event.json` and, for a request to the
owner, `question.md` (the whole text, never cut). A beat is the same ref rewritten with a new parentless commit, so one
commit is reachable from it and history never grows. The branch is the one the work is on, so the ref exists before
a PR does and survives a push. The landing lock and waiter refs (`refs/heads/loop-landing/*`, `refs/heads/loop-waiting/*`)
are not events and stay as `land` writes them, and so are the gatekeeper's `refs/loop/records/*` (gate records) and
`refs/loop/landing`: `read` lists only the kinds below.

`event.json` fields (all present on every event):

| Field | Type | Meaning |
|---|---|---|
| `state` | string | `waiting`, `ok`, `failed` or `needs-owner` |
| `seq` | integer | 1 for a ref's first event in this clone, plus one on each rewrite |
| `at` | string | UTC time of the write, `YYYY-MM-DDTHH:MM:SSZ` |
| `beat_s` | number | seconds between this producer's beats: the kind's interval below unless the producer says otherwise |
| `url` | string | what the kind's row below says, or `""` |

States: `waiting` (the step runs and will beat again), `ok` (ended well), `failed` (ended badly: `url` says why),
`needs-owner` (the step needs the owner's answer: `question.md` holds it). A reader treats `ok`, `failed` and `needs-owner`
as ends and leaves a ref it cannot read or parse as `unknown`, never as ended; the deadline then applies.

## Kinds

| Kind | Writer | Beat interval | `url` points to |
|---|---|---|---|
| `lead` | the lead's own script, when it waits or needs the owner | 300 s | the PR or issue the lead's item is |
| `land` | `approvals.py land` | 300 s | the PR, and on `failed` the failing log |
| `gate` | the gate run, `local-ci` (slice #1379); the main-commit `gate` status that `land` writes (`publish(tip, landed_pass(...))`) stays | 120 s | the `local-ci` record; on `failed`, the detached run's log when there is one, else empty |
| `verifier` | the verifier run | 300 s | the verifier's report or PR comment |
| `probe` | `events.py` tests and the one-off check below only | 60 s | nothing |

A wait is **live** while its ref changed within twice its `beat_s`. `wait` ends with exit 4 on a `waiting` event that
did not change for longer, counted from its `at` on the first sight and from the moment its sha moved after that.
The intervals are the kinds' starting values: the code that writes a kind may set `beat_s` per emit and fix its row here.

## Reading and waiting

- `read [<kind>]`: one `git ls-remote origin 'refs/loop/*'` (no API quota; a changed sha is a change), then a fetch of
  only the refs whose sha moved since the last read, into `refs/loop-remote/`, and the parsed events with `changed`,
  when this clone first saw the sha. The cache is `loop-events-seen.json` in the git dir.
- `wait <kind> <branch>`: exit 0 `ok`, 1 `failed`, 2 `needs-owner` (the question is printed), 3 timeout, 4 silent.
  Each poll reads the local ref, then origin's, and takes the later `at`.
- `clear <branch>`: removes the branch's refs of every kind here and on origin. `land` calls it when a PR merges
  and `reap` for a closed one.

## Degraded

Only `git` and an `origin` are needed. `emit` writes the local ref first; a push that fails prints one warning and
exits 0, so an event reports a step and is never part of it. A native lead in the same clone still sees the event with
`wait`; another host sees it when a later push goes through. `read` with origin down shows the local events (kinds below, nested branches included) and warns.

## Measured on GitHub

- **Rulesets:** `gh api repos/{owner}/{repo}/rulesets/<id>` lists two: `main` (target branch, includes only
  `refs/heads/main`: deletion, non_fast_forward, required_status_checks, pull_request) and `tags immutable` (target
  tag: deletion, update, non_fast_forward). Neither matches `refs/loop/*`, so no ruleset blocks it.
- **`git ls-remote origin 'refs/loop/*'`:** 0.51 s with no such ref (one call). The same call over `refs/heads/*`
  (325 refs) took 0.44 s and over every ref (1107) 0.37 s, so a listing of 20 refs costs well under a second; the call
  is bound by the round trip, not the count.
- **A push of `refs/loop/probe/<branch>`:** accepted by GitHub with a plain token from a host. One `events.py emit` took
  2.3 s end to end (process start, commit, push); `git ls-remote origin 'refs/loop/*'` with one such ref took 0.46 s;
  `events.py clear` removed it from `origin`. A cloud session's proxy refuses refs outside `refs/heads/` (`RPC failed;
  HTTP 403`), so **a cloud session's events stay local and warn once** (Degraded); only a host with push access
  writes events another host reads.
