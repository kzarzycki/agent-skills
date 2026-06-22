export const meta = {
  name: 'phase-loop',
  description: 'Generic phase convergence loop: author reworks the artifact (running the format gate itself), independent reviewers judge it in parallel, rework loops until pass, needs-user, or the rework cap. Fresh clean drafts skip the author round. No HTML rendering inside; the gate presenter renders the page.',
  whenToUse: 'Args: { workId, pluginRoot, phase: "spec"|"tech_design", instructions?, contentFrozen? }. Returns { status, rounds, verdicts, formatGate, artifact }. status: pass | needs-user | rework-cap-exceeded | error. Stateless: agents read/write work-item files only.',
  phases: [{ title: 'Author' }, { title: 'Review' }],
};

const REWORK_CAP = 2; // mirrors workflow-core/schema.js
const VERDICTS = { PASS: 'pass', NEEDS_REWORK: 'needs-rework', NEEDS_USER: 'needs-user' };

const GATE_PROPS = {
  toolAvailable: { type: 'boolean' },
  structureViolations: { type: 'integer' },
  languageFindings: { type: 'integer' },
  diagnostics: { type: 'array', items: { type: 'string' } },
};

const AUTHOR_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['written', 'summary', 'gate'],
  properties: {
    written: { type: 'boolean' },
    summary: { type: 'string' },
    gate: { type: 'object', additionalProperties: false, required: Object.keys(GATE_PROPS), properties: GATE_PROPS },
  },
};

const GATE_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: Object.keys(GATE_PROPS),
  properties: GATE_PROPS,
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

const a = typeof args === 'string' ? JSON.parse(args) : (args || {});
if (!a.workId) return { error: 'no workId provided' };
if (!a.pluginRoot) return { error: 'no pluginRoot provided (the workflow plugin dir containing contracts/)' };

const root = `.workflow/${a.workId}`;
const specPath = `${root}/01-DECISION-SPEC.mdx`;

const PHASES = {
  spec: {
    artifact: specPath,
    contract: 'decision-spec.json',
    reviewsDir: `${root}/_reviews/spec`,
    authorAgentType: 'workflow:interviewer',
    skillName: 'spec',
    reviewers: [
      { name: 'intent', agentType: 'workflow:intent-reviewer' },
      { name: 'testability', agentType: 'workflow:testability-reviewer' },
    ],
    // The draft comes out of the interview, already engine-format-checked: review it as-is.
    skipFreshDraft: true,
    frozenNouns: 'decision, constraint, criterion, and fact',
    preserveRule: 'Preserve interview-sourced content unless rework findings explicitly contradict it.',
    authorBody: `Your inputs are the existing draft and the interview record at ${root}/_phases/spec/interview-notes.md and ${root}/_phases/spec/research-brief.md. Rework the draft in place to satisfy the contract. This is workflow author mode: do NOT interview anyone, do NOT use AskUserQuestion, do NOT run any Workflow yourself. If the draft is missing, stop and return written=false with the reason in summary.`,
    reviewAgainst: `the interview record (${root}/_phases/spec/interview-notes.md, ${root}/_phases/spec/research-brief.md)`,
  },
  tech_design: {
    artifact: `${root}/02-TECH-DESIGN.md`,
    contract: 'tech-design.json',
    reviewsDir: `${root}/_reviews/tech_design`,
    authorAgentType: 'workflow:tech-designer',
    skillName: 'tech-design',
    reviewers: [
      { name: 'reuse-coverage', agentType: 'workflow:reuse-coverage-reviewer' },
      { name: 'fit-risk', agentType: 'workflow:fit-risk-reviewer' },
    ],
    // The designer authors the artifact fresh: round 0 always runs the author.
    skipFreshDraft: false,
    frozenNouns: 'decision, option, score, design element, and fact',
    preserveRule: 'Preserve approved content unless rework findings explicitly contradict it.',
    authorBody: `Read the approved Decision Spec at ${specPath}. If the artifact exists, rework it in place; otherwise write it fresh (this path is your tech_design_path). If the Decision Spec is missing, stop and return written=false with the reason in summary.`,
    reviewAgainst: `the Decision Spec at ${specPath}`,
  },
};

const cfg = PHASES[a.phase];
if (!cfg) return { error: `unknown phase "${a.phase}" (expected spec | tech_design)` };

const mdsmithCmd = `export PATH="$HOME/.local/bin:$PATH" && mdsmith check -c ${a.pluginRoot}/contracts/mdsmith.yml ${cfg.artifact} 2>&1`;
const gateRules = `If mdsmith is not installed, return toolAvailable=false and verify the H2 sections of ${cfg.artifact} manually against ${a.pluginRoot}/contracts/${cfg.contract}, reporting mismatches as diagnostics. If the artifact file is missing, report that as a diagnostic with structureViolations=1.
Count MDS020 diagnostics as structureViolations and all other MDS* diagnostics as languageFindings. Report each diagnostic as "MDSxxx line N: message".`;

function frozenRule(frozen) {
  return frozen
    ? `CONTENT IS FROZEN: keep every ${cfg.frozenNouns} exactly as it is; change only shape and language (structure, tables, lists, sentence length). Record the rework in the Approval record.`
    : cfg.preserveRule;
}

