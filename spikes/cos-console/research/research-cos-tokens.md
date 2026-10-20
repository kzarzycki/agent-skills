# Where a chief-of-staff session spends its tokens

Data: Omnigent API, read-only, three CoS sessions on cc-experiments. All figures below are measured unless marked (est).

## What the data allows

- Per-turn usage is not in the API. `/v1/sessions/<id>/items` carries no token or cost fields (only a compaction item with `token_count: 0`). `/v1/sessions/<id>` has per-session lifetime totals only: `total_cost_usd`, `usage_by_model`, `last_total_tokens`.
- So turn counts, tool-call counts and trigger kinds are exact; tokens and cost are allocated to turns by API-call count (est). One turn costs `tool calls + 1` model calls, and each call re-reads the transcript.
- `d884cbe8` has cost only (tokens null). `13cd3ad1` has token totals that look partial (cache read 3.2M over 189 calls is 17k per call, yet its final context is 174k), so read its totals with care.

## Session totals (from `GET /v1/sessions/<id>`)

| Session | Span | Turns | Model calls (est: calls + turns) | Cost | Cache read | Cache write | Output | Final context |
|---|---|---|---|---|---|---|---|---|
| `aa0cba18` (current) | 10.8 h | 119 | 417 | $10.70 | 49.8M | 0.38M | 152k | 183k of 1M |
| `13cd3ad1` | 1.7 h | 56 | 189 | $5.91 | 3.2M | 0.15M | 16k | 174k |
| `d884cbe8` | 32.7 h | 324 | ~880 | $20.43 | n/a | n/a | n/a | 109k |

Input tokens outside the cache are noise (768 and 42). The cost is more than 80% cache read by volume, so the cost tracks how many model calls ran against a long transcript.

Cost per model call, `aa0cba18`: $10.70 / 417 = about $0.026. Average cache read per call, `aa0cba18`: 49.8M / 417 = about 119k tokens. At a typical notice turn the transcript is 100-180k tokens, and a turn averages 3 calls, so a notice turn re-reads about 0.35-0.5M cache tokens (est) before it does anything.

## Turns by trigger (turn = one `response_id`; trigger = user message before it)

| Trigger | `aa0cba18` | `13cd3ad1` | `d884cbe8` |
|---|---|---|---|
| Owner message | 40 | 6 | 58 |
| `[System: session ... ended its turn` subscription notice | 35 | 48 | 123 |
| `Supervisor:` notice | 39 | 0 | 0 |
| Background task / harness reminder | 1 | 0 | 49 |
| No user message found (continuation or merged trigger) | 5 | 2 | 94 |
| Total turns | 119 | 56 | 324 |
| Notice-triggered share | 62% (74) | 86% (48) | 38% (123) |

`Supervisor:` kinds in `aa0cba18`: 25 `turn ended, quiet <n>s`, 8 turn ended with no quiet suffix (2 DONE, 2 USER NEEDED, 4 other), 4 archived, 1 blocked on a prompt, 0 failed, 0 PARKED. The 6 of 38 notices that repeat the same last message for the same session are pure duplicates. The two predecessors predate the supervisor and ran on subscription notices alone.

## Notice-triggered turns: what they do

`aa0cba18`, 74 notice turns (35 subscription + 39 supervisor), per trigger kind:

| Kind | Turns | Tool calls | Board rewrite + git push | `status` call | Report read | Ended "no change" or no tools |
|---|---|---|---|---|---|---|
| subscription | 35 | 88 | 17 | 33 | 7 | 16 |
| sup quiet | 25 | 42 | 17 | 4 | 10 | 6 |
| sup turn ended (DONE/USER NEEDED/other) | 8 | 12 | 7 | 1 | 2 | 1 |
| sup archived | 4 | 2 | 1 | 0 | 0 | 4 |
| sup prompt | 1 | 2 | 0 | 0 | 0 | 0 |
| All notice turns | 73 | 146 | 42 | 38 | 19 | 27 |

For comparison, 40 owner turns used 150 tool calls (3.75 per turn) against 2.0 per notice turn. Notice turns are cheaper each but 1.8x as many.

`13cd3ad1`: 48 subscription turns, 95 calls, 19-21 board + push, 45 `status`, 9 report reads, 12 no-change. `d884cbe8`: 123 subscription turns, 226 calls, 83 `status`, 14 report reads, 12 with no tools; the board commit pattern was not used there (1 push), so its routine turns are cheaper.

Two bounds on "routine" (a notice turn the owner needed no word from):

- Strict: the reply says "no change" or the turn used no tools. 27 of 73 turns.
- Loose: strict, or 3 or fewer tool calls (a status, a board line, a commit). 66 of 73 turns. Many of these still reply with a one-line update the owner reads, so loose overstates what can be silent. Treat it as the ceiling.

