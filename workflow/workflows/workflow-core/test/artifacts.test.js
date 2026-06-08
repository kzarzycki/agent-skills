import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, readdir, readFile, rm } from 'node:fs/promises';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { createWorkItemPaths, ensureWorkItem, writeHumanArtifact, writePhaseInternal, writeReviewInternal } from '../index.js';

async function tempRoot() {
  return mkdtemp(join(tmpdir(), 'workflow-artifacts-'));
}

test('default paths use .workflow work item state location', () => {
  const paths = createWorkItemPaths({ workId: '2026-06-07-example' });
  assert.equal(paths.root, '.workflow/2026-06-07-example');
  assert.equal(paths.stateFile, '.workflow/2026-06-07-example/_state/state.json');
});

test('rejects path-normalizing work ids', () => {
  assert.throws(() => createWorkItemPaths({ workId: '.' }), error => error.code === 'invalid-artifact-path');
});

test('creates root human artifacts and underscore internal dirs only', async () => {
  const baseDir = await tempRoot();
  try {
    const paths = createWorkItemPaths({ baseDir, workId: '2026-06-07-example' });
    await ensureWorkItem(paths);
    await writeHumanArtifact(paths, { ordinal: '01', slug: 'DECISION-SPEC', content: 'spec' });
    await writePhaseInternal(paths, { phase: 'discuss', filename: 'notes.md', content: 'internal' });
    await writeReviewInternal(paths, { phase: 'discuss', reviewer: 'intent', content: 'review' });

    const rootEntries = (await readdir(paths.root)).sort();
    assert.deepEqual(rootEntries, ['01-DECISION-SPEC.md', '_evidence', '_phases', '_reviews', '_state']);
    assert.equal(await readFile(join(paths.root, '01-DECISION-SPEC.md'), 'utf8'), 'spec');
    assert.equal(await readFile(join(paths.phasesDir, 'discuss', 'notes.md'), 'utf8'), 'internal');
    assert.equal(await readFile(join(paths.reviewsDir, 'discuss', 'intent.md'), 'utf8'), 'review');
    assert.ok(!rootEntries.includes('_history'));
  } finally {
    await rm(baseDir, { recursive: true, force: true });
  }
});

test('human artifacts are create-only by default', async () => {
  const baseDir = await tempRoot();
  try {
    const paths = createWorkItemPaths({ baseDir, workId: 'safe' });
    await writeHumanArtifact(paths, { ordinal: '01', slug: 'DECISION-SPEC', content: 'a' });
    await assert.rejects(() => writeHumanArtifact(paths, { ordinal: '01', slug: 'DECISION-SPEC', content: 'b' }), error => error.code === 'EEXIST');
    await writeHumanArtifact(paths, { ordinal: '01', slug: 'DECISION-SPEC', content: 'b', overwrite: true });
    assert.equal(await readFile(join(paths.root, '01-DECISION-SPEC.md'), 'utf8'), 'b');
  } finally {
    await rm(baseDir, { recursive: true, force: true });
  }
});

test('rejects unsafe artifact names', async () => {
  const baseDir = await tempRoot();
  try {
    const paths = createWorkItemPaths({ baseDir, workId: 'safe' });
    await assert.rejects(() => writeHumanArtifact(paths, { ordinal: '01', slug: '../BAD', content: '' }), error => error.code === 'invalid-artifact-path');
    await assert.rejects(() => writePhaseInternal(paths, { phase: '../x', filename: 'a.md', content: '' }), error => error.code === 'invalid-artifact-path');
  } finally {
    await rm(baseDir, { recursive: true, force: true });
  }
});
