import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, readdir, readFile, rm } from 'node:fs/promises';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import {
  advanceWorkflow,
  applyWorkflowEvent,
  createInitialState,
  createWorkItemPaths,
  ensureWorkItem,
  loadState,
  PHASES,
  saveState,
  STATES,
  writeHumanArtifact,
} from '../index.js';

async function tempRoot() {
  return mkdtemp(join(tmpdir(), 'workflow-drivers-'));
}

async function seededWork(baseDir) {
  const workId = '2026-06-07-driver-smoke';
  const paths = createWorkItemPaths({ baseDir, workId });
  await ensureWorkItem(paths);
  await writeHumanArtifact(paths, { ordinal: '01', slug: 'DECISION-SPEC', content: 'Pending Decision Spec.\n' });
  await writeHumanArtifact(paths, { ordinal: '02', slug: 'TECH-OPTIONS', content: 'Pending Tech Options.\n' });
  await saveState(paths.stateFile, createInitialState({ workId }), { expectedRevision: null });
  return { workId, paths };
}

const adapter = {
  async researchBrief() {
    return { markdown: '# Research Brief\n\nApproved buckets researched.\n' };
  },
  async decisionSpec() {
    return { markdown: '# 01 — Decision Spec\n\n## Question / problem\nBuild OMP workflow.\n\n## Current decision\nUse programmatic state.\n\n## Rejected alternatives\nChat-only workflow.\n\n## Acceptance criteria\nReaches Tech Options gate.\n' };
  },
  async reviewDecisionSpec() {
    return {
      results: [
        { reviewer: 'intent', verdict: 'pass', findings: [] },
        { reviewer: 'testability', verdict: 'pass', findings: [] },
      ],
      markdownByReviewer: {
        intent: '# Intent Review\n\npass\n',
        testability: '# Testability Review\n\npass\n',
      },
    };
  },
  async techOptions() {
    return { markdown: '# 02 — Tech Options\n\n## Needs\nProgrammatic OMP steering.\n\n## Options considered\nFirst-party core, pi-flows reference, generic engines.\n\n## Recommended option\nFirst-party core.\n' };
  },
  async reviewTechOptions() {
    return {
      results: [
        { reviewer: 'reuse-coverage', verdict: 'pass', findings: [] },
        { reviewer: 'fit-risk', verdict: 'pass', findings: [] },
      ],
      markdownByReviewer: {
        'reuse-coverage': '# Reuse/Coverage Review\n\npass\n',
        'fit-risk': '# Fit/Risk Review\n\npass\n',
      },
    };
  },
};

test('workflow event applies only human/controller events with revision checks', async () => {
  const baseDir = await tempRoot();
  try {
    const { workId } = await seededWork(baseDir);
    const approved = await applyWorkflowEvent({ baseDir, workId, expectedRevision: 0, event: 'approve_research_buckets', payload: { bucketIds: ['skills'] } });
    assert.equal(approved.state, STATES.RESEARCH_RUNNING);
    assert.equal(approved.revision, 1);

    await assert.rejects(
      () => applyWorkflowEvent({ baseDir, workId, expectedRevision: 0, event: 'approve_research_buckets', payload: { bucketIds: ['again'] } }),
      error => error.code === 'stale-state-revision',
    );

    await assert.rejects(
      () => applyWorkflowEvent({ baseDir, workId, event: 'research_brief_ready' }),
      error => error.code === 'invalid-transition' && /not a human event/.test(error.message),
    );
  } finally {
    await rm(baseDir, { recursive: true, force: true });
  }
});

