---
name: github-project-board-setup
description: "Work a GitHub Projects v2 board that is the single home for a repo's roadmap — add milestones, epics and stories to an existing board, wire dependencies, move items through the loop. Also covers first-time board setup. Use when asked to file, plan or organize work as issues/epics/milestones on a project board, move a ROADMAP.md/epics out of the filesystem onto GitHub, or bootstrap tracking for a new project around a GitHub project board."
---

## The shape

**Milestone** (M0…Mn) → **epic issue** (`type:epic`) → **story/task sub-issues**. Order is real `blocked by` issue dependencies, not prose. Anything with a status lives on the board; repo docs hold only what stays true regardless of which story is in flight.

Board fields: `Status` (Backlog→Todo→In progress→In review→Done, human column) and `Phase` (TRIAGED→SPEC→SPEC_APPROVED→PLAN→PLAN_APPROVED→IMPLEMENTED→BRANCH_APPROVED→GATES_GREEN→MERGED / PARKED, loop position) are different axes — update both or the board lies. `Kind` = Epic/Story/Task/Bug. `Session` = owning agent session.

**No board yet?** → `references/new-board-setup.md`. Everything below assumes one exists.

## Discover first

Ids and single-select option ids differ per project and change whenever a field is edited. Derive them; never hardcode from memory. A repo may pin its own values in `AGENTS.md` — use those and skip discovery.

```bash
read -r OWNER REPO < <(gh repo view --json owner,name -q '[.owner.login,.name]|@tsv')
NUM=$(gh repo view --json projectsV2 -q '.projectsV2.Nodes[0].number')   # note: .Nodes, capital N
PID=$(gh project view "$NUM" --owner "$OWNER" --format json | jq -r .id)

FIELDS=$(gh project field-list "$NUM" --owner "$OWNER" --format json)
fid() { jq -r --arg n "$1" '.fields[]|select(.name==$n).id' <<<"$FIELDS"; }
opt() { jq -r --arg n "$1" --arg o "$2" '.fields[]|select(.name==$n).options[]|select(.name==$o).id' <<<"$FIELDS"; }
KIND_FID=$(fid Kind) STATUS_FID=$(fid Status) PHASE_FID=$(fid Phase) SESSION_FID=$(fid Session)

gh api repos/$OWNER/$REPO/milestones -q '.[]|[.number,.title]|@tsv'
gh issue list --label type:epic --state all --limit 50 --json number,title -q '.[]|[.number,.title]|@tsv'
```

Continue the existing id sequence (E18 after E17, E07-03 after E07-02). Never invent numbering.

```bash
add_to_board() {   # $1=issue number  $2=Kind option name  $3=Status option name
  local item; item=$(gh project item-add "$NUM" --owner "$OWNER" \
    --url https://github.com/$OWNER/$REPO/issues/$1 --format json | jq -r .id)
  gh project item-edit --project-id "$PID" --id "$item" --field-id "$KIND_FID"   --single-select-option-id "$(opt Kind   "$2")"
  gh project item-edit --project-id "$PID" --id "$item" --field-id "$STATUS_FID" --single-select-option-id "$(opt Status "$3")"
}
```

`item-add` returns the existing item id when the issue is already on the board, so it is safe to call even with an auto-add workflow configured. Without that workflow it is required.

## Add a story to an epic

```bash
N=$(gh issue create --title "E07-03 · <imperative summary>" --label type:story \
      --milestone M2 --body-file /tmp/story.md 2>&1 | grep -o '[0-9]*$') && [ -n "$N" ] || { echo "create failed"; exit 1; }
gh api repos/$OWNER/$REPO/issues/$EPIC/sub_issues \
  -F sub_issue_id="$(gh api repos/$OWNER/$REPO/issues/$N -q .id)" -q .number
add_to_board "$N" Story Backlog
```

Sub-issue linking takes the **REST numeric id** with `-F`, not the issue number with `-f`. `gh issue create` prints the URL on stderr, hence the `2>&1`; without the `[ -n "$N" ]` gate a failed create leaves `$N` empty and the next steps run against nothing — and a retry files a duplicate, so search by title before retrying.

Body follows the **Story** template in `references/templates.md` (Problem / Change / Acceptance / Proof / For the implementer). No acceptance list you can write → the story isn't ready; say so rather than filing a vague one.

## Add an epic

```bash
N=$(gh issue create --title "E18 — <scope> (M3)" --label type:epic \
      --milestone M3 --body-file /tmp/epic.md 2>&1 | grep -o '[0-9]*$') && [ -n "$N" ] || { echo "create failed"; exit 1; }
gh issue edit "$N" --add-blocked-by "$PREREQ_EPIC"
add_to_board "$N" Epic Backlog
```

Body follows the **Epic** template in `references/templates.md` (Problem / Scope / Rules for stories / Done when / Not now / For the implementer). Write stories only when the epic is picked up. An unscoped epic is legitimate — say "not scoped yet" under Scope instead of inventing filler stories.

## Add a milestone

```bash
gh api repos/$OWNER/$REPO/milestones -f title=M6 -f description="$(cat /tmp/m6.txt)" -q '[.number,.title]|@tsv'
```

Description follows the **Milestone** shape in `references/templates.md`: theme, outcome, epics, exit criteria as a checklist, why it sits here. A milestone whose exit criteria you can't state is a wish, not a milestone.

## Move an item through the loop

```bash
ITEM=$(gh project item-add "$NUM" --owner "$OWNER" \
  --url https://github.com/$OWNER/$REPO/issues/$N --format json | jq -r .id)
gh project item-edit --project-id "$PID" --id "$ITEM" --field-id "$PHASE_FID"   --single-select-option-id "$(opt Phase SPEC)"
gh project item-edit --project-id "$PID" --id "$ITEM" --field-id "$SESSION_FID" --text "sess-2026-09-14-a"
```

Park: `loop:needs-human` label + Status `Backlog` + Phase `PARKED`, and state on the issue which decision you're waiting for.

Close-out: closing the issue moves it to Done via the built-in workflow — don't hand-set Status. Epic sub-issue progress rolls up automatically. Record the outcome on the issue (what shipped, what's still unproven), not in a doc.

## Rules

- **One home.** Never mirror a story list into markdown. Design docs describe the target; the board holds the work.
- **Dependencies are `blocked by` links**, not sentences.
- **PR bodies follow the Pull request template** in `references/templates.md` and describe the branch at merge time.
- **Batch via script** past ~3 items; re-read `field-list` after any field mutation (option ids change).
- **Don't bulk-close or re-milestone** existing items unless asked.
- Labels, field names and option names are the project's — take them from its `AGENTS.md` or discover them; the recipes here use the `type:*` / `loop:needs-human` vocabulary as an example.

## Verify before claiming done

```bash
gh api repos/$OWNER/$REPO/issues/$EPIC -q .sub_issues_summary        # total reflects new stories
gh project view "$NUM" --owner "$OWNER" --format json | jq '.items.totalCount'
gh api repos/$OWNER/$REPO/issues/$N/dependencies/blocked_by -q '.[]|.number'
```

Projects **workflows and views are web-UI only** — auto-add, group-by-parent, roadmap view cannot be set from `gh`. Report them as manual steps; never claim they're configured.
