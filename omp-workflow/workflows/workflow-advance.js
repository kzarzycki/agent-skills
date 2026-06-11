import { readFile } from 'node:fs/promises';
import { join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { STATES, advanceWorkflow } from '../workflow-core/index.js';

export const meta = {
  name: 'workflow-advance',
  description: 'Run exactly one autonomous workflow step unless a human gate is pending.',
  whenToUse: 'Args: { workId: string }. Advances research, Decision Spec generation/review, Tech Options generation/review, or reports the pending human gate.',
  phases: [{ title: 'Advance' }],
};

const pluginRoot = fileURLToPath(new URL('../../workflow/', import.meta.url));
const mdsmithConfig = join(pluginRoot, 'contracts', 'mdsmith.yml');

const MARKDOWN_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['markdown'],
  properties: { markdown: { type: 'string' } },
};

const REVIEWER_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['verdict', 'findings', 'markdown'],
  properties: {
    verdict: { type: 'string', enum: ['pass', 'needs-rework', 'needs-user'] },
    findings: { type: 'array', items: { type: 'string' } },
    markdown: { type: 'string' },
  },
};

const GATE_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['toolAvailable', 'structureViolations', 'diagnostics'],
  properties: {
    toolAvailable: { type: 'boolean' },
    structureViolations: { type: 'integer' },
    diagnostics: { type: 'array', items: { type: 'string' } },
  },
};

const REVIEWERS = {
  spec: [
    { name: 'intent', agentType: 'intent-reviewer' },
    { name: 'testability', agentType: 'testability-reviewer' },
  ],
  tech_options: [
    { name: 'reuse-coverage', agentType: 'reuse-coverage-reviewer' },
    { name: 'fit-risk', agentType: 'fit-risk-reviewer' },
  ],
};

async function human(paths, name) {
  return readFile(join(paths.root, name), 'utf8');
}

async function phaseInternal(paths, phase, filename) {
  return readFile(join(paths.phasesDir, phase, filename), 'utf8');
}

function workItemDir(paths) {
  return resolve(paths.root);
}

function reworkInput(state, reworkState) {
  if (state.current_state !== reworkState || state.blockers.length === 0) return '';
  return `\n\nRework input — address every finding:\n${state.blockers.join('\n')}`;
}

async function runFixedReview({ state, paths, phaseKey, artifactName, context }) {
  const reviewers = REVIEWERS[phaseKey];
  const artifactAbs = resolve(paths.root, artifactName);

  const gate = await agent(
    `Run the workflow format gate for work item ${state.work_id}. Execute exactly:\n` +
    `export PATH="$HOME/.local/bin:$PATH" && mdsmith check -c ${mdsmithConfig} ${artifactAbs} 2>&1\n` +
    'If mdsmith is not installed, return toolAvailable=false with empty diagnostics. ' +
    'Count MDS020 diagnostics as structureViolations; report every diagnostic line as "MDSxxx line N: message". Do not modify any file.',
    { phase: 'Review', label: `workflow:format-gate:${phaseKey}`, schema: GATE_SCHEMA },
  );
  if (gate && gate.structureViolations > 0) {
    const findings = gate.diagnostics.length > 0 ? gate.diagnostics : [`${gate.structureViolations} structure violations (MDS020)`];
    const report = `# Format gate\n\nmdsmith found ${gate.structureViolations} MDS020 structure violations in ${artifactName}; reviewers were skipped.\n\n${findings.join('\n')}\n`;
    return {
      results: reviewers.map(r => ({ reviewer: r.name, verdict: 'needs-rework', findings })),
      markdownByReviewer: Object.fromEntries(reviewers.map(r => [r.name, report])),
    };
  }

  const artifactContent = await human(paths, artifactName);
  const reviews = await parallel(reviewers.map(r => () => agent(
    `${context}\n\nWork item dir: ${workItemDir(paths)} (internal phase notes live under _phases/; the artifact under review is ${artifactAbs}).\n\nArtifact content:\n${artifactContent}\n\nReturn {verdict, findings, markdown}: verdict is exactly pass, needs-rework, or needs-user; findings lists each actionable defect (empty when pass); markdown is your full review report.`,
    { phase: 'Review', label: `workflow:review:${r.name}`, schema: REVIEWER_SCHEMA, agentType: r.agentType },
  )));
  return {
    results: reviewers.map((r, i) => ({
      reviewer: r.name,
      verdict: reviews[i]?.verdict || 'needs-rework',
      findings: reviews[i]?.findings || [`${r.name} reviewer returned no result`],
    })),
    markdownByReviewer: Object.fromEntries(
      reviewers.map((r, i) => [r.name, reviews[i]?.markdown || `# ${r.name} review\n\n(no result returned)\n`]),
    ),
  };
}

