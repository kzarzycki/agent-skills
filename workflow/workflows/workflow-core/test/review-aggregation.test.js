import test from 'node:test';
import assert from 'node:assert/strict';
import { applyReviewResults, createInitialState, PHASES, STATES } from '../index.js';

function discussReviewingState() {
  const state = createInitialState({ workId: 'x' });
  state.current_state = STATES.DECISION_SPEC_REVIEWING;
  return state;
}

function techReviewingState() {
  const state = createInitialState({ workId: 'x' });
  state.current_phase = PHASES.TECH_OPTIONS;
  state.current_state = STATES.TECH_OPTIONS_REVIEWING;
  return state;
}

test('discuss approval requires intent and testability reviewers to pass together', () => {
  assert.throws(
    () => applyReviewResults(discussReviewingState(), {
      phase: PHASES.DISCUSS,
      results: [{ reviewer: 'intent', verdict: 'pass', findings: [] }],
    }),
    error => error.code === 'invalid-transition' && /missing reviewer testability/.test(error.message),
  );

  const state = applyReviewResults(discussReviewingState(), {
    phase: PHASES.DISCUSS,
    results: [
      { reviewer: 'intent', verdict: 'pass', findings: [] },
      { reviewer: 'testability', verdict: 'pass', findings: [] },
    ],
  });

  assert.equal(state.current_state, STATES.DECISION_SPEC_APPROVAL_PENDING);
  assert.equal(state.pending_gate.kind, 'decision_spec_approval');
  assert.equal(state.pending_gate.target_artifact, '01-DECISION-SPEC.md');
});

test('review aggregation sends any needs-rework verdict through one rework transition', () => {
  const state = applyReviewResults(discussReviewingState(), {
    phase: PHASES.DISCUSS,
    results: [
      { reviewer: 'intent', verdict: 'pass', findings: [] },
      { reviewer: 'testability', verdict: 'needs-rework', findings: ['Acceptance criteria are not observable.'] },
    ],
  });

  assert.equal(state.current_state, STATES.DECISION_SPEC_REWORK);
  assert.equal(state.rework.discuss, 1);
  assert.deepEqual(state.blockers, ['Acceptance criteria are not observable.']);
});

test('review aggregation sends any needs-user verdict to user gate', () => {
  const state = applyReviewResults(discussReviewingState(), {
    phase: PHASES.DISCUSS,
    results: [
      { reviewer: 'intent', verdict: 'needs-user', findings: ['Choose whether Tech Options can change scope.'] },
      { reviewer: 'testability', verdict: 'pass', findings: [] },
    ],
  });

  assert.equal(state.current_state, STATES.NEEDS_USER);
  assert.equal(state.pending_gate.kind, 'discuss_needs_user');
  assert.deepEqual(state.open_questions, ['Choose whether Tech Options can change scope.']);
});

test('tech options approval requires reuse coverage and fit risk reviewers to pass together', () => {
  const state = applyReviewResults(techReviewingState(), {
    phase: PHASES.TECH_OPTIONS,
    results: [
      { reviewer: 'reuse-coverage', verdict: 'pass', findings: [] },
      { reviewer: 'fit-risk', verdict: 'pass', findings: [] },
    ],
  });

  assert.equal(state.current_state, STATES.TECH_OPTIONS_APPROVAL_PENDING);
  assert.equal(state.pending_gate.kind, 'tech_options_approval');
  assert.equal(state.pending_gate.target_artifact, '02-TECH-OPTIONS.md');
});

test('review aggregation rejects unknown reviewers', () => {
  assert.throws(
    () => applyReviewResults(discussReviewingState(), {
      phase: PHASES.DISCUSS,
      results: [
        { reviewer: 'intent', verdict: 'pass', findings: [] },
        { reviewer: 'testability', verdict: 'pass', findings: [] },
        { reviewer: 'extra', verdict: 'pass', findings: [] },
      ],
    }),
    error => error.code === 'invalid-transition' && /unknown reviewer extra/.test(error.message),
  );
});
