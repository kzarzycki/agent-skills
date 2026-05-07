# Prompt Improvement Guide for Gemini Deep Research

When the calling agent provides a research prompt, evaluate it against these dimensions
before submitting to Gemini. If improvements would meaningfully help, suggest them to the
calling agent — but never modify the prompt autonomously.

## Evaluation Dimensions

### 1. Scope Clarity
- Is the research question specific enough to produce actionable results?
- Vague: "Tell me about AI" → Better: "Compare transformer architectures for real-time inference on edge devices"
- If too broad, suggest narrowing to 2-3 specific sub-questions

### 2. Temporal Framing
- Does it specify how recent the information needs to be?
- If the topic evolves fast (tech, policy, markets), suggest adding: "Focus on developments from the last 6 months" or similar
- If historical analysis is fine, no change needed

### 3. Angle Specification
- Are the desired dimensions/perspectives clear?
- Good: "Compare X from technical feasibility, cost, and organizational readiness angles"
- If missing, suggest 2-3 angles that would make the research more structured

### 4. Output Expectations
- What depth and format does the calling agent expect?
- Suggest specifying: executive summary vs detailed technical report, inclusion of comparisons/tables, code examples if relevant

### 5. Audience Context
- Who will read this? Technical team? Executives? Mixed audience?
- If unclear, suggest adding audience context so Gemini calibrates depth appropriately

## When to Suggest vs When to Accept As-Is

**Suggest improvements when:**
- The prompt is fewer than 20 words (likely too vague)
- No temporal context for a fast-moving topic
- Multiple interpretations are possible
- The prompt would benefit from structured angles

**Accept as-is when:**
- The prompt is already specific and well-structured
- The calling agent has clearly thought through what they want
- Minor tweaks wouldn't meaningfully improve the research output

## Communication Format

When suggesting improvements, send to calling agent:
```
PROMPT_SUGGESTION: I'd suggest these improvements to get better results from Gemini Deep Research:
1. [specific suggestion with example]
2. [specific suggestion with example]

Original: "<original prompt>"
Suggested: "<improved prompt>"

Should I use the original or the suggested version?
```
