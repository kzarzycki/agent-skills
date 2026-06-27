export const meta = {
  name: 'autopilot-engine',
  description: 'autopilot engine: plan -> plan-review -> execute -> code-review -> verify -> finish, with flow tracking, retries, and resume.',
  phases: [
    { title: 'Track' }, { title: 'Plan' }, { title: 'PlanReview' },
    { title: 'Execute' }, { title: 'CodeReview' }, { title: 'Verify' }, { title: 'Finish' },
  ],
}

// ---- args --------------------------------------------------------------
const A = typeof args === 'string' ? JSON.parse(args) : (args || {})
const ITEM = A.itemDir
const DATE = A.date
const BASE = A.base || 'main'
const REPO = A.repoRoot || '.'
const SKILL_DIR = A.skillDir || '.'
const MAX = A.maxIters || 3
const DRY = !!A.dryRun
const INCREMENT = !!A.increment
const ITER = A.iteration || 1
if (!ITEM || !DATE) { log('autopilot-engine: missing itemDir/date'); return { error: 'missing args' } }

// ---- inlined pure logic (mirror of lib/*; verified by engine-inline.test.js)
// <inline:waves>
function deriveWaves(tasks) {
  const byId = new Map(tasks.map((t) => [t.id, t]))
  for (const t of tasks) for (const d of t.deps || []) if (!byId.has(d)) throw new Error(`unknown dependency: ${d} (task ${t.id})`)
  const placed = new Set(); const waves = []; let guard = tasks.length + 1
  while (placed.size < tasks.length) {
    if (guard-- <= 0) throw new Error('dependency cycle detected')
    const ready = tasks.filter((t) => !placed.has(t.id) && (t.deps || []).every((d) => placed.has(d)))
    if (!ready.length) throw new Error('dependency cycle detected')
    const wave = []; const usedFiles = new Set()
    for (const t of ready) {
      const scope = t.fileScope || []
      if (scope.some((f) => usedFiles.has(f))) continue
      wave.push(t.id); scope.forEach((f) => usedFiles.add(f))
    }
    wave.forEach((id) => placed.add(id)); waves.push(wave)
  }
  return waves
}
// </inline:waves>

// <inline:rules>
function ancestorDirs(filePath) {
  const parts = filePath.split('/'); parts.pop(); const dirs = ['']; let acc = ''
  for (const p of parts) { acc = acc ? `${acc}/${p}` : p; dirs.push(acc) }
  return dirs
}
function gatherRulePaths(touchedFiles, repoFiles) {
  const repo = new Set(repoFiles); const claudeMd = new Set()
  for (const f of touchedFiles) for (const dir of ancestorDirs(f)) {
    const c = dir ? `${dir}/CLAUDE.md` : 'CLAUDE.md'; if (repo.has(c)) claudeMd.add(c)
  }
  if (repo.has('CLAUDE.md')) claudeMd.add('CLAUDE.md')
  const rules = repoFiles.filter((p) => p.startsWith('.claude/rules/'))
  return { claudeMd: [...claudeMd], rules }
}
// </inline:rules>

// ---- flow track() kit (from flow/references/workflow.md) ---------------
const STATUS = ['not_started', 'researching', 'planning', 'in_progress', 'blocked', 'done']
const TRACK = { type: 'object', additionalProperties: false,
  required: ['logged', 'status', 'priorStatusOk'],
  properties: { logged: { type: 'boolean' }, status: { type: 'string', enum: STATUS },
    priorStatusOk: { type: 'boolean' }, note: { type: 'string' } } }
async function track(d) {
  if (DRY) { log(`[dry] track ${d.status}: ${d.note || ''}`); return { logged: true, status: d.status, priorStatusOk: true } }
  const v = await agent(
    `Mechanical bookkeeping ONLY on ${ITEM}/ITEM.md and .work/log.md. No thinking, no other edits.\n` +
    `${d.from ? `0. read the "## Status:" line; if it is not exactly "${d.from}", set priorStatusOk:false and STOP -- change nothing. Else priorStatusOk:true.` : 'Set priorStatusOk:true.'}\n` +
    `1. append "- ${DATE} [${d.status}] ${d.note}" to .work/log.md AND ITEM.md "## Log".\n` +
    `2. tick these "## Progress" checkboxes (- [ ] -> - [x]): ${JSON.stringify(d.check || [])}\n` +
    `3. set the "## Status:" line to exactly: ${d.status}\n` +
    `Use the token "${d.status}" verbatim. Return what you did.`,
    { phase: 'Track', label: `track:${d.status}`, schema: TRACK, model: 'haiku' })
  if (d.from && !v.priorStatusOk) throw new Error(`prior-status mismatch: expected ${d.from} before ${d.status}`)
  if (!v.logged) throw new Error(`tracking failed @ ${d.status}: ${v.note || ''}`)
  return v
}