function liveAdapter() {
  return {
    async researchBrief({ state, paths }) {
      const current = await human(paths, state.human_artifacts.decision_spec);
      return agent(
        `Workflow work item ${state.work_id} at ${workItemDir(paths)}. Produce a concise internal research brief for Spec. Focus on facts that sharpen user grilling. Return markdown only in the schema field.\n\nApproved research buckets:\n${state.approvals.research_buckets.join('\n')}\n\nCurrent artifact:\n${current}`,
        { phase: 'Research', label: 'workflow:research-brief', schema: MARKDOWN_SCHEMA, agentType: 'explore' },
      );
    },
    async decisionSpec({ state, paths }) {
      const current = await human(paths, state.human_artifacts.decision_spec);
      const researchBrief = await phaseInternal(paths, 'spec', 'research-brief.md').catch(() => '(no research brief)');
      return agent(
        `Use the spec skill and interviewer agent contract to produce ${state.human_artifacts.decision_spec}. Preserve the original question/problem and rejected alternatives.\n\nWork item dir: ${workItemDir(paths)} — read _phases/spec/ for internals and write your interview notes to _phases/spec/interview-notes.md.\n\nResearch brief:\n${researchBrief}\n\nCurrent artifact:\n${current}${reworkInput(state, STATES.DECISION_SPEC_REWORK)}`,
        { phase: 'Spec', label: 'workflow:decision-spec', schema: MARKDOWN_SCHEMA, agentType: 'interviewer' },
      );
    },
    async reviewDecisionSpec({ state, paths }) {
      return runFixedReview({
        state,
        paths,
        phaseKey: 'spec',
        artifactName: state.human_artifacts.decision_spec,
        context: 'Run your fixed Spec review gate using the spec skill. Judge the Decision Spec against your reviewer checklist only.',
      });
    },
    async techOptions({ state, paths }) {
      const spec = await human(paths, state.human_artifacts.decision_spec);
      return agent(
        `Use the tech-options skill and tech-options-analyst agent contract to produce ${state.human_artifacts.tech_options}. Compare multiple option families, not just one hint.\n\nWork item dir: ${workItemDir(paths)} — read _phases/ internals there as needed.\n\nApproved Decision Spec:\n${spec}${reworkInput(state, STATES.TECH_OPTIONS_REWORK)}`,
        { phase: 'Tech Options', label: 'workflow:tech-options', schema: MARKDOWN_SCHEMA, agentType: 'tech-options-analyst' },
      );
    },
    async reviewTechOptions({ state, paths }) {
      const spec = await human(paths, state.human_artifacts.decision_spec);
      return runFixedReview({
        state,
        paths,
        phaseKey: 'tech_options',
        artifactName: state.human_artifacts.tech_options,
        context: `Run your fixed Tech Options review gate using the tech-options skill. Judge the Tech Options artifact against the approved Decision Spec below and your reviewer checklist.\n\nApproved Decision Spec:\n${spec}`,
      });
    },
  };
}

const a = typeof args === 'string' ? JSON.parse(args) : (args || {});
if (!a.workId) {
  log('No args.workId provided.');
  return { error: 'no workId provided' };
}

phase('Advance');
const result = await advanceWorkflow({ workId: a.workId, adapter: liveAdapter() });
log(`workflow ${result.workId}: ${result.phase}/${result.state} r${result.revision} ${result.kind}`);
return result;
