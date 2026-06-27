---
name: tech-design
description: Use when an approved spec needs a technical design -- architecture and technology choices grounded in compared options -- before planning.
---

# Tech Design

Design how to satisfy the approved Decision Spec: compare candidate approaches, choose one, and record the resulting design — architecture, components, and the technical decisions that bind it. Options research is the evidence; the chosen design is the product. Start from approved needs, not a favored tool.

This file is the phase contract — the rules the artifact must satisfy. Execution mechanics (how an executor runs and returns) live with the executor and the workflow engine, not here.

## Execution

Delegated by default: the engine stays orchestrator and runs the `tech-design-phase` workflow — the autonomous loop of the designer authoring `02-TECH-DESIGN.mdx`, the format gate, both reviewers judging independently in parallel, and capped rework — until it returns `pass`, `needs-user`, or the rework cap. The engine never authors or reviews in its own context; it only presents the result at the user gate. Under the same contract, fallbacks spawn the designer as a teammate or run in-situ.

## Contract

- **Input:** the approved `01-DECISION-SPEC.mdx`, plus any architecture answers the Spec interview recorded as design inputs.
- **Output:** one evolving root human artifact, `02-TECH-DESIGN.mdx`.
- **Research multiple option families:** first-party implementation, capabilities of the existing runtime/platform, reusable in-repo skills/agents/components, and third-party packages.
- **Third-party dependencies are references only** until safety audit, compatibility check, wrapper design, and user approval.
- **The chosen design follows from the scorecard:** pick the winning option and commit it to a concrete shape — architecture sketch, component responsibilities, data flow. H3 subsections inside Chosen design are free-form.
- **Key technical decisions records every binding choice** beyond the headline option (libraries, protocols, storage, naming) as decision | choice | rationale rows; a decision without a stated alternative is a smell.
- **Artifact UX assessment:** how the design affects the user-facing artifact experience, under the work-item layout rule (root numbered human artifacts, underscore internals, no routine history).
- **Findings that change the product need** trigger a focused Spec addendum, never a silent edit to the spec.

## Artifact shape and language

- **Rich MDX**, authored with `communicating-in-mdx` loaded — reach for a component where it lands harder than prose, not for decoration. Contract-clean Markdown underneath: H1 title on line 1, H2 sections, no extra H2s, no frontmatter. Section names and order are normative in `../../contracts/tech-design.json`.
- **Structure over prose.** Scorecard and Key technical decisions are always tables; other enumerable facts go in tables (option | tradeoff; need | coverage), parallel items in lists with bold lead-ins. Render architecture/data flow as a ` ```mermaid ` fence or `<Mermaid>` inside Chosen design; a `<Callout>` carries a load-bearing decision or a design-blocking risk. Prose only where narrative explains. A few sentences for simple sections, ~300 words for nuanced ones.
- **Clean-slate, not a log.** Write as a first draft by someone who knew the answer from the first prompt, not a record of how the discussion reached it. Per paragraph: would this exist in a one-shot draft? Cut what survives only because the conversation debated, corrected, or circled. Scrub the tells: *replacing* or *superseding* a "current state" on a from-scratch design; a dropped option used as a running comparison baseline (it lives only in **Rejected alternatives**); history words (*settled*, *the old*, *obsolete*, *this pass*, *no longer*, *verified-not-speculation*); *the user wanted / rejected X* — state the reason, not who decided.
- **Each fact once; the Approval record is a pointer.** No fact recurs across **Scorecard**, **Key technical decisions**, **Rejected alternatives**, and **Approval record**. The Approval record is the checkbox plus a one-line pointer to the decision trail (`_phases/`) and any evidence — never a recap of the design, the most common log-residue failure. History and the cross-round `<DocDiff>` live on the gate page, not the body.

## Format gate

Before the review gate: `mdsmith check -c <plugin>/contracts/mdsmith.yml <work-item>/02-TECH-DESIGN.mdx`, where `<plugin>` is the installed plugin root (the dir containing `contracts/`) and `<work-item>` is `.workflow/<id>/`. mdsmith reads MDX directly — JSX components and ` ```mermaid ` fences pass through. It enforces document shape (H1 on line 1, H2 sections in contract order, no frontmatter, no extra H2s): MDS020 is a contract violation, fix first; MDS023/MDS036/MDS056 are language budget, rework input; MDS025 (table alignment) is advisory and auto-fixable with `mdsmith fix`. The author runs the gate after each writing round and fixes structure before returning. Without mdsmith installed, verify sections manually against the contract JSON.

## Scorecard

Derive the needs from the approved Decision Spec — its Constraints and Acceptance criteria sections, plus any need the spec's Goal makes explicit. One row per need, one column per option, each cell a short verifiable judgment. Do not reuse another work item's needs list; if the spec yields fewer than three needs, that is a Spec gap — raise it instead of padding.

## Review gate

Run fixed reviewers. Their checklists are normative in this plugin's `agents/<reviewer>.md`; this table is only a map.

| Reviewer | Focus |
|---|---|
| Reuse/Coverage Reviewer (`agents/reuse-coverage-reviewer.md`) | Candidate breadth, source coverage, needs mapping |
| Fit/Risk Reviewer (`agents/fit-risk-reviewer.md`) | Design follows from evidence; capability fit, lock-in, safety/audit risk, reversibility |

The verdict enum, aggregation rule, and rework cap are machine truth in `contracts/work-item.json`, applied by `phase-loop.js`. The distinction reviewers judge: `needs-user` is a product question only the user can answer or a contradiction with stated intent; `needs-rework` is a fixable defect.
