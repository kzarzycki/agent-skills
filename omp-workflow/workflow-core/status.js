function firstOrNone(values) {
  return values.length > 0 ? values[0] : '(none)';
}

export function renderStatus(state, { debug = false } = {}) {
  const lines = [
    `work_id: ${state.work_id}`,
    `phase: ${state.current_phase}`,
    `state: ${state.current_state}`,
    `approved_phases: ${state.approved_phases.join(', ') || '(none)'}`,
    `rework.spec: ${state.rework.spec}`,
    `rework.tech_options: ${state.rework.tech_options}`,
    `current_human_artifact: ${state.pending_gate?.target_artifact || '(none)'}`,
  ];
  if (state.pending_gate) lines.push(`pending_gate: ${state.pending_gate.kind}`);
  lines.push(`blockers_count: ${state.blockers.length}`);
  lines.push(`current_blocker: ${firstOrNone(state.blockers)}`);
  lines.push(`open_questions_count: ${state.open_questions.length}`);
  lines.push(`current_open_question: ${firstOrNone(state.open_questions)}`);
  if (debug) {
    lines.push(`blockers: ${state.blockers.join(' | ') || '(none)'}`);
    lines.push(`open_questions: ${state.open_questions.join(' | ') || '(none)'}`);
    lines.push('internal_dirs: _state/ _phases/ _reviews/ _evidence/');
  }
  return lines.join('\n');
}

export function getNextAction(state) {
  if (state.pending_gate) {
    return {
      kind: 'human_gate',
      gate: state.pending_gate.kind,
      targetArtifact: state.pending_gate.target_artifact,
    };
  }
  if (state.current_state === 'planning_pending') return { kind: 'done', phase: state.current_phase, state: state.current_state };
  if (state.current_state === 'needs_user') return { kind: 'blocked', phase: state.current_phase, state: state.current_state };
  return { kind: 'autonomous_step', phase: state.current_phase, state: state.current_state };
}

export function getResumeAction(state) {
  if (state.pending_gate) {
    return {
      kind: 'redisplay_gate',
      gate: state.pending_gate.kind,
      targetArtifact: state.pending_gate.target_artifact,
    };
  }
  if (state.current_state === 'needs_user') {
    return {
      kind: 'blocked',
      phase: state.current_phase,
      state: state.current_state,
    };
  }
  return {
    kind: 'continue',
    phase: state.current_phase,
    state: state.current_state,
  };
}