The owner asked for exactly this at 1792478511: "you don't need to wake up, make a turn sending all the context, and report on just finished verifier rounds, or 'No change: ...'".

## Share of model calls (proxy for tokens and cost), `aa0cba18` and `13cd3ad1`

| | `aa0cba18` | `13cd3ad1` |
|---|---|---|
| Model calls total | 417 | 189 |
| Owner turns | 190 (46%) | 44 (23%) |
| All notice turns | 219 (53%) | 143 (76%) |
| Strict routine notice turns | 48 (11.5%) | 27 (14%) |
| Loose routine notice turns | 167 (40%) | 120 (63%) |

## Estimate (est)

Allocation assumption: cost per call is flat across the session. Context grows from 0 to 183k and notices are spread evenly through it, so this is fair on average; a late-session notice costs more than an early one.

Current session `aa0cba18`, $10.70:

| Scenario | Routine turns removed | Share of cost | Saving |
|---|---|---|---|
| Deterministic handler, strict set | 27 turns, 48 calls | 11.5% | about $1.2 |
| Deterministic handler, loose set | 66 turns, 167 calls | 40% | about $4.3 |
| Haiku triage (about 3.5k tokens, no transcript, about $0.005 per call at $1/M in), strict | removes $1.2, adds 27 x $0.005 = $0.14 | net 10% | about $1.1 |
| Haiku triage, loose | removes $4.3, adds 66 x $0.005 = $0.33 | net 37% | about $4.0 |
| Skip the 6 duplicate notices only (zero risk) | 6 turns, about 15 calls | about 3.6% | about $0.4 |

Predecessor `13cd3ad1` ($5.91, notice-heavy): strict 14% (about $0.8), loose 63% (about $3.7).

So the honest range for the current CoS is 10-40% of session cost, mid-point near 25%. A session whose work is mostly notices, as `13cd3ad1` was, can reach 60%. Note the rest of the cost, 46% owner turns plus the non-routine notice turns that report a landed PR, a USER NEEDED or a prompt, stays with Opus.

A Haiku call and a deterministic handler differ little in saving; the Haiku call's main value is judging which notices are routine, which is the part a deterministic rule needs a stable `last message` format for. Once a notice kind is known routine, the board line and push need no model.

## Per-turn context risk

Each wake re-reads the whole transcript (119k average, 183k at the end, 1M window). The cost of one notice turn is dominated by that read rather than by the tool work, so reducing wakes beats trimming each wake. A no-tool reply still costs one full call (about $0.026).

## Caveats

- Cost is not decomposed by token type here because the API totals do not reconcile with list pricing across sessions (the two sessions differ by an inconsistent factor), so use the call-count allocation, not price arithmetic.
- Classification of board commit, report read and `status` is by regex on tool-call arguments (`board.md` write plus `git ... push`; `omnigent_agent.py status`; `cat|sed|head` of a path containing `report`). Expect a few misses either way.
- "No user message found" turns (5 / 2 / 94) are a split of tool loops by `response_id` or triggers merged into one message; `d884cbe8`'s 94 are unexplained.
- Predecessor sessions ran Codex and Claude mixes; only `aa0cba18` has the `Supervisor:` notices.

## Re-run

```sh
S=/Users/zarz/dev/agents/agent-skills/engineering/skills/orchestrating-agents/scripts
# fetch: auth through omnigent_agent.Omnigent (token from ~/.omnigent/config.yaml server)
python3 - <<'PY'
import sys,json; sys.path.insert(0,'/Users/zarz/dev/agents/agent-skills/engineering/skills/orchestrating-agents/scripts')
import omnigent_agent as o; c=o.Omnigent()
for s in ['aa0cba1850bb4105a19d894d3b16f400','13cd3ad1ed8f4c09992a4ba2bcc32f7a','d884cbe8a7444e8b83cf13813ee1cad9']:
    json.dump(c.call('GET',f'/v1/sessions/{s}'),open(f'{s}.sess.json','w'))      # totals
    out=[];after=None
    while True:  # items: limit 100, order=asc, after=<last_id>, stop when has_more is false
        r=c.call('GET',f'/v1/sessions/{s}/items?limit=100&order=asc'+(f'&after={after}' if after else ''))
        out+=r['data']; after=r['last_id']
        if not r['has_more']: break
    json.dump(out,open(f'{s}.all.json','w'))
PY
```

Then group items by `response_id` into turns (a turn's trigger is the user messages since the last turn). Classify the user text by prefix: `Supervisor:` (kind from `quiet`, `blocked on a prompt`, `archived`, first word of `last message:`), `[System: session`, `<task-notification>`, else owner. Per turn, count `function_call` items and regex their `arguments`. Model calls = calls + 1. Shares = sum of model calls per class / total. `GET /v1/usage` and the `omnigent-telemetry` script give only session-tree cost, so they add nothing at turn level.
