---
name: spec
description: Use when a vague work item needs product/user clarification before planning or implementation.
---

# Spec

Turn a vague work item into a Decision Spec. Reuse existing project docs and code facts; ask the user only for product choices tools cannot answer.

This file is the phase contract — the rules the artifact must satisfy. Execution mechanics (how an executor runs and returns) live with the executor and the workflow engine, not here.

## Execution

An executor owns the phase: interview the user, write `01-DECISION-SPEC.mdx`, then run the `spec-phase` workflow — the convergence loop of author rework, format gate, both reviewers in parallel, and capped rework cycles, until it returns `pass`, `needs-user`, or the rework cap. `needs-user` and the cap go back to the user over the interview channel. The user gate is the artifact path plus verdicts plus the rendered MDX page; the artifact content stays out of the orchestrator's context. Whether the engine delegates the interview or runs it in-situ is the engine's call, not this contract's.

## Contract

- **Research first.** Propose research buckets, let the user approve/narrow/reject, run only the approved ones.
- **Interview with both skills loaded.** `superpowers:brainstorming` (domain coverage — purpose, approaches, architecture/components/data flow/error handling/testing) and `mattpocock-skills:grill-me` (adversarial depth, one adaptive question at a time), via preload or explicit Skill calls. If one cannot load, record that; reviewers escalate it as `needs-user`, not `needs-rework`.
- **Pace the questions.** Batch questions resolving one decision branch into a single AskUserQuestion (max 4); never batch across a dependency — grill-me's adaptivity applies between branches.
- **`_phases/spec/interview-notes.md` is the record** the author and reviewers work from: which skills loaded and what each contributed (the review gate checks this), plus the decisions, answers, and rejected alternatives. The original question/problem and rejected alternatives survive every rework.
- **Architecture answers are Tech Design inputs**, recorded here, not decided in Spec.
- **Testable rationale.** A decision justified by a capability needs an acceptance criterion that exercises that capability — the reason gets verified, not just the happy path.
- **Layout.** `01-DECISION-SPEC.mdx` is the only root artifact; notes, research, and review evidence go under underscore dirs.

## Spec shape and language

- **Rich MDX**, authored with `communicating-in-mdx` loaded — reach for a component where it lands harder than prose, not for decoration. Contract-clean Markdown underneath: H1 title on line 1, H2 sections, no extra H2s, no frontmatter. Section names and order are normative in `../../contracts/decision-spec.json`.
- **Structure over prose.** Tables for enumerable facts (alternative | why rejected; risk | routed-to), lists for parallel items, a ` ```mermaid ` fence for architecture/data-flow/sequence inside Current context or Desired behavior, a `<Callout>` for load-bearing intent. Prose only where narrative explains. A few sentences for simple sections, ~300 words for nuanced ones.
- **Clean-slate, not a log.** Write as a first draft by someone who knew the answer from the first prompt, not a record of how the discussion reached it. Per paragraph: would this exist in a one-shot draft? Cut what survives only because the conversation debated, corrected, or circled. Scrub the tells: *replacing* or *superseding* a "current state" on a from-scratch design; a dropped option used as a running comparison baseline (it lives only in **Rejected alternatives**); history words (*settled*, *the old*, *obsolete*, *this pass*, *no longer*, *verified-not-speculation*); *the user wanted / rejected X* — state the reason, not who decided.
- **Each fact once; the Approval record is a pointer.** No fact recurs across **Key decisions and rationale**, **Rejected alternatives**, and **Approval record**. The Approval record is the checkbox plus a one-line pointer to the decision trail (`_phases/`) — never a recap of the spec, the most common log-residue failure. History and the cross-round `<DocDiff>` live on the gate page, not the body.

## Format gate

Before the review gate: `mdsmith check -c <plugin>/contracts/mdsmith.yml <work-item>/01-DECISION-SPEC.mdx`, where `<plugin>` is the installed plugin root (the dir containing `contracts/`) and `<work-item>` is `.workflow/<id>/`. mdsmith reads MDX directly — JSX components and ` ```mermaid ` fences pass through. It enforces document shape (H1 on line 1, H2 sections in contract order, no frontmatter, no extra H2s): MDS020 is a contract violation, fix first; MDS023/MDS036/MDS056 are language budget, rework input; MDS025 (table alignment) is advisory and auto-fixable with `mdsmith fix`. The author runs the gate after each writing round and fixes structure before returning. Without mdsmith installed, verify sections manually against the contract JSON.

## Review gate

Run fixed reviewers. Their checklists are normative in this plugin's `agents/<reviewer>.md`; this table is only a map.

| Reviewer | Focus |
|---|---|
| Intent Reviewer (`agents/intent-reviewer.md`) | Intent and scope fidelity; interview composition record |
| Testability Reviewer (`agents/testability-reviewer.md`) | Observable acceptance criteria; format gate |

The verdict enum, aggregation rule, and rework cap are machine truth in `contracts/work-item.json`, applied by `phase-loop.js`. The distinction reviewers judge: `needs-user` is a product question only the user can answer or a contradiction with stated intent; `needs-rework` is a fixable defect.
