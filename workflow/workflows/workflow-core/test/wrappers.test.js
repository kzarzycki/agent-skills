import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

const pluginRoot = new URL('../../../', import.meta.url);
const fromRoot = path => new URL(path, pluginRoot);

test('workflow-event wrapper delegates human events to core driver', async () => {
  const text = await readFile(fromRoot('workflows/workflow-event.js'), 'utf8');
  assert.match(text, /name: 'workflow-event'/);
  assert.match(text, /applyWorkflowEvent/);
  assert.match(text, /expectedRevision/);
  assert.match(text, /approve_research_buckets/);
});

test('workflow-advance wrapper delegates one autonomous step to core driver', async () => {
  const text = await readFile(fromRoot('workflows/workflow-advance.js'), 'utf8');
  assert.match(text, /name: 'workflow-advance'/);
  assert.match(text, /advanceWorkflow/);
  assert.match(text, /reviewDecisionSpec/);
  assert.match(text, /reviewTechOptions/);
  assert.match(text, /agent\(/);
});

test('workflow-advance live adapter passes approved research scope into research', async () => {
  const text = await readFile(fromRoot('workflows/workflow-advance.js'), 'utf8');
  assert.match(text, /state\.approvals\.research_buckets/);
  assert.match(text, /current artifact/i);
});

test('workflow-advance live adapter passes research brief into Decision Spec generation', async () => {
  const text = await readFile(fromRoot('workflows/workflow-advance.js'), 'utf8');
  assert.match(text, /research-brief\.md/);
  assert.match(text, /Research brief:/);
});

test('workflow start creates both selected human artifact slots', async () => {
  const text = await readFile(fromRoot('workflows/workflow-start.js'), 'utf8');
  assert.match(text, /slug: 'DECISION-SPEC'/);
  assert.match(text, /slug: 'TECH-OPTIONS'/);
  assert.match(text, /Pending approved Decision Spec/);
});
