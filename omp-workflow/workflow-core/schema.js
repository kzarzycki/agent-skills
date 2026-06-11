export const SCHEMA_VERSION = 1;

export const PHASES = Object.freeze({ SPEC: 'spec', TECH_OPTIONS: 'tech_options', PLANNING: 'planning' });

export const STATES = Object.freeze({
  RESEARCH_PROPOSAL_PENDING: 'research_proposal_pending',
  RESEARCH_RUNNING: 'research_running',
  SPEC_GRILLING: 'spec_grilling',
  DECISION_SPEC_REVIEWING: 'decision_spec_reviewing',
  DECISION_SPEC_REWORK: 'decision_spec_rework',
  DECISION_SPEC_APPROVAL_PENDING: 'decision_spec_approval_pending',
  TECH_OPTIONS_RESEARCH_PENDING: 'tech_options_research_pending',
  TECH_OPTIONS_RUNNING: 'tech_options_running',
  TECH_OPTIONS_REVIEWING: 'tech_options_reviewing',
  TECH_OPTIONS_REWORK: 'tech_options_rework',
  TECH_OPTIONS_APPROVAL_PENDING: 'tech_options_approval_pending',
  SPEC_ADDENDUM_PENDING: 'spec_addendum_pending',
  PLANNING_PENDING: 'planning_pending',
  NEEDS_USER: 'needs_user',
});

export const GATE_VERDICTS = Object.freeze({ PASS: 'pass', NEEDS_REWORK: 'needs-rework', NEEDS_USER: 'needs-user' });

export const REVIEWERS_BY_PHASE = Object.freeze({
  [PHASES.SPEC]: Object.freeze(['intent', 'testability']),
  [PHASES.TECH_OPTIONS]: Object.freeze(['reuse-coverage', 'fit-risk']),
});

export const ERROR_CODES = Object.freeze({
  INVALID_STATE_SCHEMA: 'invalid-state-schema',
  UNSUPPORTED_STATE_VERSION: 'unsupported-state-version',
  STALE_STATE_REVISION: 'stale-state-revision',
  INVALID_GATE_VERDICT: 'invalid-gate-verdict',
  INVALID_TRANSITION: 'invalid-transition',
  INVALID_ARTIFACT_PATH: 'invalid-artifact-path',
});

export const REWORK_CAP = 2;

const STATES_BY_PHASE = Object.freeze({
  [PHASES.SPEC]: new Set([
    STATES.RESEARCH_PROPOSAL_PENDING,
    STATES.RESEARCH_RUNNING,
    STATES.SPEC_GRILLING,
    STATES.DECISION_SPEC_REVIEWING,
    STATES.DECISION_SPEC_REWORK,
    STATES.DECISION_SPEC_APPROVAL_PENDING,
    STATES.NEEDS_USER,
  ]),
  [PHASES.TECH_OPTIONS]: new Set([
    STATES.TECH_OPTIONS_RESEARCH_PENDING,
    STATES.TECH_OPTIONS_RUNNING,
    STATES.TECH_OPTIONS_REVIEWING,
    STATES.TECH_OPTIONS_REWORK,
    STATES.TECH_OPTIONS_APPROVAL_PENDING,
    STATES.SPEC_ADDENDUM_PENDING,
    STATES.NEEDS_USER,
  ]),
  [PHASES.PLANNING]: new Set([STATES.PLANNING_PENDING, STATES.NEEDS_USER]),
});

function codedError(code, message) {
  const error = new Error(message);
  error.code = code;
  return error;
}

