Research a topic with the engine's `research-brief` workflow.

Arguments: $ARGUMENTS (the research topic or question)

Follow these steps:

1. Scope: if a `.workflow/<yyyy-mm-dd>-<slug>/` work item is active and the topic relates to it, tie the research to that item; otherwise treat it as standalone.

2. Run the research workflow instead of reimplementing research:
   `Workflow({ name: 'workflow:research-brief', args: { prompt: "<topic>" } })` — it fans research angles out across subagents and returns `{ brief, openThreads }`. Pass `buckets: [...]` only if you already know the angles to split on.

3. Write the returned `brief` + `openThreads` to:
   - Tied to a work item: `<item>/_phases/spec/research-brief.md`.
   - Standalone: a path the user names (or the session scratchpad).

4. Present the brief and the open questions to the user.
