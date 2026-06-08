export const meta = {
  name: 'polish-diff',
  description: 'Review (correctness) then simplify (quality) a scoped working-tree diff in a feedback loop, gated on a verify command. Only edits the named files.',
  whenToUse: 'After a scoped code change, to run a correctness review then a quality/simplify pass, apply fixes, and re-verify in a loop until clean. Args: {files: string[], verifyCmd: string, baseRef?: string, maxIters?: number}. Safe to run alongside another agent as long as files[] does not overlap their work.',
  phases: [
    { title: 'Review' },
    { title: 'Simplify' },
    { title: 'Verify' },
  ],
}

// --- inputs -------------------------------------------------------------
// args may arrive as an object or as a JSON-encoded string depending on caller.
const a = typeof args === 'string' ? JSON.parse(args) : (args || {})
const files = (a && a.files) || []
const verifyCmd = (a && a.verifyCmd) || 'true'
const baseRef = (a && a.baseRef) || 'HEAD'
const maxIters = (a && a.maxIters) || 3

if (!files.length) {
  log('No files in args.files — nothing to polish.')
  return { error: 'no files provided', applied: [] }
}

const fileList = files.join(' ')
const diffCmd = `git diff ${baseRef} -- ${fileList}`

// --- schemas ------------------------------------------------------------
const FINDINGS = {
  type: 'object',
  additionalProperties: false,
  required: ['findings'],
  properties: {
    findings: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['file', 'description', 'severity'],
        properties: {
          file: { type: 'string' },
          line: { type: 'string', description: 'line number or range, best-effort' },
          description: { type: 'string', description: 'what is wrong/improvable and the concrete fix' },
          severity: { type: 'string', enum: ['must-fix', 'nice-to-have'] },
        },
      },
    },
  },
}

const APPLY = {
  type: 'object',
  additionalProperties: false,
  required: ['applied', 'summary'],
  properties: {
    applied: { type: 'array', items: { type: 'string' } },
    summary: { type: 'string' },
  },
}

const VERIFY = {
  type: 'object',
  additionalProperties: false,
  required: ['pass', 'output'],
  properties: {
    pass: { type: 'boolean' },
    output: { type: 'string', description: 'tail of command output, especially errors' },
  },
}

// --- loop: review -> simplify -> apply -> verify ------------------------
const appliedLog = []

for (let iter = 1; iter <= maxIters; iter++) {
  log(`Iteration ${iter}/${maxIters}: reviewing scoped diff`)

  phase('Review')
  const review = await agent(
    `CORRECTNESS code review, scoped ONLY to the change in these files: ${fileList}.\n` +
    `Run \`${diffCmd}\` to see the change; read surrounding code for context.\n` +
    `Report only correctness bugs, logic errors, missing cases, broken types, or behavioral regressions INTRODUCED BY THIS DIFF. ` +
    `Do NOT report pre-existing issues outside the diff, and do NOT report style/simplification (separate pass). ` +
    `Give file, line, concrete fix, severity. If the diff is correct, return an empty findings array.`,
    { phase: 'Review', label: `review:iter${iter}`, schema: FINDINGS, agentType: 'reviewer' }
  )

  phase('Simplify')
  const simplify = await agent(
    `QUALITY pass (reuse / simplification / efficiency / altitude), scoped ONLY to the change in these files: ${fileList}.\n` +
    `Run \`${diffCmd}\` to see the change; read surrounding code for context.\n` +
    `Suggest ways to make the CHANGED code simpler or reuse existing helpers/patterns WITHOUT changing behavior. ` +
    `Only touch code in this diff (or what is directly required to simplify it). Do NOT hunt for bugs. ` +
    `Give file, line, concrete edit, severity. If nothing to improve, return an empty findings array.`,
    { phase: 'Simplify', label: `simplify:iter${iter}`, schema: FINDINGS, agentType: 'reviewer' }
  )

  const actionable = [...review.findings, ...simplify.findings]
  if (!actionable.length) {
    log(`Iteration ${iter}: no findings — converged.`)
    break
  }

  phase('Verify')
  const applyList = actionable
    .map((f, i) => `${i + 1}. [${f.severity}] ${f.file}${f.line ? ':' + f.line : ''} -- ${f.description}`)
    .join('\n')

  log(`Iteration ${iter}: applying ${actionable.length} finding(s)`)
  const apply = await agent(
    `Apply ONLY these reviewed changes to the named files (${fileList}) using Edit/MultiEdit. ` +
    `Do not touch any other file and make no unrelated changes.\n\nChanges:\n${applyList}`,
    { phase: 'Verify', label: `apply:iter${iter}`, schema: APPLY, agentType: 'executor' }
  )
  appliedLog.push(...apply.applied)

  const verify = await agent(
    `Run this command and report whether it succeeded (exit 0):\n${verifyCmd}\n` +
    `pass=true only if exit code is 0. Include the tail of output (especially any errors).`,
    { phase: 'Verify', label: `verify:iter${iter}`, schema: VERIFY, agentType: 'executor' }
  )

  if (!verify.pass) {
    log(`Iteration ${iter}: verify FAILED -- attempting fix within scoped files`)
    const fix = await agent(
      `The verify command \`${verifyCmd}\` failed after edits to ${fileList}:\n${verify.output}\n` +
      `Fix the cause within the named files ONLY so the command passes, then re-run \`${verifyCmd}\` to confirm. ` +
      `If you cannot fix it within these files, revert your edits to them and explain.`,
      { phase: 'Verify', label: `fix:iter${iter}`, schema: APPLY, agentType: 'executor' }
    )
    appliedLog.push(...fix.applied)
  } else {
    log(`Iteration ${iter}: verify passed`)
  }
}

return { files, applied: appliedLog }