// ---- halt helper -------------------------------------------------------
async function halt(phaseName, reason, detail) {
  await track({ status: 'blocked', note: `${phaseName}: ${reason}` })
  if (!DRY) await agent(
    `Write ${ITEM}/blocker.md with: phase=${phaseName}, reason=${reason}, and this detail verbatim:\n${detail || ''}\n` +
    `Also write/update ${ITEM}/run.json keeping any workflowRunId and setting phaseCursor=${JSON.stringify(phaseName)}.`,
    { phase: 'Track', label: 'write-blocker', schema: { type: 'object', additionalProperties: false, required: ['written'], properties: { written: { type: 'boolean' } } } })
  // The Workflow completion notification returns this object to the caller, so
  // the user is informed of the halt even without a separate push notification.
  log(`NOTIFY: autopilot halted at ${phaseName} -- ${reason}`)
  return { halted: phaseName, reason }
}

// ---- rules bundle + phase-file loader ----------------------------------
// Promise-cached so concurrent callers (execute runs rulesFor inside parallel())
// share one in-flight read instead of each spawning a duplicate agent.
let _repoListPromise = null
function ensureRepoList() {
  if (!_repoListPromise) {
    _repoListPromise = DRY ? Promise.resolve([]) : agent(
      `From ${REPO}, run \`git ls-files\` and return (in "paths") every tracked path that is either a CLAUDE.md (at any depth) or under .claude/rules/. Relative to repo root.`,
      { phase: 'Track', label: 'list-rule-files', schema: { type: 'object', additionalProperties: false, required: ['paths'], properties: { paths: { type: 'array', items: { type: 'string' } } } }, model: 'haiku' }).then((r) => r.paths)
  }
  return _repoListPromise
}
const _bundleCache = new Map() // key: sorted wanted paths -> Promise<concatenated contents>
async function rulesFor(touchedFiles) {
  const repoFiles = await ensureRepoList()
  const { claudeMd, rules } = gatherRulePaths(touchedFiles || [], repoFiles)
  const wanted = [...claudeMd, ...rules]
  if (!wanted.length) return '(no project rule files found)'
  if (DRY) return '(dry-run rules bundle)'
  const key = [...wanted].sort().join('\n')
  // Across a wave, many tasks resolve to the same rule files; read each distinct set once.
  if (!_bundleCache.has(key)) {
    _bundleCache.set(key, agent(
      `From ${REPO}, read these files and return their concatenated contents (each preceded by "### <path>") in "text":\n${wanted.join('\n')}`,
      { phase: 'Track', label: 'read-rules', schema: { type: 'object', additionalProperties: false, required: ['text'], properties: { text: { type: 'string' } } }, model: 'haiku' }).then((r) => r.text))
  }
  return _bundleCache.get(key)
}
async function readPhase(name) {
  const r = await agent(
    `Read the file ${SKILL_DIR}/phases/${name}.md and return its exact contents in "text". Do not edit anything.`,
    { phase: 'Track', label: `read:${name}`, schema: { type: 'object', additionalProperties: false, required: ['text'], properties: { text: { type: 'string' } } }, model: 'haiku' })
  return r.text.replaceAll('{{ITEM}}', ITEM)
}

// ---- schemas -----------------------------------------------------------
const PLAN = { type: 'object', additionalProperties: false,
  required: ['tasks', 'verifyCmd'],
  properties: {
    verifyCmd: { type: 'string' },
    tasks: { type: 'array', items: { type: 'object', additionalProperties: false,
      required: ['id', 'desc', 'deps', 'fileScope', 'acceptance'],
      properties: {
        id: { type: 'string' }, desc: { type: 'string' },
        deps: { type: 'array', items: { type: 'string' } },
        fileScope: { type: 'array', items: { type: 'string' } },
        acceptance: { type: 'array', items: { type: 'string' } },
      } } },
  } }
const CRITIC = { type: 'object', additionalProperties: false,
  required: ['concerns'],
  properties: { concerns: { type: 'array', items: { type: 'object', additionalProperties: false,
    required: ['severity', 'issue'],
    properties: {
      severity: { type: 'string', enum: ['blocker', 'advisory'] },
      issue: { type: 'string' },
      taskId: { type: 'string' },
    } } } } }
