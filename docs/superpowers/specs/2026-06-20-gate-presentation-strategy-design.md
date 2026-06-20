# Gate Presentation Strategy Design

## Goal

Decide how workflow gate artifacts (Decision Spec, Tech Design, …) get turned into the live HTML decision pages the user reviews — specifically, where the model judgment "how should this content be displayed" runs, and at what cost per render and per rework round.

## Current context

- Every phase gate serves the user a live decision page: `communicating-in-html/assets/render-decision-page.py` renders a markdown artifact deterministically; `gate-server.py` carries answers back (approve / rework / annotations) without copy-paste. Shipped, verified.
- The baseline renderer treats the artifact as generic markdown: H2 sections become annotatable prose blocks. It is correct and live for any artifact but presents a scorecard as a plain table, not as weight sliders with needs-as-rows.
- A throwaway experiment (`gate-x.html`) showed the consumability ceiling: clickable architecture diagram, scorecard with live weight sliders and winner-flip detection, selectable option cards. Every one of those widgets was derived from the *kind* of section (scorecard, options, risks), not from the specific artifact.
- Artifacts are schematized: each phase's sections are fixed by `contracts/*.json` before any artifact exists. Markdown is the single source of truth — `mdsmith`, the reviewers, the contract sections, the Approval record, and git diffs all gate on it.
- A prior speed pass deleted the per-render LLM page agent precisely because it cost tokens on every round and forced verification of novel output each time.

## Decision

Presentation is **progressive enhancement keyed by the contract**. The model judgment about display runs **once per artifact kind at contract-design time**, not once per render. Four layers, cheapest first:

1. **Deterministic baseline** — `render-decision-page.py` turns any markdown artifact into a correct, live, annotatable page. Zero tokens; verified once per template change. This is the *guaranteed* layer: it secures availability and correctness, not peak consumability. It plays the same role the format gate does — a floor, not a ceiling.
2. **Contract display hints** — a section in the contract JSON binds known sections to deterministic widgets (`score-matrix`, `option-cards`, `risk-list`). The renderer grows a small widget library that maps parsed section content to widgets; unhinted sections fall back to layer 1. This is where the consumability ceiling lives: designed once, reviewed once, benchmarkable by the eval harness as a pipeline variant.
3. **Author-emits-data** — escape hatch for sections too free-form to parse reliably (e.g. Tech Design's free-form H3s under "Chosen design"). The phase author — an LLM already running in the loop — additionally returns the section as machine data; the renderer binds data → widget deterministically. Model thinking rides an agent that already runs, so it is near-free; the cost is a second representation of the same facts that must stay synced with the markdown.
4. **Author-emits-fragment** — opt-in only, for contract-less one-offs. The author returns an HTML *body fragment*; the harness wraps it with the owned chrome (decision bar, live channel, annotations, CSS). Recovers bespoke presentation while keeping the protocol, fallback, and channel wiring out of the model's hands.

### Rejected alternative: author emits full HTML from the start

The author sees *this* artifact, not just its kind, so it can make bespoke calls a contract hint never could ("this scorecard's winner flips at weight 2 — call it out"; "these four options reduce to one axis — draw it"). No widget library to maintain. Rejected because the costs are structural, not incidental:

- **Splits the source of truth.** Everything downstream gates on markdown. HTML-as-artifact makes the reviewers and format gate read presentation noise and makes diffs unusable; HTML-alongside-markdown is two representations of the same facts — the one-owner-per-fact rule the architecture forbids.
- **Marginal cost on every round.** A gate-x-grade page is ~25–40k output tokens, paid again on *every* rework round, in the author's context. This re-adds the per-render page agent the speed pass removed.
- **Per-round verification gate.** Novel JS each time means a jsdom smoke run on every round, with failures looping back through the expensive author. A deterministic template is verified once per template change — that is what "guaranteed baseline" buys.
- **Eval irreproducibility.** Bespoke pages vary run-to-run, so golden traces and cross-variant diffs get noisy, and a broken page blocks the gate.

The eval harness can later measure whether the bespoke ceiling earns its cost. Until that evidence exists, the baseline holds the line.

## Architecture and data flow

- **Ownership.** Display hints live in the contract layer (`contracts/*.json`) — the existing machine-truth owner of sections and format. The renderer (`communicating-in-html/assets/`) owns the widget library and the chrome. No new layer; the hint is an attribute on sections the contract already defines.
- **Render path.** Phase workflow returns artifact path + verdicts → engine calls `render-decision-page.py` with the contract → renderer parses markdown sections, applies hinted widgets (layer 2) or data-bound widgets (layer 3) or prose fallback (layer 1) → one self-contained live HTML file → served via `gate-server.py`.
- **Verification.** Each widget gets a jsdom smoke test once, when the widget or template changes — not per artifact. Layers 1–2 never need per-render verification because output is deterministic for a given template; only layer 4 (novel fragment) does.

## Status

Layers 1–2 built and verified. The baseline renderer ships; four layer-2 widgets are wired via `tech-design.json`'s `display` map and verified on the real `02-TECH-DESIGN.md` (jsdom-smoked, no load errors, plus a live round-trip): `score-matrix` (Scorecard → sticky sentiment matrix, 13×4), `option-cards` (Options → selectable cards feeding `chosenOption`), `decision-table` (Key technical decisions → label→choice rows, rationale folded), `risk-list` (Risks → risk headlines, mitigation folded). Each derives only from the markdown; a section with no hint or no matching table/H3 falls back to prose. Layers 3–4 stay unbuilt escape hatches — add only when a section's content defeats parsing (author-emits-data) or an artifact has no contract (author-emits-fragment); the weighted-slider scorecard with winner-flip is the canonical layer-3 case, since real weights and per-need scores are data the markdown does not carry.
