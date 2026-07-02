---
name: deep-research
description: "Multi-round multi-source research (Perplexity, Tavily, Exa, Gemini, WebSearch) producing a cited report with confidence scores and gaps."
when_to_use: "Any nontrivial research request ('research X', 'what's the latest on', 'look into'), or when a decision/report needs verified multi-source evidence."
---

# Deep Research

Multi-round, multi-source research orchestration for Claude Code. Produces structured
reports by dispatching parallel research agents across multiple search providers, iterating
until coverage is comprehensive.

## Philosophy

The difference between a web search and deep research is **iteration and triangulation**.
A single search returns surface-level results. Deep research decomposes questions into angles,
searches across independent sources, identifies what's missing, searches again with refined
queries, and synthesizes findings only when coverage is sufficient. This skill replicates
the pattern used by commercial deep research products (Claude Research, Gemini Deep Research,
Perplexity Deep Research) using Claude Code's agent system and MCP integrations.

## Two-Phase Design

The skill operates in two distinct phases:

1. **Planning** (interactive) — Detect tools, interview the user, propose a research plan
2. **Execution** (autonomous) — Run multi-round research without pausing until done

Never skip the planning phase. The interview shapes the entire research — angles, recency
requirements, depth expectations, and output format all come from the user's input.

## Step 0: Establish the date

Before any research, run `date +%Y-%m-%d` to get today's date. This prevents stale year
assumptions from training data and ensures recency filtering uses the correct baseline.

---

## Phase 0: Discovery & Planning

### Step 1: Detect available tools

Check which MCP tools are available by attempting to use them or checking the tool list.
Build an inventory:

**Deep research channels (thorough, multi-step — these are the primary tools):**

| Channel | Tool / Skill | How it works |
|---------|-------------|-------------|
| Perplexity Deep Research | `perplexity_research` | Multi-source investigation via API. Does its own iterative search+read+synthesize loop internally. |
| Perplexity Reasoning | `perplexity_reason` | Step-by-step logical analysis with web grounding. |
| Tavily Deep Research | `tavily_research` | Multi-step research via API. Iterates internally across sources. |
| Gemini Deep Research | `browser-researcher` agent + gemini skill | Browser automation at gemini.google.com. Browses hundreds of sites. Plan review: gated. |
| ChatGPT Deep Research | `browser-researcher` agent + chatgpt skill | Browser automation at chatgpt.com. Uses o3/o4-mini reasoning. Plan review: gated. |
| Claude.ai Deep Research | `browser-researcher` agent + claude-ai skill | Browser automation at claude.ai. Plan review: informational (auto-starts, can stop & restart). |

All of these do their own internal multi-round research — they are not simple search
queries. They are the core of what makes this skill "deep." Use them as the primary
research channels, not as fallbacks.

**Supplementary tools (for targeted lookups, gap-filling, reading specific sources):**

| Channel | Tools |
|---------|-------|
| Perplexity | `perplexity_search`, `perplexity_ask` |
| Tavily | `tavily_search`, `tavily_extract`, `tavily_crawl` |
| Exa | `web_search_exa`, `crawling` |
| Gemini | `ask-gemini`, `brainstorm` |
| Native | `WebSearch`, `WebFetch` (always available) |

These are faster, lighter tools useful for filling specific gaps, verifying claims,
reading individual pages, or brainstorming additional angles.

Present the full inventory to the user: "I have N search channels available, including
Gemini Deep Research and ChatGPT Deep Research which can run in the background while
faster MCP tools handle other angles."

If no MCPs are available, inform the user that research will use native tools + deep
research skills. Ask if they want to proceed or install MCPs first.

### Step 2: Interview the user