const IMPL = { type: 'object', additionalProperties: false,
  required: ['filesChanged', 'summary'],
  properties: { filesChanged: { type: 'array', items: { type: 'string' } }, summary: { type: 'string' } } }
const RECONCILE = { type: 'object', additionalProperties: false, required: ['pass', 'conflict'],
  properties: { pass: { type: 'boolean' }, conflict: { type: 'boolean' }, files: { type: 'array', items: { type: 'string' } }, output: { type: 'string' } } }
const FINDINGS = { type: 'object', additionalProperties: false, required: ['findings'],
  properties: { findings: { type: 'array', items: { type: 'object', additionalProperties: false,
    required: ['file', 'description', 'confidence'],
    properties: { file: { type: 'string' }, line: { type: 'string' }, description: { type: 'string' }, confidence: { type: 'number' } } } } } }
const VERDICT = { type: 'object', additionalProperties: false, required: ['verdict', 'checks'],
  properties: { verdict: { type: 'string', enum: ['pass', 'fail'] },
    checks: { type: 'array', items: { type: 'object', additionalProperties: false,
      required: ['criterion', 'pass'], properties: { criterion: { type: 'string' }, pass: { type: 'boolean' }, evidence: { type: 'string' } } } } } }
const APPLIED = { type: 'object', additionalProperties: false, required: ['applied'], properties: { applied: { type: 'array', items: { type: 'string' } } } }

// ---- phases ------------------------------------------------------------
async function runPlan() {
  if (DRY) return { tasks: [{ id: 't1', desc: 'demo', deps: [], fileScope: ['x.js'], acceptance: ['works'] }, { id: 't2', desc: 'demo2', deps: ['t1'], fileScope: ['y.js'], acceptance: ['works'] }], verifyCmd: 'true' }
  // One writable agent both produces the structured plan AND writes plan.md, so the
  // full plan never crosses an extra agent boundary just to be rendered to disk.
  let prompt = await readPhase('plan')
  if (INCREMENT) prompt += `\n\nINCREMENT (iteration ${ITER}): ${ITEM}/spec.md has a new "## Iteration ${ITER}" section and ${ITEM}/plan.md already holds prior tasks. Append ONLY new tasks covering the iteration-${ITER} requirements; do NOT repeat or re-run completed work. Return ONLY the new iteration-${ITER} tasks in "tasks" (with the current verifyCmd).`
  prompt += `\n\nAfter deciding the tasks, WRITE them to ${ITEM}/plan.md (${INCREMENT ? `APPEND a "## Iteration ${ITER}" section; do not rewrite earlier content` : 'create/overwrite'}) using the Write/Edit tool: "# Implementation Plan", then per task a "## <id>" heading with bullets desc/deps/fileScope/acceptance, ending with a line "verifyCmd: <cmd>". Then RETURN the same tasks + verifyCmd as the structured result.`
  return await agent(prompt, { phase: 'Plan', label: 'plan', schema: PLAN, agentType: 'executor' })
}

async function runPlanReview(plan) {
  if (DRY) return { plan, verdict: 'pass', critiques: [] }
  const lenses = ['gaps', 'over-engineering', 'testability']
  const tmpl = await readPhase('plan-review')
  let cur = plan
  // Revise plan.md AND return the updated structured tasks, so revisions actually
  // reach execution (execute runs the returned object, not plan.md on disk).
  const revise = (concerns, iter, kind) => agent(
    `Revise ${ITEM}/plan.md (using Edit/Write) to address these ${kind} concern(s), preserving the structured task fields (id, deps, fileScope, acceptance).` +
    (kind === 'advisory' ? ' Apply where reasonable; this is the only pass for these.' : '') +
    `\nConcerns:\n${concerns.map((c, i) => `${i + 1}. ${c.issue}`).join('\n')}` +
    `\n\nThen RETURN the COMPLETE updated plan as structured tasks + verifyCmd -- this return value is what gets executed.`,
    { phase: 'PlanReview', label: `revise-${kind}:${iter}`, schema: PLAN, agentType: 'executor' })
  for (let iter = 1; iter <= MAX; iter++) {
    const verdicts = await parallel(lenses.map((lens) => () =>
      agent(tmpl.replaceAll('{{LENS}}', lens),
        { phase: 'PlanReview', label: `critic:${lens}:${iter}`, schema: CRITIC, agentType: 'reviewer' })))
    const concerns = verdicts.filter(Boolean).flatMap((v) => v.concerns)
    const blockers = concerns.filter((c) => c.severity === 'blocker')
    const advisories = concerns.filter((c) => c.severity === 'advisory')
    // Gate on BLOCKERS only (any lens, any count). Advisories never block: they get
    // one best-effort pass, then the plan is accepted. A blocker = would make the
    // implementation wrong, incomplete, or build something the spec didn't ask for.
    if (!blockers.length) {
      if (advisories.length) { log(`plan-review: 0 blockers, ${advisories.length} advisory; applying once, then accepting.`); cur = await revise(advisories, iter, 'advisory') }
      return { plan: cur, verdict: 'pass', critiques: advisories.map((c) => c.issue) }
    }
    if (iter === MAX) {
      // A genuine blocker survived MAX adversarial rounds -> halt for human input
      // (the spec's bounded-retry -> halt). This fires only on real blockers, never nits.
      return { plan: cur, verdict: 'revise', critiques: blockers.map((c) => c.issue) }
    }
    log(`plan-review round ${iter}: ${blockers.length} blocker(s); revising.`)
    cur = await revise(blockers, iter, 'blocker')
  }
  return { plan: cur, verdict: 'pass', critiques: [] }
}

