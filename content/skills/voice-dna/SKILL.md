---
name: voice-dna
description: "Extract a person's LinkedIn writing voice DNA into an 8-dimension style profile with vocabulary fingerprint, signature moves, and a Prompt Engineering Guide."
when_to_use: "Analyzing someone's writing style, extracting voice DNA, or preparing a style profile for content creation — 'voice DNA', 'how does X write', 'style analysis'."
---

# Voice DNA — LinkedIn Style Extraction & Analysis

Extract a person's writing voice from their LinkedIn posts. Produce a reusable style profile with an 8-dimension analysis and a Prompt Engineering Guide for AI-assisted writing in that voice.

## What This Skill Produces

1. **Corpus file** — all LinkedIn posts with metadata (`projects/blogging/corpus/{handle}/linkedin-posts.md`)
2. **Mode classification** — posts categorized into 6 posting modes (`.work/style-research/{handle}-mode-classification.md`)
3. **Dimension analyses** — intermediate files for dims 1-4 and 5-8 (`.work/style-research/`)
4. **Final style profile** — synthesized profile with Prompt Engineering Guide (`projects/blogging/analyses/{handle}.md`)
5. **Blended voice profile** *(Phase 7)* — merged voice DNA from multiple profiles (`projects/blogging/analyses/blended-voice.md`)
6. **my-voice skill** *(Phase 7)* — auto-generated skill for content creation (`~/.claude/skills/my-voice/`)

## Prerequisites

- Chrome MCP tools (authenticated LinkedIn session in Chrome)
- Subagent capability (mode classification + parallel dimension analysis)
- The `linkedin` skill handles Chrome MCP setup; this skill handles the analysis workflow

## Workflow

### Phase 1: Interview

Before extracting anything, understand the user's intent. Ask:

1. **Who?** — Name, LinkedIn handle/URL. If not provided, search LinkedIn via Chrome.
2. **Why?** — This shapes the output, especially the blending notes:
   - *Content creation* — user wants to write like this person → focus blending notes on adoptable techniques
   - *Voice blending* — user wants to combine this voice with their own/others → focus on non-negotiable vs blendable elements
   - *Competitor study* — user wants to understand a peer's style → focus on differentiation opportunities
3. **What aspects interest you most?** — Humor, authenticity, structure, persuasion, etc. This guides emphasis in analysis.
4. **Audience context** — Who does this person write for? Who does the USER write for? The gap shapes the audience translation table in blending notes.
5. **Any known context?** — Role, industry, native language (affects human-sound markers analysis), relationship to the user.

If the user already provided answers in their initial request, don't re-ask — incorporate what they said.

### Phase 2: Extraction

Read `references/voyager-api.md` for the full technical reference.

**Summary of the approach:**
1. Navigate to `https://www.linkedin.com/in/{handle}/recent-activity/all/` in Chrome
2. Capture the Voyager API endpoint via `read_network_requests` after clicking "Show More"
3. Extract `profileUrn`, `queryId`, and CSRF token
4. Paginate through all posts using `paginationToken` (NOT `start` parameter)
5. Output JSON chunks via `console.log()` channel (JS return value gets blocked by content filter)
6. Parse into corpus markdown using `scripts/parse-voyager-corpus.py`

**Corpus format** (one post per section):
```markdown
## Post {N}

**Date:** YYYY-MM-DD
**Type:** Original/Repost
**Engagement:** {likes} likes, {comments} comments
**URL:** {url}

{full post text}

---
```

Save to: `projects/blogging/corpus/{handle}/linkedin-posts.md`

Update `.work/style-research/scratchpad.md` with extraction stats (post count, date range, originals vs reposts).

