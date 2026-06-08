import { readFile } from 'node:fs/promises';
import { join } from 'node:path';
import { advanceWorkflow } from './workflow-core/index.js';

export const meta = {
  name: 'workflow-advance',
  description: 'Run exactly one autonomous workflow step unless a human gate is pending.',
  whenToUse: 'Args: { workId: string }. Advances research, Decision Spec generation/review, Tech Options generation/review, or reports the pending human gate.',
  phases: [{ title: 'Advance' }],
};

const MARKDOWN_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['markdown'],
  properties: { markdown: { type: 'string' } },
};

const REVIEW_SCHEMA = {
  type: 'object',
  additionalProperties: false,
  required: ['results', 'markdownByReviewer'],
  properties: {
    results: {
      type: 'array',
      items: {
        type: 'object',
        additionalProperties: false,
        required: ['reviewer', 'verdict', 'findings'],
        properties: {
          reviewer: { type: 'string' },
          verdict: { type: 'string', enum: ['pass', 'needs-rework', 'needs-user'] },
          findings: { type: 'array', items: { type: 'string' } },
        },
      },
    },
    markdownByReviewer: { type: 'object', additionalProperties: { type: 'string' } },
  },
};

async function human(paths, name) {
  return readFile(join(paths.root, name), 'utf8');
}

async function phaseInternal(paths, phase, filename) {
  return readFile(join(paths.phasesDir, phase, filename), 'utf8');
}

function liveAdapter() {
  return {
    async researchBrief({ state, paths }) {
      const current = await human(paths, state.human_artifacts.decision_spec);
      return agent(
        `Workflow work item ${state.work_id}. Produce a concise internal research brief for Discuss. Focus on facts that sharpen user grilling. Return markdown only in the schema field.\n\nApproved research buckets:\n${state.approvals.research_buckets.join('\n')}\n\nCurrent artifact:\n${current}`,
        { phase: 'Research', label: 'workflow:research-brief', schema: MARKDOWN_SCHEMA, agentType: 'researcher' },
      );
    },
    async decisionSpec({ state, paths }) {
      const current = await human(paths, state.human_artifacts.decision_spec);
      const researchBrief = await phaseInternal(paths, 'discuss', 'research-brief.md');
      return agent(
        `Use the discuss skill and interviewer agent contract to produce ${state.human_artifacts.decision_spec}. Preserve the original question/problem and rejected alternatives.\n\nResearch brief:\n${researchBrief}\n\nCurrent artifact:\n${current}`,
        { phase: 'Discuss', label: 'workflow:decision-spec', schema: MARKDOWN_SCHEMA, agentType: 'interviewer' },
      );
    },
    async reviewDecisionSpec({ state, paths }) {
      const spec = await human(paths, state.human_artifacts.decision_spec);
      return agent(
        `Run the fixed Discuss review gate using the discuss skill. Return both reviewers: intent and testability.\n\nDecision Spec:\n${spec}`,
        { phase: 'Review', label: 'workflow:review-decision-spec', schema: REVIEW_SCHEMA, agentType: 'reviewer' },
      );
    },
    async techOptions({ state, paths }) {
      const spec = await human(paths, state.human_artifacts.decision_spec);
      return agent(
        `Use the tech-options skill and tech-options-analyst agent contract to produce ${state.human_artifacts.tech_options}. Compare multiple option families, not just one hint.\n\nApproved Decision Spec:\n${spec}`,
        { phase: 'Tech Options', label: 'workflow:tech-options', schema: MARKDOWN_SCHEMA, agentType: 'tech-options-analyst' },
      );
    },
    async reviewTechOptions({ state, paths }) {
      const options = await human(paths, state.human_artifacts.tech_options);
      return agent(
        `Run the fixed Tech Options review gate using the tech-options skill. Return both reviewers: reuse-coverage and fit-risk.\n\nTech Options:\n${options}`,
        { phase: 'Review', label: 'workflow:review-tech-options', schema: REVIEW_SCHEMA, agentType: 'reviewer' },
      );
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
