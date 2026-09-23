# Issue tracker: GitHub

Issues and PRDs for this repository live in GitHub Issues. Run `gh` commands inside the
repository so the CLI infers the remote.

## Operations

- Create: `gh issue create --title "..." --body "..."`
- Read: `gh issue view <number> --comments`
- List: `gh issue list --state all --json number,title,body,labels,url`
- Comment: `gh issue comment <number> --body "..."`
- Label: `gh issue edit <number> --add-label "..."` or `--remove-label "..."`
- Close: `gh issue close <number> --comment "..."`

Pull requests are not a triage request surface unless this file says otherwise.

## Publish an issue batch

Every set of issues an engineering skill produces is one publication batch. It is
fingerprinted and resumable so that an interrupted run neither duplicates nor loses an
issue.

### Canonical batch

- Titles are the issues' identities inside the batch. Stop on a duplicate title, an
  unknown blocker or a dependency cycle.
- Order: repeatedly take, among the tickets whose blockers are all already ordered, the
  one with the smallest exact UTF-8 title bytes; number them from 1 as `order`.
- Sort and deduplicate each issue's labels by exact UTF-8 bytes and its blockers by
  their `order`. Preserve titles and bodies byte-for-byte.
- Serialize the array of issues, in `order`, as UTF-8 JSON with only `title`, `body`,
  `labels`, `blockers` and `order`: object keys sorted, Unicode characters emitted
  directly, comma and colon separators without surrounding whitespace. The lowercase
  hexadecimal SHA-256 of those bytes is `batch_sha256`.
- Append each issue's marker to its body after a blank line:
  `<!-- agent-skills-batch:{batch_sha256}:ticket:{ordinal} -->`

### Durable state

Store the approved batch at
`.scratch/agent-skills/github-issue-batches/{batch_sha256}.json` with `version`,
`batch_sha256`, `approved`, the complete canonical issue array (each issue also holding
its marker, marked body, and resolved URL or `null`), and a `relationships` array
recording each edge's blocked order, blocker order, and `pending` or `confirmed` status.

Write state atomically after every transition: sibling temporary file, flush and
`fsync`, atomic replace, `fsync` of the parent directory. A partially written file is
never valid resume state. Stop when an existing state file is malformed, or its
fingerprint or canonical batch differs from the current batch.

### First publication

1. Search every marker across all issue states with
   `gh issue list --state all --search "<marker>" --json url,body`, and count only
   bodies that contain the exact marker. Record a single match's URL in the proposed
   state. When several issues contain one marker, stop before approval and report every
   matching URL.
2. Render one numbered review with every issue's order, title, complete marked body,
   labels and blockers, then the exact remaining write plan: each missing issue
   creation followed by each pending relationship edit.
3. When the plan contains external writes, ask exactly:
   “Create these GitHub Issues now?”
   Rejection, an edit request or no answer records no approval and writes nothing. A changed title, body, label, blocker or derived order is a new fingerprint
   and starts this flow over.
4. After approval, atomically persist the exact batch with `approved: true`, then run
   the first mutating `gh` command with no remote read in between.

### Create and resume

A run on an exact, already approved batch keeps its recorded approval. Before the next
external write, search every marker again, reconcile each unique match into state and
persist it; this recovers an issue GitHub created when the command response or the
following state write was lost.

- Create only issues whose URL is still `null`, in canonical order, passing the
  approved title, marked body and labels unchanged to `gh issue create`. Persist and
  print each returned URL immediately.
- On any command failure or interruption, stop with the current durable state; the next
  run reconciles again and does not ask for approval of the same fingerprint.
- Once every issue has a URL, add the native sub-issue and blocking relationships in
  canonical edge order with an idempotent add, so replaying a pending edge yields the
  same graph. Mark an edge `confirmed` only after its command succeeds. Where native
  relationships are unavailable, make an idempotent body update with the confirmed
  `Part of` and `Blocked by` URLs.

Approval covers only the displayed missing issue creations and relationship edits for
this fingerprint. Closing, commenting on, relabeling, assigning or editing unrelated
issues needs separate authority.

<!-- github-issue-batch-fixture-protocol
version: 2
canonical_fields:
  - title
  - body
  - labels
  - blockers
  - order
marker: "<!-- agent-skills-batch:{batch_sha256}:ticket:{ordinal} -->"
approval_prompt: "Create these GitHub Issues now?"
ordering:
  algorithm: stable_topological
  ticket_tiebreak: title_utf8_bytes
  blocker_order: final_ticket_order
  unique_titles: true
state:
  directory: .scratch/agent-skills/github-issue-batches
  filename: "{batch_sha256}.json"
  atomic_write: sibling_temp_fsync_replace_directory_fsync
  durable_fields:
    - batch_sha256
    - approved
    - canonical_marked_issues
    - resolved_urls
    - relationship_statuses
external_write_boundary:
  - gh
  - issue
  - create
first_run:
  reconcile_before_preview: true
  exact_remaining_write_plan: true
  approval_immediately_before_write: true
resume:
  reuse_exact_batch_approval: true
  reconcile_before_write: true
  recover_lost_create_response: true
search:
  state: all
  before_creation: all_markers
  exact_body_marker: true
matches:
  zero: create
  one: reuse_and_report_url
  multiple: stop
creation_order: dependency
relationships:
  phase: after_all_issue_urls
  replay: idempotent_pending_edges
-->
