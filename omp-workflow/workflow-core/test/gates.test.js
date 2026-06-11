import test from 'node:test';
import assert from 'node:assert/strict';
import { createInitialState, transition, applyGateResult, STATES, PHASES } from '../index.js';

test('research approval and denial transitions', () => {
  const initial = createInitialState({ workId: 'x' });
  const approved = transition(initial, { type: 'approve_research_buckets', bucketIds: ['local'] });
  assert.equal(approved.current_state, STATES.RESEARCH_RUNNING);
  assert.deepEqual(approved.approvals.research_buckets, ['local']);

  const denied = transition(initial, { type: 'deny_all_research' });
  assert.equal(denied.current_state, STATES.NEEDS_USER);
  assert.ok(denied.blockers[0].includes('Research cannot proceed'));
});

test('spec to tech options approval path', () => {
  let state = createInitialState({ workId: 'x' });
  state = transition(state, { type: 'approve_research_buckets', bucketIds: ['local'] });
  state = transition(state, { type: 'research_brief_ready' });
  state = transition(state, { type: 'questions_complete' });
  state = transition(state, { type: 'decision_spec_review_passed' });
  assert.equal(state.pending_gate.kind, 'decision_spec_approval');
  state = transition(state, { type: 'approve_decision_spec' });
  assert.equal(state.current_phase, PHASES.TECH_OPTIONS);
  assert.equal(state.current_state, STATES.TECH_OPTIONS_RESEARCH_PENDING);
  assert.ok(state.approved_phases.includes(PHASES.SPEC));
});

test('gate verdicts and spec rework cap', () => {
  let state = createInitialState({ workId: 'x' });
  state.current_state = STATES.DECISION_SPEC_REVIEWING;
  state = applyGateResult(state, { phase: PHASES.SPEC, reviewer: 'intent', verdict: 'needs-rework', findings: ['a'] });
  assert.equal(state.current_state, STATES.DECISION_SPEC_REWORK);
  assert.equal(state.rework.spec, 1);
  state = applyGateResult(state, { phase: PHASES.SPEC, reviewer: 'intent', verdict: 'needs-rework', findings: ['b'] });
  assert.equal(state.rework.spec, 2);
  state = applyGateResult(state, { phase: PHASES.SPEC, reviewer: 'intent', verdict: 'needs-rework', findings: ['c'] });
  assert.equal(state.current_state, STATES.NEEDS_USER);
  assert.equal(state.pending_gate.kind, 'spec_rework_cap_exceeded');
});

test('needs-user verdict creates open question gate', () => {
  let state = createInitialState({ workId: 'x' });
  state.current_state = STATES.DECISION_SPEC_REVIEWING;
  state = applyGateResult(state, { phase: PHASES.SPEC, reviewer: 'intent', verdict: 'needs-user', findings: ['Choose runtime'] });
  assert.equal(state.current_state, STATES.NEEDS_USER);
  assert.deepEqual(state.open_questions, ['Choose runtime']);
  assert.equal(state.pending_gate.kind, 'spec_needs_user');
});

test('tech options rework cap targets tech artifact', () => {
  let state = createInitialState({ workId: 'x' });
  state.current_state = STATES.TECH_OPTIONS_REVIEWING;
  state.current_phase = PHASES.TECH_OPTIONS;
  state = applyGateResult(state, { phase: PHASES.TECH_OPTIONS, reviewer: 'reuse', verdict: 'needs-rework', findings: ['a'] });
  state = applyGateResult(state, { phase: PHASES.TECH_OPTIONS, reviewer: 'reuse', verdict: 'needs-rework', findings: ['b'] });
  state = applyGateResult(state, { phase: PHASES.TECH_OPTIONS, reviewer: 'reuse', verdict: 'needs-rework', findings: ['c'] });
  assert.equal(state.current_state, STATES.NEEDS_USER);
  assert.equal(state.pending_gate.target_artifact, '02-TECH-OPTIONS.md');
});

test('unknown verdict, invalid phase state, and invalid phase are rejected', () => {
  const state = createInitialState({ workId: 'x' });
  assert.throws(() => applyGateResult({ ...state, current_state: STATES.DECISION_SPEC_REVIEWING }, { phase: PHASES.SPEC, reviewer: 'intent', verdict: 'maybe' }), error => error.code === 'invalid-gate-verdict');
  assert.throws(() => applyGateResult(state, { phase: PHASES.SPEC, reviewer: 'intent', verdict: 'needs-rework' }), error => error.code === 'invalid-transition');
  assert.throws(() => applyGateResult({ ...state, current_state: STATES.DECISION_SPEC_REVIEWING }, { phase: 'bogus', reviewer: 'intent', verdict: 'needs-rework' }), error => error.code === 'invalid-transition');
});

