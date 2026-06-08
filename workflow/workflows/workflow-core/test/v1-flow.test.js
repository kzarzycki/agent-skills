import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, readdir, rm } from 'node:fs/promises';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { createInitialState, createWorkItemPaths, ensureWorkItem, runScriptedV1Flow, transition, writeHumanArtifact } from '../index.js';

async function tempRoot() {
  return mkdtemp(join(tmpdir(), 'workflow-v1-'));
}

test('scripted v1 flow reaches planning pending', () => {
  const state = runScriptedV1Flow();
  assert.equal(state.current_state, 'planning_pending');
  assert.deepEqual(state.approved_phases, ['discuss', 'tech_options']);
  assert.equal(state.rework.discuss, 1);
  assert.equal(state.pending_gate, null);
});

test('partial research approval excludes denied buckets', () => {
  let state = createInitialState({ workId: 'x' });
  state = transition(state, { type: 'approve_research_buckets', bucketIds: ['local-omp', 'skills'] });
  assert.deepEqual(state.approvals.research_buckets, ['local-omp', 'skills']);
});

test('denied research becomes needs-user and clears the research gate', () => {
  const state = transition(createInitialState({ workId: 'x' }), { type: 'deny_all_research' });
  assert.equal(state.current_state, 'needs_user');
  assert.equal(state.pending_gate, null);
});

test('empty research approval becomes needs-user and clears the research gate', () => {
  const state = transition(createInitialState({ workId: 'x' }), { type: 'approve_research_buckets', bucketIds: [] });
  assert.equal(state.current_state, 'needs_user');
  assert.equal(state.pending_gate, null);
});

test('root human artifacts are stable and internals are underscored', async () => {
  const baseDir = await tempRoot();
  try {
    const paths = createWorkItemPaths({ baseDir, workId: '2026-06-07-vague-workflow-idea' });
    await ensureWorkItem(paths);
    await writeHumanArtifact(paths, { ordinal: '01', slug: 'DECISION-SPEC', content: 'spec' });
    await writeHumanArtifact(paths, { ordinal: '02', slug: 'TECH-OPTIONS', content: 'tech' });
    const entries = (await readdir(paths.root)).sort();
    assert.deepEqual(entries, ['01-DECISION-SPEC.md', '02-TECH-OPTIONS.md', '_evidence', '_phases', '_reviews', '_state']);
  } finally {
    await rm(baseDir, { recursive: true, force: true });
  }
});