async function runExecute(plan) {
  const waves = deriveWaves(plan.tasks)
  const byId = new Map(plan.tasks.map((t) => [t.id, t]))
  if (DRY) { waves.forEach((w, i) => log(`[dry] wave ${i + 1}: ${w.join(', ')}`)); return { changedFiles: plan.tasks.flatMap((t) => t.fileScope) } }
  const tmpl = await readPhase('execute')
  const changed = []
  // Tasks run SEQUENTIALLY on the shared feature-branch working tree (no per-task
  // worktrees). deriveWaves still validates the DAG and gives topological order;
  // running in that order means each task sees every prior task's edits, so a
  // dependent task compiles against its dependencies. (Per-task worktrees branched
  // `fresh` from the base broke this: a downstream task's tree lacked its deps,
  // forcing executors to re-create dependency code, which then collided at merge.)
  // A tightly-coupled change often does not fully verify until ALL tasks land, so
  // the per-task verify is best-effort and a single integrated verify+commit runs
  // at the end.
  const order = waves.flat()
  for (const id of order) {
    log(`Execute task ${id}`)
    const t = byId.get(id)
    const bundle = await rulesFor(t.fileScope)
    const prompt = tmpl
      .replaceAll('{{TASK_DESC}}', t.desc)
      .replaceAll('{{FILE_SCOPE}}', t.fileScope.join(' '))
      .replaceAll('{{VERIFY_CMD}}', plan.verifyCmd)
      .replaceAll('{{RULES_BUNDLE}}', bundle)
    const r = await agent(prompt, { phase: 'Execute', label: `impl:${id}`, schema: IMPL, agentType: 'executor' })
    if (r && r.filesChanged) changed.push(...r.filesChanged)
  }
  // Integrated verify + commit on the feature branch (single shared tree, nothing to merge).
  const done = await agent(
    `In ${REPO} on the current feature branch, run \`${plan.verifyCmd}\`. If it fails, make the minimal cross-file fixes needed to get it to exit 0 (tasks were implemented one file at a time and may have small integration gaps). Then stage the changed SOURCE files and commit with one concise message (no emojis). Do NOT push. Do NOT use \`git add -A\` or \`git add .\` -- stage only the changed source files, never .work/ or unrelated untracked files. Report pass=true only if verify exited 0 AND you committed.`,
    { phase: 'Execute', label: 'verify-commit', schema: RECONCILE, agentType: 'executor' })
  if (!done.pass) throw new Error(`execute verify/commit failed: ${(done.output || '').slice(-1500)}`)
  return { changedFiles: [...new Set(changed)] }
}

async function runCodeReview(ex, plan) {
  if (DRY) return { verdict: 'pass', findings: [] }
  const tmpl = await readPhase('code-review')
  const bundle = await rulesFor(ex.changedFiles)
  const prompt = tmpl.replaceAll('{{BASE}}', BASE).replaceAll('{{RULES_BUNDLE}}', bundle)
  for (let iter = 1; iter <= MAX; iter++) {
    const review = await agent(prompt, { phase: 'CodeReview', label: `review:${iter}`, schema: FINDINGS, agentType: 'reviewer' })
    const must = review.findings.filter((f) => f.confidence >= 80)
    if (!must.length) return { verdict: 'pass', findings: [] }
    if (iter === MAX) return { verdict: 'revise', findings: must }
    await agent(
      `Apply ONLY these reviewed fixes to the named files using Edit/MultiEdit, then run \`${plan.verifyCmd}\`. ` +
      `When it passes, COMMIT the fixes onto the current feature branch (amend the existing commit, e.g. \`git commit --amend --no-edit\`, or add a small follow-up commit; no emojis, no push). ` +
      `Committing is REQUIRED: the next review round diffs against ${BASE}, so uncommitted fixes would be invisible and re-flagged. Fixes:\n` +
      must.map((f, i) => `${i + 1}. ${f.file}${f.line ? ':' + f.line : ''} -- ${f.description}`).join('\n'),
      { phase: 'CodeReview', label: `fix:${iter}`, schema: APPLIED, agentType: 'executor' })
  }
  return { verdict: 'revise', findings: [] }
}

