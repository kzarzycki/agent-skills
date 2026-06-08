import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, readdir, readFile, rm } from 'node:fs/promises';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import {
  GATE_VERDICTS,
  PHASES,
  applyGateResult,
  createInitialState,
  createWorkItemPaths,
  ensureWorkItem,
  getResumeAction,
  loadState,
  renderStatus,
  saveState,
  transition,
  writeHumanArtifact,
  writePhaseInternal,
  writeReviewInternal,
} from '../index.js';

const runLive = process.env.OMP_WORKFLOW_LIVE === '1';

async function tempRoot() {
  return mkdtemp(join(tmpdir(), 'workflow-live-v1-'));
}

async function persist(paths, state) {
  return saveState(paths.stateFile, state, { expectedRevision: state.revision });
}

test('live v1 smoke runs the full file-state workflow', { skip: !runLive }, async () => {
  const baseDir = await tempRoot();
  try {
    const workId = '2026-06-07-live-v1-smoke';
    const paths = createWorkItemPaths({ baseDir, workId });
    await ensureWorkItem(paths);

    await writeHumanArtifact(paths, {
      ordinal: '01',
      slug: 'DECISION-SPEC',
      content: [
        '# Decision Spec',
        '',
        '## Question / problem',
        'How should a vague workflow request become a bounded implementation plan?',
        '',
        '## Decision',
        'Use a small first-party state machine with numbered human artifacts and underscored internals.',
        '',
        '## Rejected alternatives',
        '- Unstructured chat-only workflow: loses resumability.',
        '- Many review packet files: overwhelms human review.',
      ].join('\n'),
    });
    await writeHumanArtifact(paths, {
      ordinal: '02',
      slug: 'TECH-OPTIONS',
      content: '# Tech Options\n\nPending approved research.\n',
    });

    let state = await saveState(paths.stateFile, createInitialState({ workId }), { expectedRevision: null });
    assert.equal((await loadState(paths.stateFile)).revision, 0);

    state = transition(state, { type: 'approve_research_buckets', bucketIds: ['local-state-machine', 'skills-runtime'] });
    state = await persist(paths, state);
    state = transition(state, { type: 'research_brief_ready' });
    await writePhaseInternal(paths, {
      phase: 'discuss',
      filename: 'research-brief.md',
      content: 'Internal research notes for agents, not human review surface.\n',
    });
    state = transition(state, { type: 'questions_complete' });
    state = applyGateResult(state, {
      phase: PHASES.DISCUSS,
      reviewer: 'live-reviewer',
      verdict: GATE_VERDICTS.PASS,
      findings: [],
    });
    state = transition(state, { type: 'decision_spec_review_passed' });
    await writeReviewInternal(paths, {
      phase: 'discuss',
      reviewer: 'live-reviewer',
      content: 'pass\n',
    });
    state = await persist(paths, state);

    let resume = getResumeAction(await loadState(paths.stateFile));
    assert.deepEqual(resume, {
      kind: 'redisplay_gate',
      gate: 'decision_spec_approval',
      targetArtifact: '01-DECISION-SPEC.md',
    });

    state = transition(state, { type: 'approve_decision_spec', approvedAt: 'live-smoke' });
    state = transition(state, { type: 'approve_tech_options_research' });
    state = transition(state, { type: 'tech_options_ready' });
    await writeHumanArtifact(paths, {
      ordinal: '02',
      slug: 'TECH-OPTIONS',
      overwrite: true,
      content: [
        '# Tech Options',
        '',
        '## Need matched',
        'Bounded workflow execution with small human artifact set and hidden runtime state.',
        '',
        '## Selected option',
        'First-party workflow core plus thin adapter.',
      ].join('\n'),
    });
    state = applyGateResult(state, {
      phase: PHASES.TECH_OPTIONS,
      reviewer: 'live-reviewer',
      verdict: GATE_VERDICTS.PASS,
      findings: [],
    });
    state = transition(state, { type: 'tech_options_review_passed' });
    state = await persist(paths, state);

    resume = getResumeAction(await loadState(paths.stateFile));
    assert.deepEqual(resume, {
      kind: 'redisplay_gate',
      gate: 'tech_options_approval',
      targetArtifact: '02-TECH-OPTIONS.md',
    });

    state = transition(state, { type: 'approve_tech_options', approvedAt: 'live-smoke' });
    state = await persist(paths, state);

    const finalState = await loadState(paths.stateFile);
    assert.equal(finalState.current_phase, PHASES.PLANNING);
    assert.equal(finalState.current_state, 'planning_pending');
    assert.deepEqual(finalState.approved_phases, [PHASES.DISCUSS, PHASES.TECH_OPTIONS]);
    assert.equal(finalState.pending_gate, null);

    const rootEntries = (await readdir(paths.root)).sort();
    assert.deepEqual(rootEntries, ['01-DECISION-SPEC.md', '02-TECH-OPTIONS.md', '_evidence', '_phases', '_reviews', '_state']);

    const decisionSpec = await readFile(join(paths.root, '01-DECISION-SPEC.md'), 'utf8');
    assert.match(decisionSpec, /## Question \/ problem/);
    assert.match(decisionSpec, /## Rejected alternatives/);

    const status = renderStatus(finalState);
    assert.doesNotMatch(status, /internal_dirs/);
    assert.match(status, /phase: planning/);
  } finally {
    await rm(baseDir, { recursive: true, force: true });
  }
});