function authorPrompt(notes, frozen) {
  return `You author the ${a.phase} artifact ${cfg.artifact} for work item ${a.workId}. The ${cfg.skillName} skill preloaded in your context is the phase contract; follow it.
${cfg.authorBody}
${frozenRule(frozen)}
${notes ? `Rework input — address every item:\n${notes}` : ''}
After writing, run the format gate yourself. Execute exactly:
${mdsmithCmd}
${gateRules}
Fix MDS020 structure violations yourself before returning (re-run the command after fixing); report the final state in gate. Do not SendMessage anyone. Return {written, summary, gate}.`;
}

const gatePrompt = `Run the workflow format gate. Execute exactly:
${mdsmithCmd}
${gateRules} Do not modify any file. Return {toolAvailable, structureViolations, languageFindings, diagnostics}.`;

function reviewPrompt(reviewer) {
  return `Review ${cfg.artifact} against ${cfg.reviewAgainst}, following your reviewer checklist and the ${cfg.skillName} skill preloaded in your context.
If your previous review exists at ${cfg.reviewsDir}/${reviewer.name}.md, this is a rework round: read it first, verify each earlier finding was addressed, and focus on what changed since -- do not re-derive findings you already passed.
Write your full review markdown to ${cfg.reviewsDir}/${reviewer.name}.md (create dirs as needed; overwrite with the current review).
Return {verdict, findings}: verdict is exactly pass, needs-rework, or needs-user; findings lists each actionable defect (empty when pass).`;
}

function reviewThunks(round) {
  return cfg.reviewers.map(r => () =>
    agent(reviewPrompt(r), { label: `${r.name} r${round}`, phase: 'Review', schema: REVIEW_SCHEMA, agentType: r.agentType })
      .then(v => ({ reviewer: r.name, ...v })));
}

let notes = a.instructions || '';
let formatGate = null;
let verdicts = {};
const done = (status, rounds) => ({ status, rounds, formatGate, verdicts, artifact: cfg.artifact });

for (let round = 0; ; round++) {
  let reviews;
  const skipAuthor = round === 0 && cfg.skipFreshDraft && !notes;

  if (skipAuthor) {
    // Fresh reviewed-ready draft: format gate (cheap model) and reviewers run in one parallel wave.
    log('round 0: fresh draft, skipping author; gate + reviewers in parallel');
    const wave = await parallel([
      () => agent(gatePrompt, { label: 'mdsmith r0', phase: 'Review', schema: GATE_SCHEMA, model: 'haiku' }),
      ...reviewThunks(round),
    ]);
    formatGate = wave[0];
    reviews = wave.slice(1);
  } else {
    const frozen = a.contentFrozen || false;
    const author = await agent(authorPrompt(notes, frozen), {
      label: `author r${round}`, phase: 'Author', schema: AUTHOR_SCHEMA, agentType: cfg.authorAgentType,
    });
    if (!author?.written) return { status: 'error', rounds: round, detail: author?.summary || 'author did not write the artifact' };
    formatGate = author.gate;
    if (formatGate && formatGate.structureViolations > 0) {
      if (round >= REWORK_CAP) return done('rework-cap-exceeded', round);
      notes = `Format gate failed — fix the section structure first:\n${formatGate.diagnostics.join('\n')}`;
      log(`round ${round}: ${formatGate.structureViolations} structure violations, bouncing to author`);
      continue;
    }
    reviews = await parallel(reviewThunks(round));
  }

  verdicts = Object.fromEntries(reviews.filter(r => r && r.verdict).map(r => [r.reviewer, r]));
  const all = Object.values(verdicts);

  if (formatGate && formatGate.structureViolations > 0) {
    // Only reachable on the skip-author wave; reviewer verdicts on a malformed artifact still count as rework input.
    if (round >= REWORK_CAP) return done('rework-cap-exceeded', round);
    notes = [`Format gate failed — fix the section structure first:\n${formatGate.diagnostics.join('\n')}`,
      ...all.flatMap(r => r.findings.map(f => `[${r.reviewer}] ${f}`))].join('\n');
    log(`round ${round}: structure violations on fresh draft, bouncing to author`);
    continue;
  }

  if (all.some(r => r.verdict === VERDICTS.NEEDS_USER)) return done('needs-user', round);

  if (all.length === cfg.reviewers.length && all.every(r => r.verdict === VERDICTS.PASS)) {
    const language = formatGate?.languageFindings ?? 0;
    if (language > 0 && round < REWORK_CAP) {
      // Reviewers passed the content: clear the language budget with one frozen author pass, no re-review.
      log(`round ${round}: reviewers pass, ${language} language findings -> frozen language pass, no re-review`);
      const polish = await agent(
        authorPrompt(`Reviewers passed the content. Clear the language budget without changing decisions:\n${formatGate.diagnostics.join('\n')}`, true),
        { label: 'language pass', phase: 'Author', schema: AUTHOR_SCHEMA, agentType: cfg.authorAgentType },
      );
      if (polish?.written && polish.gate) formatGate = polish.gate;
    }
    log(`round ${round}: pass (${formatGate?.languageFindings ?? 0} language findings remain)`);
    return done('pass', round);
  }

  if (round >= REWORK_CAP) return done('rework-cap-exceeded', round);
  const findings = all.flatMap(r => r.findings.map(f => `[${r.reviewer}] ${f}`));
  if (formatGate?.languageFindings > 0) findings.push(`[format-gate] clear the language budget:\n${formatGate.diagnostics.join('\n')}`);
  notes = findings.join('\n');
  log(`round ${round}: needs-rework (${findings.length} findings)`);
}