async function runVerify(plan) {
  if (DRY) return { verdict: 'pass', checks: [] }
  const tmpl = await readPhase('verify')
  const bundle = await rulesFor(plan.tasks.flatMap((t) => t.fileScope))
  const prompt = tmpl.replaceAll('{{VERIFY_CMD}}', plan.verifyCmd).replaceAll('{{RULES_BUNDLE}}', bundle)
  for (let iter = 1; iter <= MAX; iter++) {
    const v = await agent(prompt, { phase: 'Verify', label: `verify:${iter}`, schema: VERDICT, agentType: 'reviewer' })
    if (v.verdict === 'pass') return v
    if (iter === MAX) return v
    const fails = v.checks.filter((c) => !c.pass)
    await agent(
      `Verification failed these criteria; fix the implementation so they pass, then re-run \`${plan.verifyCmd}\`:\n` +
      fails.map((c, i) => `${i + 1}. ${c.criterion} -- ${c.evidence || ''}`).join('\n'),
      { phase: 'Verify', label: `fix:${iter}`, schema: APPLIED, agentType: 'executor' })
  }
}

async function runFinish(plan) {
  if (DRY) return { prUrl: 'dry-run://pr' }
  const iterationNote = INCREMENT
    ? `Iteration ${ITER}: ${plan.tasks.map((t) => t.desc).join('; ')}`.slice(0, 500)
    : ''
  const res = await workflow({ scriptPath: `${SKILL_DIR}/finish-branch.js` }, {
    repoRoot: REPO,
    base: BASE,
    testCmd: plan.verifyCmd,
    allowlist: A.allowlist || [],
    increment: INCREMENT,
    iterationNote,
  })
  if (res && res.finish && res.finish.ok && res.finish.prUrl) return { prUrl: res.finish.prUrl }
  return { prUrl: '', stopped: (res && res.stopped) || 'finish-failed', detail: res }
}

// ---- orchestration -----------------------------------------------------
// In increment mode the item reopens from `done`/`blocked`, so the linear
// `from:` guards (which prevent double-advance on a fresh run) are dropped.
const FROM = (s) => (INCREMENT ? undefined : s)

phase('Plan')
await track({ from: FROM('planning'), status: INCREMENT ? 'in_progress' : 'planning', note: INCREMENT ? `iteration ${ITER} start` : 'plan start' })
let plan = await runPlan()

phase('PlanReview')
const pr = await runPlanReview(plan)
if (pr.verdict !== 'pass') return await halt('plan-review', 'unresolved blocker(s) after max rounds', JSON.stringify(pr.critiques))
plan = pr.plan // revisions reach execution: use the reviewed/revised structured plan
await track({ status: INCREMENT ? 'in_progress' : 'planning', check: ['Plan created', 'Plan reviewed'], note: 'plan reviewed' })

phase('Execute')
await track({ from: FROM('planning'), status: 'in_progress', note: 'execute start' })
let ex
try { ex = await runExecute(plan) }
catch (e) { return await halt('execute', 'wave failure', (e && e.message) || String(e)) }

phase('CodeReview')
const cr = await runCodeReview(ex, plan)
if (cr.verdict !== 'pass') return await halt('code-review', 'unresolved findings', JSON.stringify(cr.findings))
await track({ from: FROM('in_progress'), status: 'in_progress', check: ['Executed', 'Reviewed'], note: 'reviewed' })

phase('Verify')
const vr = await runVerify(plan)
if (vr.verdict !== 'pass') return await halt('verify', 'acceptance not met', JSON.stringify(vr.checks))
await track({ from: FROM('in_progress'), status: 'in_progress', check: ['Verified'], note: 'verified' })

phase('Finish')
const fin = await runFinish(plan)
if (!fin.prUrl) return await halt('finish', fin.stopped || 'PR not opened', JSON.stringify(fin.detail || fin))
await track({ from: FROM('in_progress'), status: 'done', check: ['Finished'], note: INCREMENT ? `iteration ${ITER} -> PR ${fin.prUrl}` : `PR ${fin.prUrl}` })

return { prUrl: fin.prUrl }
