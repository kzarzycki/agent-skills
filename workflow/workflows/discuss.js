import { unlink } from 'node:fs/promises';
import { createInitialState, createWorkItemPaths, ensureWorkItem, saveState, writeHumanArtifact } from './workflow-core/index.js';

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
const paths = createWorkItemPaths({ workId });
await ensureWorkItem(paths);
const state = createInitialState({ workId });
const artifactPaths = [];
artifactPaths.push(await writeHumanArtifact(paths, {
  ordinal: '01',
  slug: 'DECISION-SPEC',
  content: `---\naudience: human\nartifact_type: decision_spec\nphase: discuss\nstatus: research_proposal_pending\n---\n\n# 01 — Decision Spec\n\n## Original prompt\n\n${prompt}\n\n## Current gate\n\nApprove, narrow, or reject the research proposal before Discuss continues.\n`,
}));
artifactPaths.push(await writeHumanArtifact(paths, {
  ordinal: '02',
  slug: 'TECH-OPTIONS',
  content: `---\naudience: human\nartifact_type: tech_options\nphase: tech_options\nstatus: pending_decision_spec\n---\n\n# 02 — Tech Options\n\nPending approved Decision Spec.\n`,
}));
try {
  await saveState(paths.stateFile, state, { expectedRevision: null });
} catch (error) {
  await Promise.all(artifactPaths.map(path => unlink(path).catch(() => {})));
  throw error;
}
return { mode: 'saved', workId, root: paths.root, currentArtifact: '01-DECISION-SPEC.md' };
