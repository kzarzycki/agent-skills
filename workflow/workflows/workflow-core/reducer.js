import { PHASES, STATES, GATE_VERDICTS, REWORK_CAP, ERROR_CODES, REVIEWERS_BY_PHASE, assertGateVerdict, makeError, validateState } from './schema.js';

function clone(state) {
  return JSON.parse(JSON.stringify(state));
}

function withReason(state, reason) {
  state.last_transition_reason = reason;
  return state;
}

function approvePhase(state, phase) {
  if (!state.approved_phases.includes(phase)) state.approved_phases.push(phase);
}

function setGate(state, kind, targetArtifact) {
  state.pending_gate = { kind, target_artifact: targetArtifact };
}

function clearGate(state) {
  state.pending_gate = null;
}

function addBlocker(state, summary) {
  state.blockers.push(summary);
}

function assertTransition(condition, eventType, currentState) {
  if (!condition) {
    throw makeError(ERROR_CODES.INVALID_TRANSITION, `invalid transition ${eventType} from ${currentState}`);
  }
}

export function transition(inputState, event) {
  const state = clone(validateState(inputState));
  switch (event.type) {
    case 'approve_research_buckets':
      assertTransition(state.current_state === STATES.RESEARCH_PROPOSAL_PENDING, event.type, state.current_state);
      if (!Array.isArray(event.bucketIds) || event.bucketIds.length === 0) {
        state.current_state = STATES.NEEDS_USER;
        addBlocker(state, 'No research buckets approved.');
        clearGate(state);
        return withReason(state, 'research-denied');
      }
      state.current_state = STATES.RESEARCH_RUNNING;
      state.approvals.research_buckets = event.bucketIds;
      clearGate(state);
      return withReason(state, 'research-buckets-approved');

    case 'deny_all_research':
      assertTransition(state.current_state === STATES.RESEARCH_PROPOSAL_PENDING, event.type, state.current_state);
      state.current_state = STATES.NEEDS_USER;
      addBlocker(state, 'Research cannot proceed without approved buckets.');
      clearGate(state);
      return withReason(state, 'research-denied');

    case 'research_brief_ready':
      assertTransition(state.current_state === STATES.RESEARCH_RUNNING, event.type, state.current_state);
      state.current_state = STATES.DISCUSS_GRILLING;
      return withReason(state, 'research-brief-ready');

    case 'questions_complete':
      assertTransition(state.current_state === STATES.DISCUSS_GRILLING, event.type, state.current_state);
      state.current_state = STATES.DECISION_SPEC_REVIEWING;
      return withReason(state, 'discuss-questions-complete');

    case 'decision_spec_rework_complete':
      assertTransition(state.current_state === STATES.DECISION_SPEC_REWORK, event.type, state.current_state);
      state.current_state = STATES.DECISION_SPEC_REVIEWING;
      return withReason(state, 'decision-spec-rework-complete');

    case 'decision_spec_review_passed':
      assertTransition([STATES.DECISION_SPEC_REVIEWING, STATES.DECISION_SPEC_REWORK].includes(state.current_state), event.type, state.current_state);
      state.current_state = STATES.DECISION_SPEC_APPROVAL_PENDING;
      setGate(state, 'decision_spec_approval', state.human_artifacts.decision_spec);
      return withReason(state, 'decision-spec-review-passed');

    case 'approve_decision_spec':
      assertTransition(state.current_state === STATES.DECISION_SPEC_APPROVAL_PENDING, event.type, state.current_state);
      approvePhase(state, PHASES.DISCUSS);
      state.approvals.decision_spec = event.approvedAt || true;
      state.current_phase = PHASES.TECH_OPTIONS;
      state.current_state = STATES.TECH_OPTIONS_RESEARCH_PENDING;
      setGate(state, 'tech_options_research_approval', state.human_artifacts.tech_options);
      return withReason(state, 'decision-spec-approved');

    case 'approve_tech_options_research':
      assertTransition(state.current_state === STATES.TECH_OPTIONS_RESEARCH_PENDING, event.type, state.current_state);
      state.current_state = STATES.TECH_OPTIONS_RUNNING;
      clearGate(state);
      return withReason(state, 'tech-options-research-approved');

    case 'tech_options_ready':
      assertTransition(state.current_state === STATES.TECH_OPTIONS_RUNNING, event.type, state.current_state);
      state.current_state = STATES.TECH_OPTIONS_REVIEWING;
      return withReason(state, 'tech-options-ready');

    case 'tech_options_rework_complete':
      assertTransition(state.current_state === STATES.TECH_OPTIONS_REWORK, event.type, state.current_state);
      state.current_state = STATES.TECH_OPTIONS_REVIEWING;
      return withReason(state, 'tech-options-rework-complete');

    case 'tech_options_product_change':
      assertTransition(state.current_state === STATES.TECH_OPTIONS_REVIEWING, event.type, state.current_state);
      state.current_state = STATES.DISCUSS_ADDENDUM_PENDING;
      setGate(state, 'discuss_addendum', state.human_artifacts.decision_spec);
      return withReason(state, 'tech-options-product-change');

    case 'approve_discuss_addendum':
      assertTransition(state.current_state === STATES.DISCUSS_ADDENDUM_PENDING, event.type, state.current_state);
      state.current_state = STATES.TECH_OPTIONS_RESEARCH_PENDING;
      setGate(state, 'tech_options_research_approval', state.human_artifacts.tech_options);
      return withReason(state, 'discuss-addendum-approved');

    case 'tech_options_review_passed':
      assertTransition([STATES.TECH_OPTIONS_REVIEWING, STATES.TECH_OPTIONS_REWORK].includes(state.current_state), event.type, state.current_state);
      state.current_state = STATES.TECH_OPTIONS_APPROVAL_PENDING;
      setGate(state, 'tech_options_approval', state.human_artifacts.tech_options);
      return withReason(state, 'tech-options-review-passed');

    case 'approve_tech_options':
      assertTransition(state.current_state === STATES.TECH_OPTIONS_APPROVAL_PENDING, event.type, state.current_state);
      approvePhase(state, PHASES.TECH_OPTIONS);
      state.approvals.tech_options = event.approvedAt || true;
      state.current_phase = PHASES.PLANNING;
      state.current_state = STATES.PLANNING_PENDING;
      clearGate(state);
      return withReason(state, 'tech-options-approved');

    default:
      throw makeError(ERROR_CODES.INVALID_TRANSITION, `unknown transition ${event.type}`);
  }
}