**If Voyager API fails** (can't capture endpoint, auth issues), fall back to DOM scraping — see the fallback section in `references/voyager-api.md`. DOM scraping works better on the user's own profile than on external profiles.

### Phase 3: Mode Classification

Spawn **1 subagent** to classify all posts. The agent needs:
- The corpus file
- `references/dimensions.md` (contains posting mode definitions and classification procedure)

**Agent prompt template:**

```
You are classifying LinkedIn posts into posting modes for a voice DNA analysis.

Read these files:
1. {corpus_path} — the full post corpus
2. {skill_path}/references/dimensions.md — Part 1 has the 6 posting modes and classification procedure

For each post, assign exactly one mode: authentic_voice, quick_reshare, marketing_provided, event_promo, thought_piece, or minimal_legacy.

Focus on the most recent 500 posts if the corpus is larger. For older posts, do temporal sampling (every 5th post) to confirm distribution holds.

Output format — save to {output_path}:
1. Summary table (mode, count, percentage)
2. Per-post classification: Post number, mode, confidence (high/medium/low), brief rationale for non-obvious classifications
3. Key observations about corpus composition

Subject-specific notes: {any context from the interview about this person's role, platform, likely mode distribution}
```

**After classification completes:** Present the summary table to the user for sanity-check before proceeding. Let them flag any misclassifications or patterns you missed.

### Phase 4: 8-Dimension Analysis

After user approves mode classification, spawn **2 parallel subagents**:

**Agent A — Dimensions 1-4 (Voice, Language, Humor, Thought Leadership):**

```
You are analyzing the writing style of {name} across 4 dimensions.

Read these files:
1. {corpus_path} — full corpus
2. {mode_classification_path} — use ONLY authentic_voice and thought_piece posts
3. {skill_path}/references/dimensions.md — Part 2, dimensions 1-4

For each dimension:
- Position the author on every spectrum (percentage + characterization)
- Cite specific evidence (post numbers + verbatim quotes)
- Flag any anti-patterns detected
- Note temporal evolution if patterns shift across years

Special attention to: {aspects the user highlighted in interview}
Context: {person's role, native language, audience — affects language register analysis}

Save to: {output_path}
```

**Agent B — Dimensions 5-8 (Authenticity, Structure, Persuasion, Topic Framing):**

```
You are analyzing the writing style of {name} across 4 dimensions.

Read these files:
1. {corpus_path} — full corpus
2. {mode_classification_path} — use ONLY authentic_voice and thought_piece posts
3. {skill_path}/references/dimensions.md — Part 2, dimensions 5-8

For each dimension:
- Analyze with specific evidence (post numbers + verbatim quotes)
- Identify signature structural patterns and recurring techniques
- Note temporal evolution if patterns shift across years
- Catalog hook patterns with frequencies

Special attention to: {aspects the user highlighted in interview}
Context: {person's role, audience — affects persuasion and framing analysis}

Save to: {output_path}
```

### Phase 5: Synthesis

After both analysis agents complete, synthesize into the final profile. Read `references/output-template.md` for the full template.

Either do this in the main thread (if context allows) or spawn a synthesis agent that reads:
- The corpus (for Best-Of selection and Vocabulary Fingerprint)
- Both dimension analyses
- The mode classification
- `references/output-template.md` (the template to follow)
- Interview context (why the user wants this, audience gap for blending notes)

The synthesis must produce ALL sections in the template, including the full Prompt Engineering Guide with:
- Voice DNA compact prompt block
- Banned words/patterns
- Encouraged patterns
- Content type templates
- Calibration examples (3-7 gold standard posts)
- Blending notes with audience translation table

Save to: `projects/blogging/analyses/{handle}.md`

### Phase 6: Verify & Present

Before presenting to the user, verify:
- [ ] All 8 dimensions analyzed with concrete examples (post numbers + quotes)
- [ ] Mode classification covers the full corpus with distribution table
- [ ] Vocabulary Fingerprint has characteristic words, avoided words, AI-smell checklist
- [ ] Best-Of Posts has 3-7 exemplars with justification
- [ ] Prompt Engineering Guide has all 6 subsections (voice DNA, banned, encouraged, templates, calibration, blending)
- [ ] Blending notes address the audience gap identified in interview
- [ ] Temporal evolution section present (if corpus spans 2+ years)

Present to the user: a brief summary of key findings, the voice essence in 1-2 sentences, and the most surprising discovery. Point them to the full profile path.

### Phase 7: Voice Blending (optional)

When the user has 2+ completed profiles and wants to synthesize a blended voice for their own content creation. This phase reads the individual profiles' Prompt Engineering Guides + Blending Notes and produces a unified voice.

**When to trigger:** User says "blend voices", "combine profiles", "create my voice", "synthesize voice", "mix these voices", or has completed multiple profiles and wants to create content in a blended style. Also triggers when the user asks to "write a LinkedIn post" and has analyzed multiple voices but no `my-voice` skill exists yet.

#### Step 1: Interview

If not already clear from context, ask:
1. **Which profiles?** — List the available profiles in `projects/blogging/analyses/`. Confirm which ones to include.
2. **Which is the base?** — The user's own profile is the identity foundation. Other profiles are influences.
3. **Proportions?** — Suggest a starting point (e.g., 60% base, 25% strongest influence, 15% secondary). User adjusts.
4. **Target channels?** — Where will this voice be used? (LinkedIn, blog, etc.)
5. **Any techniques to emphasize or suppress?** — User may want more of Giovanni's humor but less of Robin's profanity, etc.

#### Step 2: Read source profiles

For each profile, load these sections:
- Prompt Engineering Guide (Voice DNA block, Banned, Encouraged, Templates, Calibration, Blending notes)
- Signature Moves
- Key Takeaways for Style Synthesis
- Summary (for voice essence)

The blending notes in each influence profile already contain: non-negotiable elements, blendable elements, audience translation table, and what NOT to blend. These are the primary inputs.

#### Step 3: Synthesize (1 subagent)

Spawn a synthesis agent that reads all source profiles + `references/blending-template.md` and produces:

1. **Blended voice profile** at `projects/blogging/analyses/blended-voice.md` — follows the blending template
2. **my-voice skill** at `~/.claude/skills/my-voice/SKILL.md` — auto-generated skill containing the blended voice DNA, ready to trigger on LinkedIn/blog content creation
3. **Calibration posts** at `~/.claude/skills/my-voice/references/calibration-posts.md` — 5-7 gold standard posts (full text) from across all source corpora

The blended voice must read as **one coherent person**, not a patchwork. The base voice's identity (L1 markers, core positioning, audience relationship) is non-negotiable. Influence voices contribute techniques, patterns, and range — not identity.

**Agent prompt template:**

```
You are synthesizing a blended writing voice from multiple analyzed profiles.

Read these files:
1. {profile_paths} — all source profiles (focus on: Summary, Signature Moves, Key Takeaways, Prompt Engineering Guide sections)
2. {skill_path}/references/blending-template.md — the template for the blended output
3. {corpus_paths} — source corpora (for selecting calibration posts with full text)

Interview context:
- Base voice: {base_name} at {base_pct}%
- Influences: {influence_name} at {pct}%, {influence_name} at {pct}%
- Target: {channels} for {audience}
- Emphasis: {techniques to emphasize}
- Suppress: {techniques to suppress}

Produce THREE files:

1. Blended voice profile → save to {blended_profile_path}
   Follow the blending template exactly. The Voice DNA block must be a single coherent prompt, not three blocks merged.

2. my-voice skill SKILL.md → save to {skill_path}
   Frontmatter: name "my-voice", description triggering on LinkedIn/blog content.
   Body: Voice DNA block, Blend Origins table, Banned/Encouraged patterns, Content Type Templates, Writing Workflow, Self-Test Checklist, source profile pointers.

3. Calibration posts → save to {calibration_path}
   5-7 posts from across source corpora. Include full post text. Choose posts that best represent the TARGET blended voice (not the most extreme examples of each individual voice).
```

#### Step 4: Verify & present

Verify:
- [ ] Voice DNA reads as one person, not a patchwork
- [ ] Banned patterns are the union of all profiles
- [ ] Encouraged patterns have source attribution
- [ ] Calibration posts span all source corpora
- [ ] Self-test checklist covers AI-smell detection
- [ ] my-voice skill frontmatter will trigger correctly
- [ ] Content type templates are blended, not just the base voice's templates

Present to the user: the blended Voice DNA block, the dial settings table, and the self-test checklist. Point them to both files (blended profile + skill).

## File Conventions

| File | Path |
|------|------|
| Corpus | `projects/blogging/corpus/{handle}/linkedin-posts.md` |
| Mode classification | `.work/style-research/{handle}-mode-classification.md` |
| Dims 1-4 analysis | `.work/style-research/{handle}-analysis-voice-language.md` |
| Dims 5-8 analysis | `.work/style-research/{handle}-analysis-structure-persuasion.md` |
| Final profile | `projects/blogging/analyses/{handle}.md` |
| Progress tracking | `.work/style-research/scratchpad.md` (append) |
| Blended voice profile | `projects/blogging/analyses/blended-voice.md` |
| my-voice skill | `~/.claude/skills/my-voice/SKILL.md` |
| Calibration posts | A user-maintained `calibration-posts.md` (e.g. in a local `my-voice/` skill or project notes) |
| Blending template | `references/blending-template.md` (this skill's reference) |

`{handle}` = LinkedIn username slug. Derive from the profile URL.

## Existing Profiles (for reference)

If you have prior analyses on disk (e.g. in `projects/blogging/analyses/<handle>.md`), agents can read them to calibrate output depth and format. The expected shape is one markdown file per analyzed profile, named by handle, containing the 8-dimension style profile this skill produces.

## Troubleshooting

**Voyager API returns same page repeatedly:** You're using `start` for pagination instead of `paginationToken`. See `references/voyager-api.md`.

**Timestamps 40 years in future:** You added Twitter epoch offset. LinkedIn snowflakes use Unix epoch directly. See `references/voyager-api.md`.

**JS return value blocked:** Use `console.log()` + `read_console_messages` channel. Content filter blocks combined social media text in return values.

**DOM shows only ~5 posts for external profile:** Expected — DOM virtualization. Switch to Voyager API method.

**Corpus too large for a single console.log:** Output in chunks, read all at once, parse with `scripts/parse-voyager-corpus.py`.
