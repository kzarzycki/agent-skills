Research a topic, optionally tied to a work stream.

Arguments: $ARGUMENTS (the research topic or question)

Follow these steps:

1. Determine research scope:
   - If the topic relates to an existing work stream: stream-specific research
   - Otherwise: standalone research (create a new .work/<slug>/ directory for it)

2. Check for existing research:
   - Stream-specific: check .work/<name>/research.md
   - If found: "Found existing research on [topic]. Build on it, or start fresh?"

3. Gather context for the research agent:
   - Read the research methodology from the flow skill's references/research.md
   - Read .work/brief.md
   - Read .work/standards/ (if any files exist)
   - If stream-specific: read the stream's ITEM.md and any existing research

4. Spawn research agent:
   - Inline ALL context into the prompt (methodology + brief + standards + stream context + the research question)
   - Use subagent_type: "general-purpose"
   - Description: "Research: <topic summary>"

5. Agent writes findings to .work/<name>/research.md and returns file path + summary.

6. Update ITEM.md status to "researching", add log entry, check progress box.
   Append to .work/log.md: "YYYY-MM-DD: Research completed — <topic>"

7. Present a brief summary of findings and recommendation to the user.