function isObject(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function assertString(value, path) {
  if (typeof value !== 'string' || value.length === 0) throw codedError(ERROR_CODES.INVALID_STATE_SCHEMA, `${path} must be a non-empty string`);
}

function assertNumber(value, path) {
  if (!Number.isInteger(value) || value < 0) throw codedError(ERROR_CODES.INVALID_STATE_SCHEMA, `${path} must be a non-negative integer`);
}

function assertStringArray(value, path) {
  if (!Array.isArray(value) || value.some(item => typeof item !== 'string')) throw codedError(ERROR_CODES.INVALID_STATE_SCHEMA, `${path} must be an array of strings`);
}

function assertKnown(value, allowed, path) {
  if (!Object.values(allowed).includes(value)) throw codedError(ERROR_CODES.INVALID_STATE_SCHEMA, `${path} has unknown value: ${value}`);
}

function assertExactKeys(value, allowedKeys, path) {
  const allowed = new Set(allowedKeys);
  for (const key of Object.keys(value)) {
    if (!allowed.has(key)) throw codedError(ERROR_CODES.INVALID_STATE_SCHEMA, `${path} has unknown key: ${key}`);
  }
}

function assertPhaseStateCompatibility(phase, state) {
  if (!STATES_BY_PHASE[phase].has(state)) {
    throw codedError(ERROR_CODES.INVALID_STATE_SCHEMA, `current_state ${state} is not valid for current_phase ${phase}`);
  }
}

function validateApprovals(approvals) {
  assertExactKeys(approvals, ['research_buckets', 'decision_spec', 'tech_options'], 'approvals');
  if (approvals.research_buckets !== undefined) assertStringArray(approvals.research_buckets, 'approvals.research_buckets');
  for (const key of ['decision_spec', 'tech_options']) {
    const value = approvals[key];
    if (value !== undefined && typeof value !== 'string' && typeof value !== 'boolean') {
      throw codedError(ERROR_CODES.INVALID_STATE_SCHEMA, `approvals.${key} must be string or boolean`);
    }
  }
}

export function createInitialState({ workId }) {
  assertString(workId, 'workId');
  return {
    schema_version: SCHEMA_VERSION,
    work_id: workId,
    revision: 0,
    current_phase: PHASES.SPEC,
    current_state: STATES.RESEARCH_PROPOSAL_PENDING,
    approved_phases: [],
    blockers: [],
    open_questions: [],
    last_transition_reason: 'work-item-created',
    pending_gate: { kind: 'research_approval', target_artifact: '01-DECISION-SPEC.md' },
    rework: { spec: 0, tech_options: 0 },
    human_artifacts: { decision_spec: '01-DECISION-SPEC.md', tech_options: '02-TECH-OPTIONS.md' },
    approvals: {},
  };
}

export function validateState(state) {
  if (!isObject(state)) throw codedError(ERROR_CODES.INVALID_STATE_SCHEMA, 'state must be an object');
  assertExactKeys(state, [
    'schema_version', 'work_id', 'revision', 'current_phase', 'current_state', 'approved_phases',
    'blockers', 'open_questions', 'last_transition_reason', 'pending_gate', 'rework', 'human_artifacts', 'approvals',
  ], 'state');

  if (state.schema_version !== SCHEMA_VERSION) {
    if (Number.isInteger(state.schema_version)) throw codedError(ERROR_CODES.UNSUPPORTED_STATE_VERSION, `unsupported state schema ${state.schema_version}`);
    throw codedError(ERROR_CODES.INVALID_STATE_SCHEMA, 'schema_version must be 1');
  }

  assertString(state.work_id, 'work_id');
  assertNumber(state.revision, 'revision');
  assertKnown(state.current_phase, PHASES, 'current_phase');
  assertKnown(state.current_state, STATES, 'current_state');
  assertPhaseStateCompatibility(state.current_phase, state.current_state);
  assertStringArray(state.approved_phases, 'approved_phases');
  for (const phase of state.approved_phases) assertKnown(phase, PHASES, 'approved_phases[]');
  assertStringArray(state.blockers, 'blockers');
  assertStringArray(state.open_questions, 'open_questions');
  assertString(state.last_transition_reason, 'last_transition_reason');

  if (state.pending_gate !== null && state.pending_gate !== undefined) {
    if (!isObject(state.pending_gate)) throw codedError(ERROR_CODES.INVALID_STATE_SCHEMA, 'pending_gate must be null or object');
    assertExactKeys(state.pending_gate, ['kind', 'target_artifact'], 'pending_gate');
    assertString(state.pending_gate.kind, 'pending_gate.kind');
    assertString(state.pending_gate.target_artifact, 'pending_gate.target_artifact');
  }

  if (!isObject(state.rework)) throw codedError(ERROR_CODES.INVALID_STATE_SCHEMA, 'rework must be an object');
  assertExactKeys(state.rework, ['spec', 'tech_options'], 'rework');
  assertNumber(state.rework.spec, 'rework.spec');
  assertNumber(state.rework.tech_options, 'rework.tech_options');

  if (!isObject(state.human_artifacts)) throw codedError(ERROR_CODES.INVALID_STATE_SCHEMA, 'human_artifacts must be an object');
  assertExactKeys(state.human_artifacts, ['decision_spec', 'tech_options'], 'human_artifacts');
  assertString(state.human_artifacts.decision_spec, 'human_artifacts.decision_spec');
  assertString(state.human_artifacts.tech_options, 'human_artifacts.tech_options');

  if (!isObject(state.approvals)) throw codedError(ERROR_CODES.INVALID_STATE_SCHEMA, 'approvals must be an object');
  validateApprovals(state.approvals);
  return state;
}

export function assertGateVerdict(verdict) {
  if (!Object.values(GATE_VERDICTS).includes(verdict)) throw codedError(ERROR_CODES.INVALID_GATE_VERDICT, `invalid gate verdict: ${verdict}`);
}

export function makeError(code, message) {
  return codedError(code, message);
}
