import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdir, mkdtemp, rm, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { createInitialState, loadState, saveState } from '../index.js';

async function tempRoot() {
  return mkdtemp(join(tmpdir(), 'workflow-state-'));
}

async function writeState(root, state) {
  const path = join(root, '_state', 'state.json');
  await mkdir(join(root, '_state'), { recursive: true });
  await writeFile(path, JSON.stringify(state), 'utf8');
  return path;
}

test('initial save and load state', async () => {
  const root = await tempRoot();
  try {
    const path = join(root, '_state', 'state.json');
    const state = createInitialState({ workId: '2026-06-07-example' });
    const written = await saveState(path, state, { expectedRevision: null });
    assert.equal(written.revision, 0);
    const loaded = await loadState(path);
    assert.equal(loaded.work_id, '2026-06-07-example');
    assert.equal(loaded.current_state, 'research_proposal_pending');
    assert.equal(loaded.pending_gate.target_artifact, '01-DECISION-SPEC.md');
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test('invalid schema throws code', async () => {
  const root = await tempRoot();
  try {
    const path = await writeState(root, { work_id: 123 });
    await assert.rejects(() => loadState(path), error => error.code === 'invalid-state-schema');
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test('unsupported schema version throws code', async () => {
  const root = await tempRoot();
  try {
    const path = await writeState(root, { ...createInitialState({ workId: 'x' }), schema_version: 999 });
    await assert.rejects(() => loadState(path), error => error.code === 'unsupported-state-version');
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test('unknown keys and malformed approvals are rejected', async () => {
  const root = await tempRoot();
  try {
    let path = await writeState(root, { ...createInitialState({ workId: 'x' }), extra: true });
    await assert.rejects(() => loadState(path), error => error.code === 'invalid-state-schema');
    path = await writeState(root, { ...createInitialState({ workId: 'x' }), approvals: { research_buckets: [123] } });
    await assert.rejects(() => loadState(path), error => error.code === 'invalid-state-schema');
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test('phase and state mismatches are rejected', async () => {
  const root = await tempRoot();
  try {
    const path = await writeState(root, { ...createInitialState({ workId: 'x' }), current_phase: 'planning' });
    await assert.rejects(() => loadState(path), error => error.code === 'invalid-state-schema');
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test('stale revision rejected', async () => {
  const root = await tempRoot();
  try {
    const path = join(root, '_state', 'state.json');
    const state = createInitialState({ workId: 'x' });
    await saveState(path, state, { expectedRevision: null });
    await saveState(path, state, { expectedRevision: 0 });
    await assert.rejects(() => saveState(path, state, { expectedRevision: 0 }), error => error.code === 'stale-state-revision');
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});
