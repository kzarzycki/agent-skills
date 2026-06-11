import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { GATE_VERDICTS, PHASES, REVIEWERS_BY_PHASE, REWORK_CAP } from '../schema.js';
import { REVIEW_EVIDENCE_PATTERN, STATE_FILE_RELATIVE, createWorkItemPaths } from '../artifacts.js';

const pluginRoot = new URL('../../../workflow/', import.meta.url);
const fromRoot = path => new URL(path, pluginRoot);
const readJson = async path => JSON.parse(await readFile(fromRoot(path), 'utf8'));

test('work-item contract mirrors schema constants', async () => {
  const contract = await readJson('contracts/work-item.json');
  assert.deepEqual(contract.gateVerdicts, Object.values(GATE_VERDICTS));
  assert.deepEqual(contract.reviewersByPhase, {
    spec: [...REVIEWERS_BY_PHASE.spec],
    tech_options: [...REVIEWERS_BY_PHASE.tech_options],
  });
  assert.equal(contract.reworkCap, REWORK_CAP);
  assert.deepEqual(contract.phases, Object.values(PHASES));
});

test('work-item contract names the state file and review evidence layout', async () => {
  const contract = await readJson('contracts/work-item.json');
  assert.equal(contract.stateFile, STATE_FILE_RELATIVE);
  assert.equal(contract.reviewEvidencePattern, REVIEW_EVIDENCE_PATTERN);
  const paths = createWorkItemPaths({ workId: '2026-01-01-sample' });
  assert.ok(paths.stateFile.endsWith(`/${STATE_FILE_RELATIVE}`), 'stateFile suffix matches contract');
});

test('work-item contract mirrors createWorkItemPaths layout', async () => {
  const contract = await readJson('contracts/work-item.json');
  const paths = createWorkItemPaths({ workId: '2026-01-01-sample' });
  for (const value of Object.values(paths)) {
    assert.ok(value.startsWith('.workflow/'), `${value} starts with .workflow/`);
  }
  assert.equal(contract.baseDir, '.workflow');
  const dirs = [paths.stateDir, paths.phasesDir, paths.reviewsDir, paths.evidenceDir]
    .map(dir => dir.split('/').pop());
  assert.deepEqual(dirs, contract.underscoreDirs);
});

test('artifact contracts declare filenames and section counts', async () => {
  const decisionSpec = await readJson('contracts/decision-spec.json');
  assert.equal(decisionSpec.filename, '01-DECISION-SPEC.md');
  assert.equal(decisionSpec.sections.length, 12);

  const techOptions = await readJson('contracts/tech-options.json');
  assert.equal(techOptions.filename, '02-TECH-OPTIONS.md');
  assert.equal(techOptions.sections.length, 7);
});

test('artifact contracts declare structure rules mirrored by the mdsmith config', async () => {
  const yml = await readFile(fromRoot('contracts/mdsmith.yml'), 'utf8');
  for (const name of ['decision-spec', 'tech-options']) {
    const contract = await readJson(`contracts/${name}.json`);
    assert.equal(contract.closed, true, `${name} is closed`);
    assert.equal(contract.headingLevel, 2, `${name} sections are H2s`);
    assert.match(contract.title, /H1 on line 1/, `${name} title rule`);
    const kindBody = yml.split(`  ${name}:\n`)[1];
    assert.ok(kindBody, `mdsmith kind ${name} declared`);
    assert.match(kindBody, /closed: true/, `mdsmith ${name} kind is closed`);
  }
});

test('mdsmith config mirrors artifact contracts', async () => {
  const yml = await readFile(fromRoot('contracts/mdsmith.yml'), 'utf8');
  const decisionSpec = await readJson('contracts/decision-spec.json');
  const techOptions = await readJson('contracts/tech-options.json');

  const kindSections = (kind, nextKind) => {
    let body = yml.split(`  ${kind}:\n`)[1];
    assert.ok(body, `kind ${kind} declared`);
    if (nextKind) body = body.split(`  ${nextKind}:\n`)[0];
    return [...body.matchAll(/- heading: "([^"]+)"/g)].map(m => m[1]);
  };
  assert.deepEqual(kindSections('decision-spec', 'tech-options'), decisionSpec.sections);
  assert.deepEqual(kindSections('tech-options'), techOptions.sections);

  assert.ok(yml.includes(`filename: "${decisionSpec.filename}"`));
  assert.ok(yml.includes(`filename: "${techOptions.filename}"`));
});

test('skills point at contracts instead of restating them', async () => {
  const spec = await readFile(fromRoot('skills/spec/SKILL.md'), 'utf8');
  assert.match(spec, /contracts\/decision-spec\.json/);

  const techOptions = await readFile(fromRoot('skills/tech-options/SKILL.md'), 'utf8');
  assert.match(techOptions, /contracts\/tech-options\.json/);

  const workflow = await readFile(fromRoot('skills/workflow/SKILL.md'), 'utf8');
  assert.match(workflow, /contracts\/work-item\.json/);
  assert.ok(!workflow.includes('_decision-spec.md'), 'workflow skill must not mention _decision-spec.md');
});
