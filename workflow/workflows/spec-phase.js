export const meta = {
  name: 'spec-phase',
  description: 'Spec convergence loop via phase-loop (draft → review → rework → format gate; no interviewing). Args: {workId, pluginRoot, instructions?, contentFrozen?} → {status, rounds, verdicts, formatGate, artifact}. Requires existing draft + _phases/spec/ notes.',
  whenToUse: 'Stateless: agents read/write work-item files only.',
};

const a = typeof args === 'string' ? JSON.parse(args) : (args || {});
if (!a.pluginRoot) return { error: 'no pluginRoot provided (the workflow plugin dir containing contracts/)' };
return await workflow({ scriptPath: `${a.pluginRoot}/workflows/phase-loop.js` }, { ...a, phase: 'spec' });
