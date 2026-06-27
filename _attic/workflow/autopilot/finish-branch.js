export const meta = {
  name: 'autopilot-finish-branch',
  description: 'Finish a development branch: verify, HARD-GATE leak-scan the net diff, squash to one clean commit, then either open a PR (new) or push + comment an existing PR (increment). Vendored from trinity finish-branch, generalized (repoRoot arg) and extended with increment/update-PR support. The leak scan runs every time and cannot be skipped.',
  whenToUse: 'Composed by the autopilot engine at finish. Args: {repoRoot, base?, testCmd?, allowlist?, increment?, iterationNote?, title?}.',
  phases: [{ title: 'Verify' }, { title: 'Scan' }, { title: 'Finish' }],
}

const a = typeof args === 'string' ? JSON.parse(args) : (args || {})
const REPO = a.repoRoot || '.'
const BASE = a.base || 'main'
const TEST_CMD = a.testCmd || ''
const ALLOW = Array.isArray(a.allowlist) ? a.allowlist : []
const INCREMENT = !!a.increment
const ITER_NOTE = a.iterationNote || ''
const TITLE = a.title || ''

// ============================ 1. Verify ================================
phase('Verify')
const VERIFY = { type: 'object', additionalProperties: false, required: ['passed', 'output'],
  properties: { passed: { type: 'boolean' }, output: { type: 'string' } } }
if (TEST_CMD) {
  const v = await agent(
    `From ${REPO}, run the project's verification command EXACTLY:\n  ${TEST_CMD}\n` +
    `Report passed=true only if every command in the chain exits 0. Return the last ~30 lines of output. Do not edit any files.`,
    { phase: 'Verify', label: 'verify-tests', schema: VERIFY })
  if (!v || !v.passed) { log('Tests failed -- stopping before scan/PR.'); return { stopped: 'tests-failed', output: v && v.output } }
} else {
  log('No testCmd provided -- skipping test verification (caller asserts tests pass).')
}

// ============================ 2. Scan (hard gate) ======================
phase('Scan')
const SCAN = { type: 'object', additionalProperties: false, required: ['clean', 'findings'],
  properties: {
    clean: { type: 'boolean' },
    findings: { type: 'array', items: { type: 'object', additionalProperties: false,
      required: ['kind', 'file', 'line', 'excerpt'],
      properties: { kind: { type: 'string' }, file: { type: 'string' }, line: { type: 'string' }, excerpt: { type: 'string' } } } },
    notes: { type: 'string' },
  } }
const allowNote = ALLOW.length
  ? `ALLOWLIST (do NOT report matches of these regexes -- already vetted/public): ${JSON.stringify(ALLOW)}.`
  : 'No allowlist provided.'
const scan = await agent(
  `Security + sensitive-data leak scan. The branch will be published, so review the NET diff that will go public:\n` +
  `  cd ${REPO} && git diff ${BASE}...HEAD\n` +
  `Inspect ONLY added (\`+\`) lines. ${allowNote}\n\n` +
  `Flag, reading both deterministically and semantically:\n` +
  `1. Secrets/credentials: private keys ('-----BEGIN .*PRIVATE KEY-----'), AWS keys (AKIA[0-9A-Z]{16}), bearer/api tokens, anything matching '(api[_-]?key|secret|token|password|passwd|client_secret)\\s*[:=]', .env contents.\n` +
  `2. PII: emails tied to real people, account identifiers, anything that identifies a real individual or account.\n` +
  `3. Anything the project's own rules (CLAUDE.md / .claude/rules) forbid publishing -- e.g. real financial figures (balances, NAV, P&L, position amounts), currency-formatted amounts.\n\n` +
  `For each real leak add a finding with kind, file, line, and a REDACTED excerpt (mask the sensitive value). clean=true ONLY if zero findings after the allowlist. When uncertain whether something is a real secret vs a synthetic/test value, REPORT it (fail closed). Do not edit files.`,
  { phase: 'Scan', label: 'leak-scan', schema: SCAN })
if (!scan || !scan.clean) {
  const n = (scan && scan.findings) || []
  log(`Leak scan BLOCKED publish: ${n.length} finding(s).`)
  return { stopped: 'leak-scan-blocked', findings: n, notes: scan && scan.notes }
}
log('Leak scan clean -- proceeding to squash + publish.')

// ============================ 3. Finish ================================
phase('Finish')
const FINISH = { type: 'object', additionalProperties: false, required: ['ok'],
  properties: { ok: { type: 'boolean' }, branch: { type: 'string' }, commit: { type: 'string' },
    prUrl: { type: 'string' }, updated: { type: 'boolean' }, output: { type: 'string' } } }

const publishStep = INCREMENT
  ? `5. This is an INCREMENT on an existing PR. Find the open PR for "$BRANCH": \`gh pr view "$BRANCH" --json url,number\`.\n` +
    `   - If a PR exists: it is already updated by the force-push in step 3. Post a comment summarizing this iteration: \`gh pr comment "$BRANCH" --body ${JSON.stringify(ITER_NOTE || 'Updated with the latest iteration.')}\`. Set updated=true and prUrl to that PR's url.\n` +
    `   - If NO PR exists (edge case): open one as in the non-increment path. Set updated=false.`
  : `5. Open a PR: \`gh pr create --base ${BASE} --head "$BRANCH" ${TITLE ? `--title ${JSON.stringify(TITLE)}` : '--title "<concise title from the diff>"'} --body "<Summary bullets + Test Plan checklist; describe behavior generically, no secrets or sensitive data>"\`. Set updated=false and prUrl to the new PR url.`

const finish = await agent(
  `Finish and publish the current branch from ${REPO}. The diff was already verified and leak-scanned clean; publish ONLY that net diff (no dirty intermediate history).\n\n` +
  `1. Capture: BRANCH=$(git rev-parse --abbrev-ref HEAD). Refuse and return ok=false if BRANCH is "${BASE}" or "master" or "HEAD".\n` +
  `2. Collapse the branch to ONE clean commit so intermediate commits never reach the remote:\n` +
  `   git reset --soft ${BASE}\n` +
  `   (reset --soft keeps the index = the branch's cumulative tree and leaves unrelated unstaged changes OUT of the commit -- do NOT 'git add -A' or 'git commit -a'). Inspect \`git status\` and \`git diff --cached --stat\`, then write a concise commit message from the staged diff (imperative subject, short body, no emojis, no secrets/sensitive data). End the body with:\n` +
  `   Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>\n` +
  `   git commit -m "<your message>"\n` +
  `3. Push: \`git push -u origin "$BRANCH"\`; if the remote branch already exists, use \`git push --force-with-lease -u origin "$BRANCH"\` (the single squashed commit is the source of truth).\n` +
  `4. (no-op placeholder)\n` +
  `${publishStep}\n` +
  `Return ok, branch, commit (short hash), prUrl, updated, and key command output. If any git/gh step fails, stop and return ok=false with the error.`,
  { phase: 'Finish', label: 'squash-publish', schema: FINISH, agentType: 'executor' })

return { verify: 'passed', scan: 'clean', finish }
