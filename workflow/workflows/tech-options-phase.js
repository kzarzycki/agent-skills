export const meta = {
  name: 'tech-options-phase',
  description: 'Run the Tech Options phase by delegation: analyst authors/reworks 02-TECH-OPTIONS.md, a format gate checks it, two independent reviewers judge it, rework loops until pass, needs-user, or the rework cap.',
  whenToUse: 'Args: { workId: string, pluginRoot: string, instructions?: string, contentFrozen?: boolean }. Returns { status, rounds, verdicts, formatGate, artifact }. status: pass | needs-user | rework-cap-exceeded. Stateless: agents read/write work-item files only.',
  phases: [{ title: 'Author' }, { title: 'Format gate' }, { title: 'Review' }],
};

const REWORK_CAP = 2; // mirrors workflow-core/schema.js
const VERDICTS = { PASS: 'pass', NEEDS_REWORK: 'needs-rework', NEEDS_USER: 'needs-user' };

const AUTHOR_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['written', 'summary'],
  properties: { written: { type: 'boolean' }, summary: { type: 'string' } },
};

const GATE_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['toolAvailable', 'structureViolations', 'languageFindings', 'diagnostics'],
  properties: {
    toolAvailable: { type: 'boolean' },
    structureViolations: { type: 'integer' },
    languageFindings: { type: 'integer' },
    diagnostics: { type: 'array', items: { type: 'string' } },
  },
};

const REVIEW_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['verdict', 'findings'],
  properties: {
    verdict: { type: 'string', enum: Object.values(VERDICTS) },
    findings: { type: 'array', items: { type: 'string' } },
  },
};

const REVIEWERS = [
  { name: 'reuse-coverage', agentType: 'workflow:reuse-coverage-reviewer' },
  { name: 'fit-risk', agentType: 'workflow:fit-risk-reviewer' },
];

const a = typeof args === 'string' ? JSON.parse(args) : (args || {});
if (!a.workId) return { error: 'no workId provided' };
if (!a.pluginRoot) return { error: 'no pluginRoot provided (the workflow plugin dir containing contracts/)' };

const root = `.workflow/${a.workId}`;
const artifact = `${root}/02-TECH-OPTIONS.md`;
const specPath = `${root}/01-DECISION-SPEC.md`;
const mdsmithConfig = `${a.pluginRoot}/contracts/mdsmith.yml`;
const contractJson = `${a.pluginRoot}/contracts/tech-options.json`;
const reviewsDir = `${root}/_reviews/tech_options`;

const frozenRule = a.contentFrozen
  ? 'CONTENT IS FROZEN: keep every decision, option, score, and fact exactly as it is; change only shape and language (structure, tables, lists, sentence length). Record the rework in the Approval record.'
  : 'Preserve approved content unless rework findings explicitly contradict it.';

function authorPrompt(notes) {
  return `You run the Tech Options phase for work item ${a.workId}. The tech-options skill preloaded in your context is the phase contract; follow it.
Read the approved Decision Spec at ${specPath}. If ${artifact} exists, rework it in place; otherwise write it fresh (this path is your tech_options_path).
${frozenRule}
${notes ? `Rework input — address every item:\n${notes}` : ''}
If the Decision Spec is missing, stop and return written=false with the reason in summary. Do not SendMessage anyone; just write the file. Return {written, summary}.`;
}

function gatePrompt() {
  return `Run the workflow format gate. Execute exactly:
export PATH="$HOME/.local/bin:$PATH" && mdsmith check -c ${mdsmithConfig} ${artifact} 2>&1
If mdsmith is not installed, return toolAvailable=false and verify the H2 sections of ${artifact} manually against ${contractJson}, reporting mismatches as diagnostics.
Count MDS020 diagnostics as structureViolations and all other MDS* diagnostics as languageFindings. Return each diagnostic as "MDSxxx line N: message". Do not modify any file.`;
}

function reviewPrompt(reviewer) {
  return `Review ${artifact} against the Decision Spec at ${specPath}, following your reviewer checklist and the tech-options skill preloaded in your context.
Write your full review markdown to ${reviewsDir}/${reviewer.name}.md (create dirs as needed).
Return {verdict, findings}: verdict is exactly pass, needs-rework, or needs-user; findings lists each actionable defect (empty when pass).`;
}

let notes = a.instructions || '';
let formatGate = null;
let verdicts = {};

for (let round = 0; ; round++) {
  const author = await agent(authorPrompt(notes), {
    label: `author r${round}`, phase: 'Author', schema: AUTHOR_SCHEMA, agentType: 'workflow:tech-options-analyst',
  });
  if (!author?.written) return { status: 'error', rounds: round, detail: author?.summary || 'author did not write the artifact' };

  formatGate = await agent(gatePrompt(), { label: `mdsmith r${round}`, phase: 'Format gate', schema: GATE_SCHEMA });
  if (formatGate && formatGate.structureViolations > 0) {
    if (round >= REWORK_CAP) return { status: 'rework-cap-exceeded', rounds: round, formatGate, verdicts, artifact };
    notes = `Format gate failed — fix the section structure first:\n${formatGate.diagnostics.join('\n')}`;
    log(`round ${round}: ${formatGate.structureViolations} structure violations, bouncing to author`);
    continue;
  }

  const reviews = await parallel(REVIEWERS.map(r => () =>
    agent(reviewPrompt(r), { label: `${r.name} r${round}`, phase: 'Review', schema: REVIEW_SCHEMA, agentType: r.agentType })
      .then(v => ({ reviewer: r.name, ...v }))));
  verdicts = Object.fromEntries(reviews.filter(Boolean).map(r => [r.reviewer, r]));

  const all = Object.values(verdicts);
  if (all.some(r => r.verdict === VERDICTS.NEEDS_USER)) return { status: 'needs-user', rounds: round, formatGate, verdicts, artifact };
  if (all.length === REVIEWERS.length && all.every(r => r.verdict === VERDICTS.PASS)) {
    const language = formatGate?.languageFindings ?? 0;
    if (language > 0 && round < REWORK_CAP) {
      notes = `Reviewers passed the content. Clear the language budget without changing decisions:\n${formatGate.diagnostics.join('\n')}`;
      log(`round ${round}: reviewers pass, ${language} language findings -> one more author round`);
      continue;
    }
    log(`round ${round}: pass (${language} language findings remain)`);
    return { status: 'pass', rounds: round, formatGate, verdicts, artifact };
  }

  if (round >= REWORK_CAP) return { status: 'rework-cap-exceeded', rounds: round, formatGate, verdicts, artifact };
  const findings = all.flatMap(r => r.findings.map(f => `[${r.reviewer}] ${f}`));
  if (formatGate?.languageFindings > 0) findings.push(`[format-gate] clear the language budget:\n${formatGate.diagnostics.join('\n')}`);
  notes = findings.join('\n');
  log(`round ${round}: needs-rework (${findings.length} findings)`);
}