test('pass clears active blockers', () => {
  let state = createInitialState({ workId: 'x' });
  state.current_state = STATES.DECISION_SPEC_REVIEWING;
  state.blockers = ['old'];
  state.open_questions = ['old question'];
  state = applyGateResult(state, { phase: PHASES.SPEC, reviewer: 'intent', verdict: 'pass', findings: [] });
  assert.deepEqual(state.blockers, []);
  assert.deepEqual(state.open_questions, []);
});

test('resume_rework returns a needs-user verdict to decision spec rework with user notes', () => {
  let state = createInitialState({ workId: 'x' });
  state.current_state = STATES.DECISION_SPEC_REVIEWING;
  state = applyGateResult(state, { phase: PHASES.SPEC, reviewer: 'intent', verdict: 'needs-user', findings: ['Choose runtime'] });
  assert.equal(state.current_state, STATES.NEEDS_USER);
  state = transition(state, { type: 'resume_rework', notes: ['Runtime: node 22'] });
  assert.equal(state.current_state, STATES.DECISION_SPEC_REWORK);
  assert.equal(state.pending_gate, null);
  assert.deepEqual(state.blockers, ['Runtime: node 22']);
});

test('resume_rework resets the rework counter after a cap-exceeded gate', () => {
  let state = createInitialState({ workId: 'x' });
  state.current_phase = PHASES.TECH_OPTIONS;
  state.current_state = STATES.TECH_OPTIONS_REVIEWING;
  for (const finding of ['a', 'b', 'c']) {
    state = applyGateResult(state, { phase: PHASES.TECH_OPTIONS, reviewer: 'fit-risk', verdict: 'needs-rework', findings: [finding] });
  }
  assert.equal(state.current_state, STATES.NEEDS_USER);
  assert.equal(state.pending_gate.kind, 'tech_options_rework_cap_exceeded');
  assert.equal(state.rework.tech_options, 3);
  state = transition(state, { type: 'resume_rework' });
  assert.equal(state.current_state, STATES.TECH_OPTIONS_REWORK);
  assert.equal(state.rework.tech_options, 0);
  assert.equal(state.pending_gate, null);
});

test('resume_rework is invalid outside needs_user', () => {
  const state = createInitialState({ workId: 'x' });
  assert.throws(() => transition(state, { type: 'resume_rework' }), error => error.code === 'invalid-transition');
});

test('denied research sets a recoverable needs-user gate', () => {
  let state = transition(createInitialState({ workId: 'x' }), { type: 'deny_all_research' });
  assert.equal(state.current_state, STATES.NEEDS_USER);
  assert.equal(state.pending_gate.kind, 'spec_needs_user');
  state = transition(state, { type: 'resume_rework', notes: ['Skip research; user supplied the context directly.'] });
  assert.equal(state.current_state, STATES.DECISION_SPEC_REWORK);
  assert.deepEqual(state.blockers, ['Skip research; user supplied the context directly.']);
});

test('tech options can trigger and leave spec addendum', () => {
  let state = createInitialState({ workId: 'x' });
  state.current_state = STATES.TECH_OPTIONS_REVIEWING;
  state.current_phase = PHASES.TECH_OPTIONS;
  state = transition(state, { type: 'tech_options_product_change' });
  assert.equal(state.current_state, STATES.SPEC_ADDENDUM_PENDING);
  state = transition(state, { type: 'approve_spec_addendum' });
  assert.equal(state.current_state, STATES.TECH_OPTIONS_RESEARCH_PENDING);
});

test('tech options approval reaches planning', () => {
  let state = createInitialState({ workId: 'x' });
  state.current_state = STATES.TECH_OPTIONS_REVIEWING;
  state.current_phase = PHASES.TECH_OPTIONS;
  state = transition(state, { type: 'tech_options_review_passed' });
  assert.equal(state.pending_gate.kind, 'tech_options_approval');
  state = transition(state, { type: 'approve_tech_options' });
  assert.equal(state.current_state, STATES.PLANNING_PENDING);
  assert.ok(state.approved_phases.includes(PHASES.TECH_OPTIONS));
});
