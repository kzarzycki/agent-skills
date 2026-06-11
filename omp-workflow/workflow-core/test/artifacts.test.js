import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, readdir, readFile, rm } from 'node:fs/promises';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { createWorkItemPaths, createWorkItemScaffold, ensureWorkItem, writeHumanArtifact, writePhaseInternal, writeReviewInternal } from '../index.js';

async function tempRoot() {
  return mkdtemp(join(tmpdir(), 'workflow-artifacts-'));
}

const readContract = async name => JSON.parse(await readFile(new URL(`../../../workflow/contracts/${name}`, import.meta.url), 'utf8'));

function sectionHeadings(markdown) {
  return [...markdown.matchAll(/^## (.+)$/gm)].map(match => match[1]);
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
    await writePhaseInternal(paths, { phase: 'spec', filename: 'notes.md', content: 'internal' });
    await writeReviewInternal(paths, { phase: 'spec', reviewer: 'intent', content: 'review' });

    const rootEntries = (await readdir(paths.root)).sort();
    assert.deepEqual(rootEntries, ['01-DECISION-SPEC.md', '_evidence', '_phases', '_reviews', '_state']);
    assert.equal(await readFile(join(paths.root, '01-DECISION-SPEC.md'), 'utf8'), 'spec');
    assert.equal(await readFile(join(paths.phasesDir, 'spec', 'notes.md'), 'utf8'), 'internal');
    assert.equal(await readFile(join(paths.reviewsDir, 'spec', 'intent.md'), 'utf8'), 'review');
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

test('createWorkItemScaffold writes contract-conform stubs with state', async () => {
  const baseDir = await tempRoot();
  try {
    const result = await createWorkItemScaffold({ baseDir, workId: '2026-06-11-scaffold', prompt: 'Build the thing.' });
    assert.equal(result.created, true);
    assert.equal(result.state.current_state, 'research_proposal_pending');

    const spec = await readFile(join(result.paths.root, '01-DECISION-SPEC.md'), 'utf8');
    assert.match(spec.split('\n')[0], /^# /, 'line 1 is an H1 title');
    assert.doesNotMatch(spec, /^---/, 'no YAML frontmatter');
    assert.deepEqual(sectionHeadings(spec), (await readContract('decision-spec.json')).sections);
    assert.match(spec, /Build the thing\./);

    const tech = await readFile(join(result.paths.root, '02-TECH-OPTIONS.md'), 'utf8');
    assert.match(tech.split('\n')[0], /^# /, 'line 1 is an H1 title');
    assert.doesNotMatch(tech, /^---/, 'no YAML frontmatter');
    assert.deepEqual(sectionHeadings(tech), (await readContract('tech-options.json')).sections);

    const again = await createWorkItemScaffold({ baseDir, workId: '2026-06-11-scaffold', prompt: 'Different.' });
    assert.equal(again.created, false);
    assert.match(await readFile(join(result.paths.root, '01-DECISION-SPEC.md'), 'utf8'), /Build the thing\./);
  } finally {
    await rm(baseDir, { recursive: true, force: true });
  }
});

test('createWorkItemScaffold can skip the tech options stub', async () => {
  const baseDir = await tempRoot();
  try {
    const result = await createWorkItemScaffold({ baseDir, workId: '2026-06-11-spec-only', prompt: 'Spec only.', includeTechOptionsStub: false });
    assert.equal(result.created, true);
    const rootEntries = (await readdir(result.paths.root)).sort();
    assert.deepEqual(rootEntries, ['01-DECISION-SPEC.md', '_evidence', '_phases', '_reviews', '_state']);
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
