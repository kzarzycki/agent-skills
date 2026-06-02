# Workflow mode

Run a flow item through a workflow by inlining tracking into that workflow's own
script. Given a workflow `W`, produce `W-flow`: `W`'s script with a `track()` call
at each phase boundary. `track()` is an ordinary `agent()` call, so `W-flow` runs
at the top level and `W`'s own `workflow()` calls keep their nesting budget:

```
implement-flow                 level 0   implement's stages + track()
  └─ workflow('polish-diff')   level 1   implement's own composition
```

`track()` updates the item's `ITEM.md` and `.work/log.md` after each phase, so the
item's status and log advance in step with the work.

## Inline kit

Paste at the top of `W-flow`:

```js
const A = typeof args === 'string' ? JSON.parse(args) : (args || {})
const STATUS = ['not_started','researching','planning','in_progress','blocked','done']
const TRACK = { type:'object', additionalProperties:false,
  required:['logged','status','priorStatusOk'],
  properties:{ logged:{type:'boolean'}, status:{type:'string', enum:STATUS},
               priorStatusOk:{type:'boolean'}, note:{type:'string'} } }

// log-first: append the log, then flip status last, so an interrupted run leaves
// the log ahead of status (re-runnable) rather than status ahead of the log.
async function track(d) { // d: { status, from?, check?, note }
  const v = await agent(
    `Mechanical bookkeeping ONLY on ${A.itemDir}/ITEM.md and .work/log.md. No thinking, no other edits.
     ${d.from ? `0. read the "## Status:" line; if it is not exactly "${d.from}", set priorStatusOk:false and STOP -- change nothing. Else priorStatusOk:true.` : 'Set priorStatusOk:true.'}
     1. append "- ${A.date} [${d.status}] ${d.note}" to .work/log.md AND ITEM.md "## Log".
     2. tick these "## Progress" checkboxes (- [ ] -> - [x]): ${JSON.stringify(d.check||[])}
     3. set the "## Status:" line to exactly: ${d.status}
     Use the token "${d.status}" verbatim. Return what you did.`,
    { phase:'Track', label:`track:${d.status}`, schema:TRACK, model:'haiku' })
  if (d.from && !v.priorStatusOk) throw new Error(`prior-status mismatch: expected ${d.from} before ${d.status}`)
  if (!v.logged) throw new Error(`tracking failed @ ${d.status}: ${v.note||''}`)
  return v
}
```

`track()` runs on haiku, asserts the expected prior status, writes the append-only
log before flipping status, and uses the canonical status token verbatim.

## Placement

- One `track()` after each `phase('X')`.
- `from:` is the status the item should already hold; a mismatch throws.
- `check:` ticks that phase's `## Progress` boxes.
- The final `track()` sets `status:'done'`.
- Call `track()` serially, outside `parallel()`/`pipeline()` — fan out, join, then track.

## Generate W-flow

1. Copy `W`'s script (`.claude/workflows/<W>.js`).
2. Paste the inline kit at the top.
3. Set `meta.name` to `<W>-flow`; add `{title:'Track'}` to `meta.phases`.
4. Add a `track()` at each phase boundary, threading `from:` and ending on `done`.
5. Run with `Workflow({script})`, passing `itemDir` and `date` alongside `W`'s args.

## Example: implement-flow

`implement` runs Implement / Polish / Commit and composes `polish-diff`. Inlined:

```js
export const meta = {
  name: 'implement-flow',
  description: 'implement, with flow tracking inlined',
  phases: [{title:'Track'},{title:'Implement'},{title:'Polish'},{title:'Commit'}],
}
// inline kit here

phase('Implement')
await track({ from:'planning', status:'in_progress', note:'implement start' })
const impl = await agent(/* implement's executor stage */, { phase:'Implement', schema:/*...*/ })

phase('Polish')
const polish = await workflow('polish-diff', { files:A.files, verifyCmd:A.verifyCmd })
await track({ from:'in_progress', status:'in_progress', check:['Implemented','Polished'], note:'polished + verified' })

phase('Commit')
const commit = await agent(/* implement's commit stage */, { phase:'Commit', schema:/*...*/ })
return await track({ from:'in_progress', status:'done', check:['Committed'], note:`committed ${commit.hash}` })
```

## Example: lifecycle from scratch

When no workflow fits the item, write the stages inline and place the same `track()` calls.

```js
phase('Research')
await track({ from:'not_started', status:'researching', note:'research started' })
await agent(`Research the item. Write ${A.itemDir}/research.md ending with "## RESEARCH COMPLETE".`,
            { phase:'Research', schema:/*DONE*/ })

phase('Plan')
await track({ from:'researching', status:'planning', check:['Research completed'], note:'research done' })
await agent(`Write the plan to ${A.itemDir}/plan.md ending with "## PLAN COMPLETE".`,
            { phase:'Plan', schema:/*DONE*/ })

phase('Execute')
await track({ from:'planning', status:'in_progress', check:['Plan created'], note:'plan done' })
const steps = A.steps || []
const done = await parallel(steps.map(s => () =>
  agent(`Execute step: ${s}. Append to ${A.itemDir}/execution-report.md.`, { phase:'Execute', schema:/*DONE*/ })))
await track({ from:'in_progress', status:'in_progress', check:steps.filter((_,i)=>done[i]), note:`executed ${done.filter(Boolean).length}/${steps.length}` })

phase('Verify')
await agent(`Independently verify against the plan; do not read the execution self-assessment.
            Write ${A.itemDir}/verification-report.md ending with "## VERIFICATION COMPLETE" and PASS/FAIL.`,
            { phase:'Verify', schema:/*DONE*/ })
return await track({ from:'in_progress', status:'done', check:['Verified'], note:'verified' })
```

## Constraints

- `meta` is a pure literal; spell out `phases: [...]`.
- Helpers inline; no imports.
- Pass `date` via `args` — no `Date.now()`, `Math.random()`, or argless `new Date()`.
- Re-run a generated `W-flow` with `{scriptPath, resumeFromRunId}`; cached agents return instantly.

## args

```
{ itemDir: ".work/items/<name>", date: "<today>", ...W's args }
```

`args` may arrive as an object or JSON string; the kit normalises it to `A`. `W`'s
own args ride alongside — for `implement-flow`: `task`, `files`, `verifyCmd`.
