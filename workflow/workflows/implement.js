export const meta = {
  name: 'implement',
  description: 'Build a described change in a scoped file set, then review+simplify the diff in a verify-gated loop and commit. Args: {task, files?, verifyCmd, baseRef?, maxIters?, commit?}. Pass files[] to run safely beside another agent.',
  whenToUse: 'End-to-end when you have a fix/feature to build. Commit message is generated from the diff; pass commit:false to skip committing.',
  phases: [
    { title: 'Implement' },
    { title: 'Polish' },
    { title: 'Commit' },
  ],
}

// --- inputs (args may arrive as object or JSON string) ------------------
const a = typeof args === 'string' ? JSON.parse(args) : (args || {})
const task = a.task
const files = a.files || []
const verifyCmd = a.verifyCmd || 'true'
const baseRef = a.baseRef || 'HEAD'
const maxIters = a.maxIters || 3
const doCommit = a.commit !== false // commit by default

if (!task) {
  log('No args.task provided -- nothing to implement.')
  return { error: 'no task provided' }
}

// --- 1. Implement ------------------------------------------------------
phase('Implement')
const IMPL = {
  type: 'object',
  additionalProperties: false,
  required: ['filesChanged', 'summary'],
  properties: {
    filesChanged: { type: 'array', items: { type: 'string' } },
    summary: { type: 'string' },
  },
}
const scopeNote = files.length
  ? `Restrict edits to THESE FILES ONLY: ${files.join(' ')}. Do not touch any other file -- another agent is working elsewhere in the repo.`
  : 'Keep edits tightly scoped to what the task requires, and report every file you change.'

const impl = await agent(
  `Implement this change:\n\n${task}\n\n${scopeNote}\n\n` +
  `Read what you need for context first, then make the edits with Edit/MultiEdit/Write. Do NOT commit. ` +
  `After editing, run \`${verifyCmd}\` once; if it fails, fix it within the allowed files. ` +
  `Return the list of files you changed and a one-paragraph summary.`,
  { phase: 'Implement', label: 'implement', schema: IMPL, agentType: 'executor' }
)

const polishFiles = files.length ? files : impl.filesChanged
log(`Implemented across ${polishFiles.length} file(s); handing to polish-diff`)

// --- 2. Polish (reuse polish-diff: review + simplify + verify loop) -----
phase('Polish')
let polish = null
try {
  polish = await workflow('polish-diff', { files: polishFiles, verifyCmd, baseRef, maxIters })
} catch (e) {
  log(`polish-diff step failed: ${(e && e.message) || e}`)
}

// --- 3. Commit (default on; message authored from the diff) -------------
let committed = null
if (doCommit) {
  phase('Commit')
  const COMMIT = {
    type: 'object',
    additionalProperties: false,
    required: ['committed', 'hash', 'message', 'output'],
    properties: {
      committed: { type: 'boolean' },
      hash: { type: 'string', description: 'short commit hash, or empty if not committed' },
      message: { type: 'string', description: 'the commit message you wrote' },
      output: { type: 'string' },
    },
  }
  committed = await agent(
    `Run \`${verifyCmd}\` first and proceed ONLY if it exits 0.\n` +
    `Then stage ONLY these files -- add nothing else:\n  git add ${polishFiles.join(' ')}\n` +
    `Inspect the staged diff (\`git diff --cached\`) and WRITE YOUR OWN commit message describing the change: ` +
    `a concise imperative subject line, then a short body explaining what changed and why. ` +
    `No emojis. End the body with this trailer:\n` +
    `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>\n` +
    `Commit with that message. Return committed=true, the short hash, and the message on success; ` +
    `committed=false with the error output otherwise.`,
    { phase: 'Commit', label: 'commit', schema: COMMIT, agentType: 'executor' }
  )
}

return {
  implemented: impl.summary,
  filesChanged: impl.filesChanged,
  polish,
  committed,
}
