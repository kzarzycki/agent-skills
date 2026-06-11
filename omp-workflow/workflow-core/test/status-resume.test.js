import test from 'node:test';
import assert from 'node:assert/strict';
import { createInitialState, getResumeAction, renderStatus } from '../index.js';

test('default status hides internal directories', () => {
  const state = createInitialState({ workId: 'x' });
  state.approved_phases = ['research'];
  state.blockers = ['needs clearer scope'];
  state.open_questions = ['Which runtime?'];
  const output = renderStatus(state);
  assert.match(output, /phase: spec/);
  assert.match(output, /state: research_proposal_pending/);
  assert.match(output, /approved_phases: research/);
  assert.match(output, /current_human_artifact: 01-DECISION-SPEC.md/);
  assert.doesNotMatch(output, /_state\//);
  assert.doesNotMatch(output, /_phases\//);
  assert.doesNotMatch(output, /_reviews\//);
  assert.doesNotMatch(output, /_evidence\//);
});

test('debug status shows internal directories', () => {
  const output = renderStatus(createInitialState({ workId: 'x' }), { debug: true });
  assert.match(output, /internal_dirs: _state\/ _phases\/ _reviews\/ _evidence\//);
});

test('resume redisplays pending gate', () => {
  const action = getResumeAction(createInitialState({ workId: 'x' }));
  assert.deepEqual(action, {
    kind: 'redisplay_gate',
    gate: 'research_approval',
    targetArtifact: '01-DECISION-SPEC.md',
  });
});

test('resume continues when no gate pending', () => {
  const state = createInitialState({ workId: 'x' });
  state.pending_gate = null;
  const action = getResumeAction(state);
  assert.deepEqual(action, {
    kind: 'continue',
    phase: 'spec',
    state: 'research_proposal_pending',
  });
});

test('resume reports gate-less needs-user as blocked', () => {
  const state = createInitialState({ workId: 'x' });
  state.pending_gate = null;
  state.current_state = 'needs_user';
  state.blockers = ['No research buckets approved.'];
  const action = getResumeAction(state);
  assert.deepEqual(action, {
    kind: 'blocked',
    phase: 'spec',
    state: 'needs_user',
  });
});
