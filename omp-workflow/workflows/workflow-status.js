import { createWorkItemPaths, loadState, renderStatus } from '../workflow-core/index.js';

export const meta = {
  name: 'workflow-status',
  description: 'Show workflow state and current human-facing artifact. Hides internal files by default.',
  whenToUse: 'Args: { workId: string, debug?: boolean }.',
  phases: [{ title: 'Status' }],
};

const a = typeof args === 'string' ? JSON.parse(args) : (args || {});
if (!a.workId) {
  log('No args.workId provided.');
  return { error: 'no workId provided' };
}

phase('Status');
const paths = createWorkItemPaths({ workId: a.workId });
const state = await loadState(paths.stateFile);
const output = renderStatus(state, { debug: a.debug === true });
log(output);
return { workId: a.workId, status: output };
