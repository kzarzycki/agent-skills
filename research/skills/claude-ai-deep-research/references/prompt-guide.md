# Claude.ai Research — Prompt Improvement Guide

When the calling agent provides a research prompt, evaluate it against these criteria
before suggesting improvements. Only suggest changes that would meaningfully improve
the research quality — don't suggest changes for the sake of it.

## Evaluation Criteria

### 1. Scope Clarity
- Is the research question specific enough for a focused investigation?
- Would narrowing or broadening the scope improve the output?
- Bad: "Tell me about AI" → Too broad
- Good: "How are Fortune 500 companies implementing agentic AI in their software development workflows as of 2026?"

### 2. Temporal Framing
- Does the prompt specify recency requirements?
- For fast-moving fields (AI, tech), explicit date ranges matter
- Suggest adding "as of 2026" or "in the last 6 months" if missing and relevant

### 3. Angle Specification
- Are the desired research dimensions clear?
- Examples of angles: technical, business, competitive, regulatory, adoption trends
- If the caller hasn't specified angles, suggest 2-3 that seem relevant

### 4. Output Expectations
- Does the prompt indicate desired depth or format?
- Helpful additions: "provide examples", "include case studies", "compare approaches",
  "cite sources", "structure as executive summary + detailed sections"

### 5. Exclusions
- Would specifying what NOT to include help focus the research?
- Example: "Focus on practical implementation, not theoretical frameworks"

## When NOT to Suggest Changes

- The prompt is already well-structured and specific
- The caller has explicitly said they want it submitted as-is
- Minor stylistic preferences that won't affect research quality
- The prompt is intentionally broad (the caller may want a survey)

## Format for Suggestions

Always present suggestions as optional improvements, never as requirements.
The calling agent decides — you never modify the prompt autonomously.
