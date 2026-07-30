# Issue tracker: GitHub

Issues and PRDs for this repository live in GitHub Issues. Run `gh` commands
inside the repository so the CLI infers the remote.

## Operations

- Create: `gh issue create --title "..." --body "..."`
- Read: `gh issue view <number> --comments`
- List: `gh issue list --state all --json number,title,body,labels,url`
- Comment: `gh issue comment <number> --body "..."`
- Label: `gh issue edit <number> --add-label "..."` or `--remove-label "..."`
- Close: `gh issue close <number> --comment "..."`

## Publish an issue batch

Treat every set of issues produced by an engineering skill as one publication
batch. The batch contains every issue in dependency order. Keep the approved
batch unchanged through creation and resume; a change to any title, body, label,
blocker, or position starts a new review and approval.

Before any mutating `gh` command:

1. Render one numbered review batch. Show the title, complete body, labels,
   blockers, and order for every issue.
2. Canonicalize the batch as UTF-8 JSON: use the fields `title`, `body`,
   `labels`, `blockers`, and `order`; sort object keys and each issue's labels;
   preserve issue order and blocker order; omit insignificant whitespace.
3. Compute the lowercase hexadecimal SHA-256 of those canonical bytes as
   `batch_sha256`.
4. Append this marker to each reviewed body, replacing the placeholders with
   the batch hash and the issue's one-based position:

   ```markdown
   <!-- agent-skills-batch:{batch_sha256}:ticket:{ordinal} -->
   ```

5. Show the complete marked batch, then ask exactly: “Create these GitHub
   Issues now?”

Rejection, an edit request, or the absence of explicit approval ends the flow
with zero external mutations. Approval applies only to the displayed batch.
The first `gh issue create` is the external-write boundary.

After approval, resume or create the approved batch:

1. Search every marker across all issue states before creating anything. Use
   `gh issue list --state all --search "<marker>" --json url,body` and confirm
   the exact marker in the returned body.
2. Record and immediately print the existing issue URL when exactly one issue
   contains a marker.
3. Stop the whole batch when multiple issues contain the same marker. Report
   the matching URLs and create nothing.
4. Create only markers with no match, in the approved dependency order. Pass
   the reviewed title, marked body, and labels unchanged to `gh issue create`.
5. Record and immediately print each URL returned by `gh issue create`. Stop on
   failure. A retry repeats the all-state marker search and therefore reuses
   every confirmed issue.
6. Add native sub-issue and blocking relationships in a second pass, after
   every issue in the batch has a confirmed URL. When native relationships are
   unavailable, put the confirmed `Part of` and `Blocked by` URLs in the issue
   bodies during this second pass.

Do not reuse approval for another batch or for a changed batch. Publication
authority covers only creation and relationship wiring for the approved
issues; closing, commenting on, relabeling, assigning, or editing unrelated
issues requires its own authority.

Pull requests are not a triage request surface unless this file says otherwise.

<!-- github-issue-batch-fixture-protocol
version: 1
canonical_fields:
  - title
  - body
  - labels
  - blockers
  - order
marker: "<!-- agent-skills-batch:{batch_sha256}:ticket:{ordinal} -->"
approval_prompt: "Create these GitHub Issues now?"
external_write_boundary:
  - gh
  - issue
  - create
search:
  state: all
  before_creation: all_markers
  exact_body_marker: true
matches:
  zero: create
  one: reuse_and_report_url
  multiple: stop
creation_order: dependency
relationships: after_all_issue_urls
-->
