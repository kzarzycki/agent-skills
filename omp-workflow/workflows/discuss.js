import { createWorkItemScaffold } from '../workflow-core/index.js';

export const meta = {
  name: 'discuss',
  description: 'Standalone Discuss capability. Research proposal first; optionally saves root numbered artifacts.',
  whenToUse: 'Args: { prompt: string, save?: boolean, title?: string }. Does not call workflow-start or workflow-resume.',
  phases: [{ title: 'Discuss' }],
};

const a = typeof args === 'string' ? JSON.parse(args) : (args || {});
const prompt = a.prompt || a.task;
const save = a.save === true;

function slugify(value) {
  return String(value || 'discuss-item').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 60) || 'discuss-item';
}

if (!prompt) {
  log('No prompt provided.');
  return { error: 'no prompt provided' };
}

phase('Discuss');
log('Research proposal comes first. Approve, narrow, or reject buckets before grilling.');

if (!save) {
  return { mode: 'ephemeral', prompt, next: 'Propose research buckets, then ask one adaptive question at a time.' };
}

const today = new Date().toISOString().slice(0, 10);
const workId = `${today}-${slugify(a.title || prompt)}`;
const scaffold = await createWorkItemScaffold({ workId, prompt, includeTechOptionsStub: false });
if (!scaffold.created) {
  log(`Work item already exists: ${scaffold.paths.root}`);
  return { error: 'work item exists', workId };
}
return { mode: 'saved', workId, root: scaffold.paths.root, currentArtifact: '01-DECISION-SPEC.md' };
