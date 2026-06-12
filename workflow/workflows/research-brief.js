export const meta = {
  name: 'research-brief',
  description: 'Research filter for the Spec phase. Fans out research angles on a work item and returns a short brief plus the questions for the user.',
  whenToUse: 'Args: { prompt: string, buckets?: string[] }. One research agent per bucket when given; three default angles otherwise. Returns { brief, openThreads }.',
  phases: [{ title: 'Research' }, { title: 'Synthesize' }],
};

const a = typeof args === 'string' ? JSON.parse(args) : (args || {});
const prompt = a.prompt || a.task;
if (!prompt) {
  log('No prompt provided.');
  return { error: 'no prompt provided' };
}

const ANGLES = [
  { id: 'reuse', lens: 'existing tools, code, or libraries that already do this or part of it. Search the repo and the wider ecosystem.' },
  { id: 'product', lens: 'product and user unknowns: who uses it, what outcome they want, what is plausibly in or out of scope.' },
  { id: 'feasibility', lens: 'technical feasibility, constraints, risks, and version or compatibility concerns.' },
];

const FIND = {
  type: 'object',
  additionalProperties: false,
  required: ['angle', 'findings'],
  properties: {
    angle: { type: 'string' },
    findings: { type: 'array', items: { type: 'string' } },
  },
};

const buckets = Array.isArray(a.buckets) && a.buckets.length > 0 ? a.buckets : null;
const angles = buckets
  ? buckets.map((lens, i) => ({ id: `bucket-${i + 1}`, lens }))
  : ANGLES;

phase('Research');
const perAngle = await parallel(angles.map(x => () => agent(
  `Work item:\n${prompt}\n\nResearch this angle: ${x.lens}\nReturn concrete findings: names, versions, file paths, facts.`,
  { label: `research:${x.id}`, phase: 'Research', schema: FIND, agentType: 'Explore' },
)));

const ok = perAngle.filter(Boolean);
if (ok.length === 0) {
  return { error: `research failed: all ${angles.length} bucket agents died — fix the agent config and resume this run`, buckets: angles.map(x => x.id) };
}
if (ok.length < angles.length) {
  log(`WARNING: ${angles.length - ok.length}/${angles.length} bucket agents failed; brief covers only the surviving buckets`);
}

phase('Synthesize');
const BRIEF = {
  type: 'object',
  additionalProperties: false,
  required: ['brief', 'openThreads'],
  properties: {
    brief: { type: 'string' },
    openThreads: { type: 'array', items: { type: 'string' } },
  },
};
const out = await agent(
  'Synthesize these findings into a brief (<= 200 words) that sharpens an interview with the user about this work item. ' +
  'Then list openThreads: the questions only the user can answer (product intent, priorities, preferences).\n\n' +
  ok.map(r => `## ${r.angle}\n` + r.findings.join('\n')).join('\n\n'),
  { label: 'synthesize', phase: 'Synthesize', schema: BRIEF },
);

log(`Brief ready; ${out.openThreads.length} open threads for the user.`);
const failed = angles.length - ok.length;
return failed > 0 ? { ...out, failedBuckets: failed } : out;
