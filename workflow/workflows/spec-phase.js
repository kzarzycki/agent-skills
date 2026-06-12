export const meta = {
  name: 'spec-phase',
  description: 'Run the Spec convergence loop by delegation: thin wrapper over phase-loop.js with phase=spec. A fresh draft goes straight to review; the author reworks only on findings and runs the format gate itself. No interviewing happens inside.',
  whenToUse: 'Args: { workId: string, pluginRoot: string, instructions?: string, contentFrozen?: boolean }. Returns { status, rounds, verdicts, formatGate, artifact }. status: pass | needs-user | rework-cap-exceeded | error. Requires an existing draft plus _phases/spec/ notes. Stateless: agents read/write work-item files only.',
};

const a = typeof args === 'string' ? JSON.parse(args) : (args || {});
if (!a.pluginRoot) return { error: 'no pluginRoot provided (the workflow plugin dir containing contracts/)' };
return await workflow({ scriptPath: `${a.pluginRoot}/workflows/phase-loop.js` }, { ...a, phase: 'spec' });