function expectedReviewStates(phase) {
  if (phase === PHASES.TECH_OPTIONS) return [STATES.TECH_OPTIONS_REVIEWING, STATES.TECH_OPTIONS_REWORK];
  if (phase === PHASES.DISCUSS) return [STATES.DECISION_SPEC_REVIEWING, STATES.DECISION_SPEC_REWORK];
  throw makeError(ERROR_CODES.INVALID_TRANSITION, `invalid review phase ${phase}`);
}

function clearActiveFindings(state) {
  state.blockers = [];
  state.open_questions = [];
}

export function applyGateResult(inputState, { phase, reviewer, verdict, findings = [] }) {
  assertGateVerdict(verdict);
  if (typeof reviewer !== 'string' || reviewer.length === 0) {
    throw makeError(ERROR_CODES.INVALID_TRANSITION, 'reviewer is required');
  }
  if (!Array.isArray(findings) || findings.some(item => typeof item !== 'string')) {
    throw makeError(ERROR_CODES.INVALID_TRANSITION, 'findings must be an array of strings');
  }

  const state = clone(validateState(inputState));
  const expectedStates = expectedReviewStates(phase);
  assertTransition(expectedStates.includes(state.current_state), `gate:${phase}:${verdict}`, state.current_state);

  if (verdict === GATE_VERDICTS.PASS) {
    clearActiveFindings(state);
    return withReason(state, `${phase}:${reviewer}:pass`);
  }

  const artifact = phase === PHASES.TECH_OPTIONS ? state.human_artifacts.tech_options : state.human_artifacts.decision_spec;
  if (verdict === GATE_VERDICTS.NEEDS_USER) {
    state.current_state = STATES.NEEDS_USER;
    state.open_questions.push(...findings);
    setGate(state, `${phase}_needs_user`, artifact);
    return withReason(state, `${phase}:${reviewer}:needs-user`);
  }

  const key = phase === PHASES.TECH_OPTIONS ? 'tech_options' : 'discuss';
  state.rework[key] += 1;
  if (state.rework[key] > REWORK_CAP) {
    state.current_state = STATES.NEEDS_USER;
    addBlocker(state, `${phase} exceeded rework cap.`);
    setGate(state, `${phase}_rework_cap_exceeded`, artifact);
    return withReason(state, `${phase}:${reviewer}:rework-cap-exceeded`);
  }
  state.current_state = phase === PHASES.TECH_OPTIONS ? STATES.TECH_OPTIONS_REWORK : STATES.DECISION_SPEC_REWORK;
  state.blockers.push(...findings);
  return withReason(state, `${phase}:${reviewer}:needs-rework`);
}

