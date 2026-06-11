import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

const pluginRoot = new URL('../../../workflow/', import.meta.url);
const fromRoot = path => new URL(path, pluginRoot);

test('spec skill uses directory shape and standalone contract', async () => {
  const text = await readFile(fromRoot('skills/spec/SKILL.md'), 'utf8');
  assert.match(text, /name: spec/);
  assert.match(text, /research proposal first/i);
  assert.match(text, /one adaptive question/i);
  assert.match(text, /Intent Reviewer/);
  assert.match(text, /Testability Reviewer/);
  assert.match(text, /pass.*needs-rework.*needs-user/s);
});

test('tech-options skill uses directory shape and contains scorecard and audit boundary', async () => {
  const text = await readFile(fromRoot('skills/tech-options/SKILL.md'), 'utf8');
  assert.match(text, /name: tech-options/);
  assert.match(text, /approved needs/i);
  assert.match(text, /scorecard/i);
  assert.match(text, /third-party workflow packages as references only/i);
  assert.match(text, /artifact UX assessment/i);
  assert.match(text, /Reuse\/Coverage Reviewer/);
  assert.match(text, /Fit\/Risk Reviewer/);
});

test('workflow phase agents call reusable skills instead of embedding phase logic', async () => {
  const interviewer = await readFile(fromRoot('agents/interviewer.md'), 'utf8');
  const techOptions = await readFile(fromRoot('agents/tech-options-analyst.md'), 'utf8');
  const intentReviewer = await readFile(fromRoot('agents/intent-reviewer.md'), 'utf8');
  const testabilityReviewer = await readFile(fromRoot('agents/testability-reviewer.md'), 'utf8');
  const reuseReviewer = await readFile(fromRoot('agents/reuse-coverage-reviewer.md'), 'utf8');
  const fitReviewer = await readFile(fromRoot('agents/fit-risk-reviewer.md'), 'utf8');

  assert.match(interviewer, /mattpocock-skills:grill-me|grill-me/i);
  assert.match(techOptions, /Skill.*tech-options|tech-options skill/i);
  assert.match(intentReviewer, /Skill.*spec|spec skill/i);
  assert.match(testabilityReviewer, /Skill.*spec|spec skill/i);
  assert.match(reuseReviewer, /Skill.*tech-options|tech-options skill/i);
  assert.match(fitReviewer, /Skill.*tech-options|tech-options skill/i);
  assert.match(interviewer, /Schema return mode/);
  assert.match(interviewer, /requested schema field/);
  assert.match(interviewer, /Do not return status prose/);
  assert.match(techOptions, /Schema return mode/);
  assert.match(techOptions, /requested schema field/);
  assert.match(techOptions, /Do not return status prose/);
});
