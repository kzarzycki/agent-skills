import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

const pluginRoot = new URL('../../', import.meta.url);
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

test('workflow-advance live adapter uses real plugin reviewer agents behind a format gate', async () => {
  const text = await readFile(fromRoot('workflows/workflow-advance.js'), 'utf8');
  assert.doesNotMatch(text, /agentType: 'reviewer'/);
  assert.doesNotMatch(text, /agentType: 'researcher'/);
  assert.match(text, /'intent-reviewer'/);
  assert.match(text, /'testability-reviewer'/);
  assert.match(text, /'reuse-coverage-reviewer'/);
  assert.match(text, /'fit-risk-reviewer'/);
  assert.match(text, /mdsmith check -c/);
  assert.match(text, /structureViolations/);
});

test('workflow-advance live adapter feeds blockers into rework prompts and paths into agents', async () => {
  const text = await readFile(fromRoot('workflows/workflow-advance.js'), 'utf8');
  assert.match(text, /state\.blockers/);
  assert.match(text, /Rework input/);
  assert.match(text, /DECISION_SPEC_REWORK/);
  assert.match(text, /TECH_OPTIONS_REWORK/);
  assert.match(text, /paths\.root/);
  assert.match(text, /interview-notes\.md/);
});

test('workflow start and spec scaffold via the shared work item helper', async () => {
  const start = await readFile(fromRoot('workflows/workflow-start.js'), 'utf8');
  assert.match(start, /createWorkItemScaffold/);
  assert.match(start, /includeTechOptionsStub: true/);
  assert.match(start, /work item exists/);
  assert.doesNotMatch(start, /audience: human/, 'no YAML frontmatter stub left inline');

  const spec = await readFile(fromRoot('workflows/spec.js'), 'utf8');
  assert.match(spec, /createWorkItemScaffold/);
  assert.match(spec, /includeTechOptionsStub: false/);
  assert.doesNotMatch(spec, /audience: human/, 'no YAML frontmatter stub left inline');
});

test('research-brief fans out lowercase explore agents and honors bucket args', async () => {
  const text = await readFile(new URL('../../../workflow/workflows/research-brief.js', import.meta.url), 'utf8');
  assert.match(text, /agentType: 'explore'/);
  assert.doesNotMatch(text, /agentType: 'Explore'/);
  assert.match(text, /a\.buckets/);
});