test('workflow advance performs exactly one autonomous step and refuses pending gates', async () => {
  const baseDir = await tempRoot();
  try {
    const { workId, paths } = await seededWork(baseDir);
    const gateResult = await advanceWorkflow({ baseDir, workId, adapter });
    assert.equal(gateResult.kind, 'human_gate');
    assert.equal((await loadState(paths.stateFile)).revision, 0);

    await applyWorkflowEvent({ baseDir, workId, expectedRevision: 0, event: 'approve_research_buckets', payload: { bucketIds: ['skills'] } });

    let advanced = await advanceWorkflow({ baseDir, workId, adapter });
    assert.equal(advanced.state, STATES.DISCUSS_GRILLING);
    assert.equal((await loadState(paths.stateFile)).revision, 2);

    advanced = await advanceWorkflow({ baseDir, workId, adapter });
    assert.equal(advanced.state, STATES.DECISION_SPEC_REVIEWING);
    assert.equal((await loadState(paths.stateFile)).revision, 3);

    advanced = await advanceWorkflow({ baseDir, workId, adapter });
    assert.equal(advanced.state, STATES.DECISION_SPEC_APPROVAL_PENDING);
    assert.equal(advanced.kind, 'human_gate');
    assert.equal((await loadState(paths.stateFile)).revision, 4);

    const entries = (await readdir(paths.root)).sort();
    assert.deepEqual(entries, ['01-DECISION-SPEC.md', '02-TECH-OPTIONS.md', '_evidence', '_phases', '_reviews', '_state']);
    assert.match(await readFile(join(paths.reviewsDir, 'discuss', 'intent.md'), 'utf8'), /pass/);
    assert.match(await readFile(join(paths.reviewsDir, 'discuss', 'testability.md'), 'utf8'), /pass/);

    const blockedAtGate = await advanceWorkflow({ baseDir, workId, adapter });
    assert.equal(blockedAtGate.kind, 'human_gate');
    assert.equal((await loadState(paths.stateFile)).revision, 4);
  } finally {
    await rm(baseDir, { recursive: true, force: true });
  }
});

test('workflow drivers reach planning pending through tech options review', async () => {
  const baseDir = await tempRoot();
  try {
    const { workId, paths } = await seededWork(baseDir);
    await applyWorkflowEvent({ baseDir, workId, expectedRevision: 0, event: 'approve_research_buckets', payload: { bucketIds: ['skills'] } });
    await advanceWorkflow({ baseDir, workId, adapter });
    await advanceWorkflow({ baseDir, workId, adapter });
    await advanceWorkflow({ baseDir, workId, adapter });
    await applyWorkflowEvent({ baseDir, workId, expectedRevision: 4, event: 'approve_decision_spec', payload: { approvedAt: 'test' } });
    await applyWorkflowEvent({ baseDir, workId, expectedRevision: 5, event: 'approve_tech_options_research' });
    await advanceWorkflow({ baseDir, workId, adapter });
    await advanceWorkflow({ baseDir, workId, adapter });
    const atTechGate = await loadState(paths.stateFile);
    assert.equal(atTechGate.current_state, STATES.TECH_OPTIONS_APPROVAL_PENDING);
    await applyWorkflowEvent({ baseDir, workId, expectedRevision: atTechGate.revision, event: 'approve_tech_options', payload: { approvedAt: 'test' } });
    const finalState = await loadState(paths.stateFile);
    assert.equal(finalState.current_phase, PHASES.PLANNING);
    assert.equal(finalState.current_state, STATES.PLANNING_PENDING);
    assert.deepEqual(finalState.approved_phases, [PHASES.DISCUSS, PHASES.TECH_OPTIONS]);
    assert.match(await readFile(join(paths.root, '02-TECH-OPTIONS.md'), 'utf8'), /Options considered/);
    assert.match(await readFile(join(paths.reviewsDir, 'tech_options', 'reuse-coverage.md'), 'utf8'), /pass/);
    assert.match(await readFile(join(paths.reviewsDir, 'tech_options', 'fit-risk.md'), 'utf8'), /pass/);
  } finally {
    await rm(baseDir, { recursive: true, force: true });
  }
});

