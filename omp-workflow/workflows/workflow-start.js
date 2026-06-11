import { createWorkItemScaffold } from '../workflow-core/index.js';

export const meta = {
  name: 'workflow-start',
  description: 'Start a durable workflow work item with root numbered human artifacts and _state/state.json.',
  whenToUse: 'Args: { prompt: string, title?: string }. Creates .workflow/<work-id>/ and stops at the first human research-approval gate.',
  phases: [{ title: 'Start' }],
};

const a = typeof args === 'string' ? JSON.parse(args) : (args || {});
const prompt = a.prompt || a.task;
const title = a.title || prompt;

function slugify(value) {
  return String(value || 'workflow-item').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 60) || 'workflow-item';
}

if (!prompt) {
  log('No prompt provided.');
  return { error: 'no prompt provided' };
}

phase('Start');
const today = new Date().toISOString().slice(0, 10);
const workId = `${today}-${slugify(title)}`;
const scaffold = await createWorkItemScaffold({ workId, prompt, includeTechOptionsStub: true });
if (!scaffold.created) {
  log(`Work item already exists: ${scaffold.paths.root}`);
  return { error: 'work item exists', workId };
}

log(`Workflow created: ${scaffold.paths.root}`);
log('Current human artifact: 01-DECISION-SPEC.md');
return { workId, root: scaffold.paths.root, currentArtifact: '01-DECISION-SPEC.md', state: scaffold.state.current_state };
