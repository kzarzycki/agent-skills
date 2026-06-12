export const meta = {
  name: 'tech-options-phase',
  description: 'Run the Tech Options phase by delegation: thin wrapper over phase-loop.js with phase=tech_options. The analyst authors/reworks 02-TECH-OPTIONS.md and runs the format gate itself; two independent reviewers judge in parallel; rework loops until pass, needs-user, or the rework cap.',
  whenToUse: 'Args: { workId: string, pluginRoot: string, instructions?: string, contentFrozen?: boolean }. Returns { status, rounds, verdicts, formatGate, artifact }. status: pass | needs-user | rework-cap-exceeded | error. Stateless: agents read/write work-item files only.',
};

const a = typeof args === 'string' ? JSON.parse(args) : (args || {});
if (!a.pluginRoot) return { error: 'no pluginRoot provided (the workflow plugin dir containing contracts/)' };
return await workflow({ scriptPath: `${a.pluginRoot}/workflows/phase-loop.js` }, { ...a, phase: 'tech_options' });
