import { createInitialState } from './schema.js';
import { transition, applyReviewResults } from './reducer.js';

export const DEFAULT_SCRIPTED_FLOW = Object.freeze({
  workId: '2026-06-07-vague-workflow-idea',
  approvedBucketIds: ['local-omp', 'skills'],
});

export function runScriptedV1Flow(flow = DEFAULT_SCRIPTED_FLOW) {
  let state = createInitialState({ workId: flow.workId });
  state = transition(state, { type: 'approve_research_buckets', bucketIds: flow.approvedBucketIds });
  state = transition(state, { type: 'research_brief_ready' });
  state = transition(state, { type: 'questions_complete' });
  state = applyReviewResults(state, {
    phase: 'spec',
    results: [
      { reviewer: 'intent', verdict: 'needs-rework', findings: ['Clarify standalone spec value.'] },
      { reviewer: 'testability', verdict: 'pass', findings: [] },
    ],
  });
  state = applyReviewResults(state, {
    phase: 'spec',
    results: [
      { reviewer: 'intent', verdict: 'pass', findings: [] },
      { reviewer: 'testability', verdict: 'pass', findings: [] },
    ],
  });
  state = transition(state, { type: 'approve_decision_spec', approvedAt: '2026-06-07' });
  state = transition(state, { type: 'approve_tech_options_research' });
  state = transition(state, { type: 'tech_options_ready' });
  state = applyReviewResults(state, {
    phase: 'tech_options',
    results: [
      { reviewer: 'reuse-coverage', verdict: 'pass', findings: [] },
      { reviewer: 'fit-risk', verdict: 'pass', findings: [] },
    ],
  });
  state = transition(state, { type: 'approve_tech_options', approvedAt: '2026-06-07' });
  return state;
}