function normalizeReviewResults(phase, results) {
  const expected = REVIEWERS_BY_PHASE[phase];
  if (!expected) throw makeError(ERROR_CODES.INVALID_TRANSITION, `invalid review phase ${phase}`);
  if (!Array.isArray(results)) throw makeError(ERROR_CODES.INVALID_TRANSITION, 'results must be an array');

  const seen = new Set();
  for (const result of results) {
    if (!result || typeof result !== 'object') throw makeError(ERROR_CODES.INVALID_TRANSITION, 'review result must be an object');
    if (!expected.includes(result.reviewer)) throw makeError(ERROR_CODES.INVALID_TRANSITION, `unknown reviewer ${result.reviewer}`);
    if (seen.has(result.reviewer)) throw makeError(ERROR_CODES.INVALID_TRANSITION, `duplicate reviewer ${result.reviewer}`);
    assertGateVerdict(result.verdict);
    if (!Array.isArray(result.findings) || result.findings.some(item => typeof item !== 'string')) {
      throw makeError(ERROR_CODES.INVALID_TRANSITION, 'findings must be an array of strings');
    }
    seen.add(result.reviewer);
  }
  for (const reviewer of expected) {
    if (!seen.has(reviewer)) throw makeError(ERROR_CODES.INVALID_TRANSITION, `missing reviewer ${reviewer}`);
  }
  return results;
}

export function applyReviewResults(inputState, { phase, results }) {
  const normalized = normalizeReviewResults(phase, results);
  const needsUser = normalized.filter(result => result.verdict === GATE_VERDICTS.NEEDS_USER);
  if (needsUser.length > 0) {
    return applyGateResult(inputState, {
      phase,
      reviewer: needsUser.map(result => result.reviewer).join('+'),
      verdict: GATE_VERDICTS.NEEDS_USER,
      findings: needsUser.flatMap(result => result.findings),
    });
  }

  const needsRework = normalized.filter(result => result.verdict === GATE_VERDICTS.NEEDS_REWORK);
  if (needsRework.length > 0) {
    return applyGateResult(inputState, {
      phase,
      reviewer: needsRework.map(result => result.reviewer).join('+'),
      verdict: GATE_VERDICTS.NEEDS_REWORK,
      findings: needsRework.flatMap(result => result.findings),
    });
  }

  const state = clone(validateState(inputState));
  const expectedStates = expectedReviewStates(phase);
  assertTransition(expectedStates.includes(state.current_state), `review:${phase}:pass`, state.current_state);
  clearActiveFindings(state);
  if (phase === PHASES.DISCUSS) {
    state.current_state = STATES.DECISION_SPEC_APPROVAL_PENDING;
    setGate(state, 'decision_spec_approval', state.human_artifacts.decision_spec);
  } else {
    state.current_state = STATES.TECH_OPTIONS_APPROVAL_PENDING;
    setGate(state, 'tech_options_approval', state.human_artifacts.tech_options);
  }
  return withReason(state, `${phase}:reviewers:pass`);
}
