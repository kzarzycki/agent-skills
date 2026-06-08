import { createWorkItemPaths, getResumeAction, loadState, renderStatus } from './workflow-core/index.js';

export const meta = {
  name: 'workflow-resume',
  description: 'Resume a durable workflow from _state/state.json without duplicating root human artifacts.',
  whenToUse: 'Args: { workId: string, debug?: boolean }. Redisplays pending human gate or reports next runnable state.',
  phases: [{ title: 'Resume' }],
};

const a = typeof args === 'string' ? JSON.parse(args) : (args || {});
if (!a.workId) {
  log('No args.workId provided.');
  return { error: 'no workId provided' };
}

phase('Resume');
const paths = createWorkItemPaths({ workId: a.workId });
const state = await loadState(paths.stateFile);
const action = getResumeAction(state);
log(renderStatus(state, { debug: a.debug === true }));
return { workId: a.workId, action };
