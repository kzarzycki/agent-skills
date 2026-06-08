import { unlink } from 'node:fs/promises';
import { createInitialState, createWorkItemPaths, ensureWorkItem, saveState, writeHumanArtifact } from './workflow-core/index.js';

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

log(`Workflow created: ${paths.root}`);
log('Current human artifact: 01-DECISION-SPEC.md');
return { workId, root: paths.root, currentArtifact: '01-DECISION-SPEC.md', state: state.current_state };