test('workflow advance regenerates Tech Options after review rework', async () => {
  const baseDir = await tempRoot();
  try {
    const { workId, paths } = await seededWork(baseDir);
    let reviewCalls = 0;
    let techCalls = 0;
    const reworkAdapter = {
      ...adapter,
      async techOptions() {
        techCalls += 1;
        return { markdown: `# 02 — Tech Options\n\n## Options considered\nRevision ${techCalls}.\n` };
      },
      async reviewTechOptions() {
        reviewCalls += 1;
        if (reviewCalls === 1) {
          return {
            results: [
              { reviewer: 'reuse-coverage', verdict: 'needs-rework', findings: ['Add needs mapping.'] },
              { reviewer: 'fit-risk', verdict: 'pass', findings: [] },
            ],
            markdownByReviewer: {
              'reuse-coverage': '# Reuse/Coverage Review\n\nneeds-rework\n',
              'fit-risk': '# Fit/Risk Review\n\npass\n',
            },
          };
        }
        return adapter.reviewTechOptions();
      },
    };

    await applyWorkflowEvent({ baseDir, workId, expectedRevision: 0, event: 'approve_research_buckets', payload: { bucketIds: ['skills'] } });
    await advanceWorkflow({ baseDir, workId, adapter: reworkAdapter });
    await advanceWorkflow({ baseDir, workId, adapter: reworkAdapter });
    await advanceWorkflow({ baseDir, workId, adapter: reworkAdapter });
    await applyWorkflowEvent({ baseDir, workId, expectedRevision: 4, event: 'approve_decision_spec', payload: { approvedAt: 'test' } });
    await applyWorkflowEvent({ baseDir, workId, expectedRevision: 5, event: 'approve_tech_options_research' });
    await advanceWorkflow({ baseDir, workId, adapter: reworkAdapter });
    await advanceWorkflow({ baseDir, workId, adapter: reworkAdapter });
    let state = await loadState(paths.stateFile);
    assert.equal(state.current_state, STATES.TECH_OPTIONS_REWORK);

    const regenerated = await advanceWorkflow({ baseDir, workId, adapter: reworkAdapter });
    state = await loadState(paths.stateFile);
    assert.equal(regenerated.state, STATES.TECH_OPTIONS_REVIEWING);
    assert.equal(state.current_state, STATES.TECH_OPTIONS_REVIEWING);
    assert.equal(techCalls, 2);
    assert.equal(reviewCalls, 1);
    assert.match(await readFile(join(paths.root, '02-TECH-OPTIONS.md'), 'utf8'), /Revision 2/);
  } finally {
    await rm(baseDir, { recursive: true, force: true });
  }
});

test('workflow advance regenerates Decision Spec after review rework', async () => {
  const baseDir = await tempRoot();
  try {
    const { workId, paths } = await seededWork(baseDir);
    let specCalls = 0;
    let reviewCalls = 0;
    const reworkAdapter = {
      ...adapter,
      async decisionSpec() {
        specCalls += 1;
        return { markdown: `# 01 — Decision Spec\n\n## Question / problem\nRevision ${specCalls}.\n\n## Rejected alternatives\nChat-only.\n\n## Acceptance criteria\nObservable.\n` };
      },
      async reviewDecisionSpec() {
        reviewCalls += 1;
        if (reviewCalls === 1) {
          return {
            results: [
              { reviewer: 'intent', verdict: 'needs-rework', findings: ['Preserve original problem.'] },
              { reviewer: 'testability', verdict: 'pass', findings: [] },
            ],
            markdownByReviewer: {
              intent: '# Intent Review\n\nneeds-rework\n',
              testability: '# Testability Review\n\npass\n',
            },
          };
        }
        return adapter.reviewDecisionSpec();
      },
    };

    await applyWorkflowEvent({ baseDir, workId, expectedRevision: 0, event: 'approve_research_buckets', payload: { bucketIds: ['skills'] } });
    await advanceWorkflow({ baseDir, workId, adapter: reworkAdapter });
    await advanceWorkflow({ baseDir, workId, adapter: reworkAdapter });
    await advanceWorkflow({ baseDir, workId, adapter: reworkAdapter });
    let state = await loadState(paths.stateFile);
    assert.equal(state.current_state, STATES.DECISION_SPEC_REWORK);

    const regenerated = await advanceWorkflow({ baseDir, workId, adapter: reworkAdapter });
    state = await loadState(paths.stateFile);
    assert.equal(regenerated.state, STATES.DECISION_SPEC_REVIEWING);
    assert.equal(state.current_state, STATES.DECISION_SPEC_REVIEWING);
    assert.equal(specCalls, 2);
    assert.equal(reviewCalls, 1);
    assert.match(await readFile(join(paths.root, '01-DECISION-SPEC.md'), 'utf8'), /Revision 2/);
  } finally {
    await rm(baseDir, { recursive: true, force: true });
  }
});
