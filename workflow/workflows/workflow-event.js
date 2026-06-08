import { applyWorkflowEvent } from './workflow-core/index.js';

export const meta = {
  name: 'workflow-event',
  description: 'Apply one human/controller event to a durable workflow state file.',
  whenToUse: 'Args: { workId: string, expectedRevision?: number, event: string, payload?: object }. Events include approve_research_buckets, deny_all_research, approve_decision_spec, approve_tech_options_research, approve_discuss_addendum, approve_tech_options.',
  phases: [{ title: 'Event' }],
};

const a = typeof args === 'string' ? JSON.parse(args) : (args || {});
if (!a.workId) {
  log('No args.workId provided.');
  return { error: 'no workId provided' };
}
if (!a.event) {
  log('No args.event provided.');
  return { error: 'no event provided' };
}

phase('Event');
const result = await applyWorkflowEvent({
  workId: a.workId,
  expectedRevision: a.expectedRevision,
  event: a.event,
  payload: a.payload || {},
});
log(`workflow ${result.workId}: ${result.phase}/${result.state} r${result.revision}`);
return result;
