import { transition } from './reducer.js';
import { STATES, ERROR_CODES, makeError, PHASES } from './schema.js';
import { createWorkItemPaths, writeHumanArtifact, writePhaseInternal, writeReviewInternal } from './artifacts.js';
import { loadState, saveState } from './state-store.js';
import { applyReviewResults } from './reducer.js';
import { getResumeAction, getNextAction } from './status.js';

const HUMAN_EVENTS = new Set([
  'approve_research_buckets',
  'deny_all_research',
  'approve_decision_spec',
  'approve_tech_options_research',
  'approve_discuss_addendum',
  'approve_tech_options',
]);

function invalid(message) {
  throw makeError(ERROR_CODES.INVALID_TRANSITION, message);
}

function resultFor(workId, state, extra = {}) {
  const next = getNextAction(state);
  return {
    workId,
    revision: state.revision,
    phase: state.current_phase,
    state: state.current_state,
    kind: next.kind,
    action: getResumeAction(state),
    ...extra,
  };
}

export async function applyWorkflowEvent({ baseDir = '.workflow', workId, expectedRevision, event, payload = {} }) {
  if (!HUMAN_EVENTS.has(event)) invalid(`${event} is not a human event`);
  const paths = createWorkItemPaths({ baseDir, workId });
  const state = await loadState(paths.stateFile);
  if (expectedRevision !== undefined && expectedRevision !== state.revision) {
    throw makeError(ERROR_CODES.STALE_STATE_REVISION, `expected revision ${expectedRevision}, found ${state.revision}`);
  }
  const nextState = transition(state, { type: event, ...payload });
  const saved = await saveState(paths.stateFile, nextState, { expectedRevision: state.revision });
  return resultFor(workId, saved);
}

async function requireAdapter(adapter, name, context) {
  if (!adapter || typeof adapter[name] !== 'function') invalid(`adapter.${name} is required for ${context}`);
  return adapter[name](context);
}

async function persist(paths, state) {
  return saveState(paths.stateFile, state, { expectedRevision: state.revision });
}

export async function advanceWorkflow({ baseDir = '.workflow', workId, adapter }) {
  const paths = createWorkItemPaths({ baseDir, workId });
  const state = await loadState(paths.stateFile);
  if (state.pending_gate) return resultFor(workId, state);

  if (state.current_state === STATES.RESEARCH_RUNNING) {
    const brief = await requireAdapter(adapter, 'researchBrief', { state, paths });
    await writePhaseInternal(paths, { phase: PHASES.DISCUSS, filename: 'research-brief.md', content: brief.markdown });
    const saved = await persist(paths, transition(state, { type: 'research_brief_ready' }));
    return resultFor(workId, saved, { wrote: '_phases/discuss/research-brief.md' });
  }

  if (state.current_state === STATES.DISCUSS_GRILLING) {
    const spec = await requireAdapter(adapter, 'decisionSpec', { state, paths });
    await writeHumanArtifact(paths, { ordinal: '01', slug: 'DECISION-SPEC', content: spec.markdown, overwrite: true });
    const saved = await persist(paths, transition(state, { type: 'questions_complete' }));
    return resultFor(workId, saved, { wrote: '01-DECISION-SPEC.md' });
  }

  if (state.current_state === STATES.DECISION_SPEC_REWORK) {
    const spec = await requireAdapter(adapter, 'decisionSpec', { state, paths });
    await writeHumanArtifact(paths, { ordinal: '01', slug: 'DECISION-SPEC', content: spec.markdown, overwrite: true });
    const saved = await persist(paths, transition(state, { type: 'decision_spec_rework_complete' }));
    return resultFor(workId, saved, { wrote: '01-DECISION-SPEC.md' });
  }


  if (state.current_state === STATES.DECISION_SPEC_REVIEWING) {
    const review = await requireAdapter(adapter, 'reviewDecisionSpec', { state, paths });
    for (const [reviewer, markdown] of Object.entries(review.markdownByReviewer || {})) {
      await writeReviewInternal(paths, { phase: PHASES.DISCUSS, reviewer, content: markdown });
    }
    const saved = await persist(paths, applyReviewResults(state, { phase: PHASES.DISCUSS, results: review.results }));
    return resultFor(workId, saved, { wrote: '_reviews/discuss/*.md' });
  }

  if (state.current_state === STATES.TECH_OPTIONS_RUNNING) {
    const options = await requireAdapter(adapter, 'techOptions', { state, paths });
    await writeHumanArtifact(paths, { ordinal: '02', slug: 'TECH-OPTIONS', content: options.markdown, overwrite: true });
    const saved = await persist(paths, transition(state, { type: 'tech_options_ready' }));
    return resultFor(workId, saved, { wrote: '02-TECH-OPTIONS.md' });
  }

  if (state.current_state === STATES.TECH_OPTIONS_REWORK) {
    const options = await requireAdapter(adapter, 'techOptions', { state, paths });
    await writeHumanArtifact(paths, { ordinal: '02', slug: 'TECH-OPTIONS', content: options.markdown, overwrite: true });
    const saved = await persist(paths, transition(state, { type: 'tech_options_rework_complete' }));
    return resultFor(workId, saved, { wrote: '02-TECH-OPTIONS.md' });
  }


  if (state.current_state === STATES.TECH_OPTIONS_REVIEWING) {
    const review = await requireAdapter(adapter, 'reviewTechOptions', { state, paths });
    for (const [reviewer, markdown] of Object.entries(review.markdownByReviewer || {})) {
      await writeReviewInternal(paths, { phase: PHASES.TECH_OPTIONS, reviewer, content: markdown });
    }
    const saved = await persist(paths, applyReviewResults(state, { phase: PHASES.TECH_OPTIONS, results: review.results }));
    return resultFor(workId, saved, { wrote: '_reviews/tech_options/*.md' });
  }

  if (state.current_state === STATES.PLANNING_PENDING) return resultFor(workId, state, { done: true });
  invalid(`no autonomous advance for ${state.current_state}`);
}