Ask these questions (adapt based on what's already clear from context):

1. **What's the research question?** — Get the core topic. Clarify scope if vague.
2. **How recent must the data be?** — Always ask explicitly. Never assume a default recency based on the topic domain. The user decides what "recent" means for their specific question.
3. **What angles matter most?** — The user often knows what dimensions they care about. If they provide angles, use them. If not, you'll generate them in decomposition.
4. **What's the output for?** — A presentation, decision, report, or just curiosity? This shapes depth and format.
5. **Where should I save the output?** — Suggest `.work/<topic>/` if Flow workspace exists, otherwise ask.

### Step 3: Propose the research plan

Based on the interview, present a plan:

```
Research: [topic]
Recency: [cutoff]
Rounds: [user-specified limit, or "until coverage is met"]
Angles: [list of research angles]
Channels: [which MCPs/tools will be used]
Output: [path]
Estimated agents: [N per round]
```

Wait for user approval before proceeding. They may adjust angles, add requirements, or change scope.

---

## Phase 1: Decompose

After approval, prepare the research dispatch.

### Generate research angles

Break the topic into distinct, non-overlapping angles. The number is adaptive based on
topic complexity — bias toward thoroughness (typically 5-10 for complex topics, fewer for
narrow questions). Each angle becomes one research agent's responsibility. Good angles are:
- Specific enough for targeted searching
- Independent enough to research in parallel
- Comprehensive enough to cover the topic together

### Generate search queries

For each angle, generate specific search queries. The count is adaptive — scale with angle
complexity (simple angles: 5-10, complex: 15-25, bias toward dense). This is critical —
agents with specific query lists produce dramatically better results than agents told to
"research X."

Include varied query patterns:
- Exact phrases in quotes for precision
- Site-specific queries for known sources (site:mckinsey.com, site:arxiv.org)
- Year-filtered queries ("2026", "March 2026")
- Question-form queries ("how many companies use X")
- Comparison queries ("X vs Y 2026")

### Tool access

Give each agent access to all available MCP tools and native WebSearch/WebFetch. Agents
decide which tools to use based on what they find. **Prefer deep research tools**
(`perplexity_research`, `tavily_research`, `perplexity_reason`) — these do multi-step
research internally and produce richer results than simple search queries.

See `references/tool-guide.md` for what each tool can do.

---

## Phase 2: Research Rounds

### Dispatching deep research channels (first, all in parallel)

Spawn all available deep research channels simultaneously as background agents. Each
gets the core research question (or a specific angle if the topic is broad enough to
split across them). They all do their own internal multi-round research independently.

- **Perplexity/Tavily deep research**: Agents using `perplexity_research`, `tavily_research`,
  `perplexity_reason` as their primary tools. Each agent focuses on a research angle.
- **Gemini Deep Research**: Spawn `browser-researcher` agent with Gemini skill:
  ```
  Agent(name="gemini", subagent_type="browser-researcher",
        prompt="skill_path: ~/.claude/skills/gemini-deep-research/SKILL.md\nresearch_prompt: <topic>\noutput_path: .work/gemini-report.md\ncaller: <your name>",
        run_in_background=true)
  ```
- **ChatGPT Deep Research**: Spawn `browser-researcher` agent with ChatGPT skill:
  ```
  Agent(name="chatgpt", subagent_type="browser-researcher",
        prompt="skill_path: ~/.claude/skills/chatgpt-deep-research/SKILL.md\nresearch_prompt: <topic>\noutput_path: .work/chatgpt-report.md\ncaller: <your name>",
        run_in_background=true)
  ```
- **Claude.ai Deep Research**: Spawn `browser-researcher` agent with Claude.ai skill:
  ```
  Agent(name="claude-ai", subagent_type="browser-researcher",
        prompt="skill_path: ~/.claude/skills/claude-ai-deep-research/SKILL.md\nresearch_prompt: <topic>\noutput_path: .work/claude-ai-report.md\ncaller: <your name>",
        run_in_background=true)
  ```

All three use the same `browser-researcher` agent with different platform knowledge.
They communicate via SendMessage (prefixes: PLAN_READY, RESEARCH_PROGRESS, RESEARCH_COMPLETE, ERROR).
The browser-based research may take longer but produces comprehensive reports. The MCP-based
deep research tools return faster but are equally thorough per-query.

### Research polarity: plan two rounds for balanced topics

When researching a topic that has both positive and negative dimensions (ROI, impact,
effectiveness, adoption), general research agents naturally skew toward paradoxes,
anti-patterns, and cautionary findings. Academic/analyst sources emphasize what's
surprising, not what's working.

**Always plan two research rounds for balanced topics:**
1. **Round 1: General** — metrics, frameworks, analyst reports, anti-patterns
2. **Round 2: First-party success cases** — dedicated agents hunting for company
   engineering blogs, conference talks, investor reports, press releases.
   Vendor-sourced cases (vendor claiming "customer X saved Y") should be flagged
   as "VENDOR-SOURCED — LOWER TRUST."

Without Round 2, the synthesis will be skewed. Check after Round 1 whether results
lean heavily in one direction, and compensate with targeted agents for the
underrepresented angle.

### Dispatching supplementary agents (for specific angles)

For research angles that need targeted searches, specific source reading, or gap-filling,
spawn additional agents with supplementary tools (`perplexity_search`, `tavily_search`,
`web_search_exa`, `WebSearch`, `WebFetch`, etc.). These handle:

1. **Specific angles** not covered by the deep research channels
2. **Targeted queries** for niche sub-topics
3. **Source reading** — fetching and reading specific URLs or papers
4. **Verification** — cross-checking claims from deep research reports

Read `references/agent-prompts.md` for the full prompt template. Inline all context into
each agent prompt — context doesn't cross agent boundaries.

**Agent output requirements:**
Each agent must write its findings to a file at the designated output path and return:
- A 2-3 line summary of key findings
- A list of identified gaps (what they couldn't find or what needs deeper investigation)
- Source count and confidence assessment

### Collecting results

As agents complete, read their output files. Don't read entire files into context — use
grep, head, or offset+limit reads to extract what's needed for gap analysis.

### Outline refinement (after Round 1 only)

Before gap analysis, check whether Round 1 findings contradict the original research plan.
Evidence sometimes reveals that the decomposition was wrong — an angle was irrelevant, a
critical sub-topic was missed entirely, or assumptions in the plan were unfounded. If so,
restructure the angles for Round 2 rather than doubling down on a flawed plan. This prevents
the sunk-cost fallacy of researching angles that evidence shows are unproductive.

### Gap analysis

After all agents in a round complete, assess coverage:

1. **Angle coverage**: Is each original angle adequately addressed? Mark as strong/weak/missing.
2. **Contradictions**: Do sources disagree on key claims? Flag for resolution.
3. **Recency gaps**: Are findings current enough given the recency requirement?
4. **Specificity gaps**: Are findings granular enough or too surface-level?
5. **Source diversity**: Are findings triangulated across independent sources?

### Iteration decision

Spawn another round if:
- Any angle has weak or missing coverage
- Unresolved contradictions exist between sources
- User's key questions remain unanswered
- Sources are too old given recency requirements

Stop if:
- All angles have strong coverage
- Key questions are answered with citations
- Maximum rounds reached (default: 3, configurable in plan)
- Diminishing returns (round N found nothing new)

For Round 2+, generate **new, targeted queries** based on specific gaps — don't re-run
the same queries. Focus agents on the weak spots.

---

## Phase 3: Synthesis

When coverage is sufficient, delegate synthesis to a **dedicated agent**. The synthesis
agent reads research files directly from disk — do NOT pass research content through
the orchestrator's context (this only multiplies token use).

### Synthesis agent setup

The orchestrator provides the synthesis agent with:
1. **File paths**: list of all research output files from all rounds, **including
   Gemini Deep Research and ChatGPT Deep Research reports** if they completed
2. **Report format**: path to `references/report-format.md`
3. **Synthesis brief**: a short summary of angles covered, key themes observed,
   contradictions to resolve, and the user's original question + output purpose

If deep research skills are still running when MCP-based rounds are done, wait for them
before synthesizing — their reports are typically the richest single sources.

The synthesis agent then:
- Reads all research files from disk
- Cross-references claims across sources
- Identifies claims supported by multiple independent sources vs. single-source claims
- Resolves contradictions by noting both positions and evidence strength
- Writes the final report to the agreed output path

Read `references/agent-prompts.md` for the synthesis agent prompt template.

### Report structure

Use the template in `references/report-format.md`. Core sections:

1. **Executive Summary** — 3-5 bullet points, the headline findings
2. **Key Findings** — organized by angle, with inline citations
3. **Data & Statistics** — quantitative findings in tables where possible
4. **Contradictions & Debates** — where sources disagree, present both sides
5. **Gaps & Limitations** — what couldn't be found, what needs further research
6. **Source Index** — all sources with title, author/org, date, URL, and a quality indicator

### Confidence scoring

Rate each major finding on a **1-10 scale**:
- Source count: 1-3 points (1 source = 1pt, 2 sources = 2pts, 3+ = 3pts)
- Source independence: 1-2 points (all same type = 1pt, diverse types = 2pts)
- Recency: 1-2 points (outdated = 1pt, within recency cutoff = 2pts)
- Agreement across sources: 1-3 points (contradicted = 1pt, partial = 2pts, strong agreement = 3pts)

### Source quality indicators

Flag source type: independent research, academic, vendor-funded, consulting firm,
journalist, blog/opinion. This matters because vendor-funded studies consistently show
more optimistic results than independent research.

### Present results

After the synthesis agent completes, present a brief summary (5-10 lines) to the user
with the file path, inviting them to read the full report and ask follow-up questions.

---

## Recency Filtering

Recency is a first-class parameter because in fast-moving fields, outdated research is
misleading. When a study from 6 months ago used previous-generation AI models, its
findings may not apply to current tools.

**How to enforce recency:**
- Tavily: use `start_date` parameter (format: YYYY-MM-DD)
- Tavily: use `time_range` parameter (day/week/month/year)
- Perplexity: include year in search queries ("2026", "March 2026")
- Exa: include temporal terms in queries
- All agents: instruct them to verify publication dates and flag outdated sources

**When the user says "recent" or "latest":**
Always ask what they mean — never assume a default based on topic domain. Different users
have different recency needs even within the same field.

Always note which model generation a study's data reflects if relevant (e.g., a study
testing GPT-4 may not apply to GPT-5 era).

### Known Obsolete Studies

Research agents gravitate toward highly-cited older studies even when given strict date
filters, because these studies dominate search engine rankings. Include an explicit
**KNOWN OBSOLETE** blocklist in every research agent prompt to prevent this.

When dispatching agents, add to each prompt:
```
KNOWN OBSOLETE — do NOT cite as current evidence:
- METR Jul 2025 "experienced devs 19% slower with AI" — pre-agentic, METR retracted
  the experimental design in their Feb 2026 update
- [add other obsolete studies as they are identified]
Reference these only as HISTORICAL CONTEXT with explicit "LEGACY" label.
```

During synthesis, run a dedicated **obsolescence pass** checking all cited studies
against this blocklist before finalizing the report. Research agents WILL cite these
studies despite date filters — the blocklist is the only reliable defense.

### Recency-aware synthesis checklist

Before finalizing any research report, verify:
- [ ] No obsolete studies cited as current evidence
- [ ] Each finding tagged with model/tool generation it measured (autocomplete vs agentic)
- [ ] Findings from different eras are not mixed without context
- [ ] The most recent evidence is weighted most heavily in recommendations

---

## Adaptive Behavior

This skill does not use fixed configuration defaults. All parameters are adaptive:

- **Rounds**: no hard limit. Keep researching until coverage is met or the user specifies a cap.
- **Agents per round**: one per angle, count determined by topic complexity.
- **Searches per agent**: scale with angle complexity. Bias toward thorough.
- **Recency**: always determined during interview, never assumed.
- **Output format**: markdown by default, configurable during interview.

---

## Error Handling

- **MCP tool fails**: Fall back to native WebSearch for that agent's queries. Note the degradation in the report.
- **Agent times out**: Read partial output if available. Spawn replacement for missing coverage.
- **All MCPs unavailable**: Proceed with native tools only. Inform user of reduced breadth.
- **Topic too broad**: During interview, suggest narrowing scope or splitting into multiple research sessions.
- **Topic too narrow**: Reduce angle count, increase depth per angle.

---

## References

- `references/tool-guide.md` — Detailed MCP tool capabilities, parameters, and assignment strategy
- `references/agent-prompts.md` — Template for research agent prompts
- `references/report-format.md` — Output report template
