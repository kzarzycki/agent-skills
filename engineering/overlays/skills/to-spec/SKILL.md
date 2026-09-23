---
name: to-spec
description: "Synthesize the current conversation into a spec and publish it to the project issue tracker, without interviewing the user."
disable-model-invocation: true
---

# To Spec

Turn what the conversation and the codebase already establish into a spec. Don't interview the user; the one thing you check with them is the test seams.

`docs/agents/issue-tracker.md` configures the tracker, and the repo's agent instructions map the triage labels (default names otherwise). If that file is missing, tell the user to run `/setup-engineering-workflow-for-apm`.

1. Explore the code as far as the spec needs. Use the `CONTEXT.md` vocabulary and respect the ADRs in the area.
2. Choose the test seams: existing before new, as high as possible, as few as possible (one is ideal). Confirm them with the user.
3. Write the spec in the template below and publish it to the tracker following `docs/agents/issue-tracker.md`, labelled `ready-for-agent`; it needs no further triage.

Leave out file paths and code snippets; they go stale. The exception is a prototype snippet (state machine, reducer, schema, type shape) that states a decision more precisely than prose: inline only its decision-rich part, within that decision, and say it came from a prototype.

<spec-template>

## Problem Statement

The problem, from the user's perspective.

## Solution

The solution, from the user's perspective.

## User Stories

A long, numbered list covering every aspect of the feature, each in the form:

1. As an <actor>, I want a <feature>, so that <benefit>

## Implementation Decisions

The decisions made: modules built or modified and their changed interfaces, architectural decisions, schema changes, API contracts, specific interactions, technical clarifications from the developer.

## Testing Decisions

What makes a good test here (external behaviour, not implementation details), which modules get tested, and prior art for those tests in the codebase.

## Out of Scope

What this spec does not cover.

## Further Notes

Anything else about the feature.

</spec-template>
