#!/usr/bin/env node
import assert from 'node:assert/strict';
import { mkdir, readFile, rm } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  advanceWorkflow,
  applyWorkflowEvent,
  createInitialState,
  createWorkItemPaths,
  ensureWorkItem,
  loadState,
  PHASES,
  saveState,
  STATES,
  writeHumanArtifact,
} from '../workflow-core/index.js';

const prompt = 'Build a small browser tic-tac-toe game for two local players.';
const baseDir = join(dirname(fileURLToPath(import.meta.url)), 'runs', 'tic-tac-toe-workflow');
const workId = 'tic-tac-toe-game';

function logStep(message) {
  console.log(`\n== ${message}`);
}

async function approve(event, payload = {}) {
  const state = await loadState(paths.stateFile);
  const result = await applyWorkflowEvent({
    baseDir,
    workId,
    expectedRevision: state.revision,
    event,
    payload,
  });
  console.log(`${event}: ${result.phase}/${result.state} r${result.revision} ${result.kind}`);
  return result;
}

async function advance(label) {
  const result = await advanceWorkflow({ baseDir, workId, adapter });
  console.log(`${label}: ${result.phase}/${result.state} r${result.revision} ${result.kind}`);
  return result;
}

const adapter = {
  async researchBrief() {
    return {
      markdown: [
        '# Research Brief',
        '',
        `Prompt: ${prompt}`,
        '',
        'Useful constraints for the agent workflow:',
        '- Browser-only game; no backend needed.',
        '- Two local players alternate X/O turns.',
        '- Need win detection across rows, columns, diagonals.',
        '- Need draw detection after 9 filled cells.',
        '- Need reset control and visible status text.',
      ].join('\n'),
    };
  },
  async decisionSpec() {
    return {
      markdown: [
        '# 01 — Decision Spec',
        '',
        '## Goal',
        'Build a small browser tic-tac-toe game for two local players.',
        '',
        '## Question / problem',
        'A user needs a clear, bounded implementation plan for a playable tic-tac-toe game.',
        '',
        '## User and value',
        'A local user can open the game, play alternating X/O turns, see the result, and reset.',
        '',
        '## Desired behavior',
        '- 3x3 board starts empty.',
        '- X moves first, then turns alternate.',
        '- Clicking an occupied square does not change board state.',
        '- A row, column, or diagonal of one symbol ends the game.',
        '- Filling the board without a winner shows a draw.',
        '- Reset clears board and returns to X.',
        '',
        '## Rejected alternatives',
        '- Online multiplayer: outside the simple local scope.',
        '- AI opponent: changes game logic and testing scope.',
        '- Backend persistence: no value for local play.',
        '',
        '## Acceptance criteria',
        '- X starts and turn label changes after legal moves.',
        '- All eight win lines are detectable.',
        '- Illegal clicks after game end or on occupied cells are ignored.',
        '- Full board without winner reports draw.',
        '- Reset restores initial state.',
        '',
        '## Approval record',
        'Simulated human approves this bounded Decision Spec.',
      ].join('\n'),
    };
  },
  async reviewDecisionSpec() {
    return {
      results: [
        { reviewer: 'intent', verdict: 'pass', findings: [] },
        { reviewer: 'testability', verdict: 'pass', findings: [] },
      ],
      markdownByReviewer: {
        intent: '# Intent Review\n\npass — scope preserves local two-player tic-tac-toe.\n',
        testability: '# Testability Review\n\npass — acceptance criteria cover wins, draw, illegal moves, reset.\n',
      },
    };
  },
  async techOptions() {
    return {
      markdown: [
        '# 02 — Tech Options',
        '',
        '## Needs',
        '- Small browser game with deterministic state transitions.',
        '- Easy manual or Playwright-style verification.',
        '- No backend or build complexity.',
        '',
        '## Options considered',
        '1. Plain HTML/CSS/JS module — minimal moving parts and enough for game state.',
        '2. React component — familiar but unnecessary dependency for 9 cells.',
        '3. Canvas rendering — harder accessibility and click-target testing.',
        '',
        '## Scorecard',
        '| Need | Plain JS | React | Canvas |',
        '|---|---|---|---|',
        '| Minimal setup | strong | medium | strong |',
        '| Testable DOM state | strong | strong | weak |',
        '| Maintainability | strong | medium | medium |',
        '',
        '## Recommended option',
        'Use plain HTML/CSS/JS with an array of 9 cells, a `currentPlayer`, and derived winner/draw checks.',
        '',
        '## Rejected alternatives',
        '- React: dependency not justified.',
        '- Canvas: less direct DOM semantics for tests and accessibility.',
        '',
        '## Approval record',
        'Simulated human approves plain JS implementation path.',
      ].join('\n'),
    };
  },
  async reviewTechOptions() {
    return {
      results: [
        { reviewer: 'reuse-coverage', verdict: 'pass', findings: [] },
        { reviewer: 'fit-risk', verdict: 'pass', findings: [] },
      ],
      markdownByReviewer: {
        'reuse-coverage': '# Reuse/Coverage Review\n\npass — compares plain JS, React, and Canvas against approved needs.\n',
        'fit-risk': '# Fit/Risk Review\n\npass — recommendation avoids dependency and artifact sprawl.\n',
      },
    };
  },
};

await rm(baseDir, { recursive: true, force: true });
await mkdir(baseDir, { recursive: true });
const paths = createWorkItemPaths({ baseDir, workId });

logStep('Seed work item');
await ensureWorkItem(paths);
await writeHumanArtifact(paths, {
  ordinal: '01',
  slug: 'DECISION-SPEC',
  content: `# 01 — Decision Spec\n\n## Original prompt\n\n${prompt}\n\nPending research approval.\n`,
});
await writeHumanArtifact(paths, {
  ordinal: '02',
  slug: 'TECH-OPTIONS',
  content: '# 02 — Tech Options\n\nPending approved Decision Spec.\n',
});
await saveState(paths.stateFile, createInitialState({ workId }), { expectedRevision: null });
console.log(`root: ${paths.root}`);
console.log('initial: discuss/research_proposal_pending r0 human_gate');

logStep('Simulate human: approve research buckets');
await approve('approve_research_buckets', { bucketIds: ['browser-game', 'local-state-machine', 'testability'] });

logStep('Autonomous Discuss phase');
await advance('research brief');
await advance('decision spec');
await advance('decision spec review');

let state = await loadState(paths.stateFile);
assert.equal(state.current_state, STATES.DECISION_SPEC_APPROVAL_PENDING);
assert.equal(state.pending_gate.kind, 'decision_spec_approval');
console.log(`gate: ${state.pending_gate.kind} -> ${state.pending_gate.target_artifact}`);

logStep('Simulate human: approve Decision Spec and Tech Options research');
await approve('approve_decision_spec', { approvedAt: 'simulated-human' });
await approve('approve_tech_options_research');

logStep('Autonomous Tech Options phase');
await advance('tech options');
await advance('tech options review');

state = await loadState(paths.stateFile);
assert.equal(state.current_state, STATES.TECH_OPTIONS_APPROVAL_PENDING);
assert.equal(state.pending_gate.kind, 'tech_options_approval');
console.log(`gate: ${state.pending_gate.kind} -> ${state.pending_gate.target_artifact}`);

logStep('Simulate human: approve Tech Options');
await approve('approve_tech_options', { approvedAt: 'simulated-human' });

const finalState = await loadState(paths.stateFile);
assert.equal(finalState.current_phase, PHASES.PLANNING);
assert.equal(finalState.current_state, STATES.PLANNING_PENDING);
assert.deepEqual(finalState.approved_phases, [PHASES.DISCUSS, PHASES.TECH_OPTIONS]);
assert.equal(finalState.pending_gate, null);

const decisionSpec = await readFile(join(paths.root, '01-DECISION-SPEC.md'), 'utf8');
const techOptions = await readFile(join(paths.root, '02-TECH-OPTIONS.md'), 'utf8');
assert.match(decisionSpec, /tic-tac-toe/);
assert.match(decisionSpec, /Acceptance criteria/);
assert.match(techOptions, /Plain HTML\/CSS\/JS/);
assert.match(techOptions, /Recommended option/);

logStep('Final outputs');
console.log(`final: ${finalState.current_phase}/${finalState.current_state} r${finalState.revision}`);
console.log(`approved phases: ${finalState.approved_phases.join(', ')}`);
console.log(`decision spec: ${join(paths.root, '01-DECISION-SPEC.md')}`);
console.log(`tech options: ${join(paths.root, '02-TECH-OPTIONS.md')}`);
console.log('\n--- 01-DECISION-SPEC.md ---');
console.log(decisionSpec);
console.log('\n--- 02-TECH-OPTIONS.md ---');
console.log(techOptions);
console.log('\nPASS tic-tac-toe workflow e2e');
