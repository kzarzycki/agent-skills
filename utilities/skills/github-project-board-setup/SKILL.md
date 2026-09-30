---
name: github-project-board-setup
description: "Work a GitHub Projects v2 board that is the single home for a repo's roadmap — add milestones, epics and stories to an existing board, wire dependencies, move items through the loop. Also covers first-time board setup. Use when asked to file, plan or organize work as issues/epics/milestones on a project board, move a ROADMAP.md/epics out of the filesystem onto GitHub, or bootstrap tracking for a new project around a GitHub project board."
---

## The shape

**Milestone** (M0…Mn) → **epic issue** (`type:epic`) → **story/task sub-issues**. Order is real `blocked by` issue dependencies, not prose. Anything with a status lives on the board; repo docs hold only what stays true regardless of which story is in flight.

One board field carries the position: `Status`. Its columns are the stages of the project's own engineering loop, in order, ending in `Done` — the project's docs name them (e.g. Intent→Needs owner→Ready→Build→Verify→Done). A column no ticket ever enters is a lie about the loop, so there is no second `Phase` field to keep in step. What a ticket is (epic, story, bug, enhancement) is a label; the board's built-in Labels field shows it.

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
STATUS_FID=$(fid Status)
FIRST_COLUMN=$(jq -r '.fields[]|select(.name=="Status").options[0].name' <<<"$FIELDS")

gh api repos/$OWNER/$REPO/milestones -q '.[]|[.number,.title]|@tsv'
gh issue list --label type:epic --state all --limit 50 --json number,title -q '.[]|[.number,.title]|@tsv'
```

Continue the existing id sequence (E18 after E17, E07-03 after E07-02). Never invent numbering.

```bash
move_on_board() {   # $1=issue number  $2=Status column name; adds the issue when it is not on the board yet
  local item; item=$(gh project item-add "$NUM" --owner "$OWNER" \
    --url https://github.com/$OWNER/$REPO/issues/$1 --format json | jq -r .id)
  gh project item-edit --project-id "$PID" --id "$item" --field-id "$STATUS_FID" --single-select-option-id "$(opt Status "$2")"
}
```

When setting a field through `gh api graphql` instead, pass ids with `-f`: an option id can be all digits, and `-F` then sends a number that the API refuses (`Variable $option of type String! was provided invalid value`).

`item-add` returns the existing item id when the issue is already on the board, so it is safe to call even with an auto-add workflow configured. Without that workflow it is required.

## Add a story to an epic

```bash
N=$(gh issue create --title "E07-03 · <imperative summary>" --label type:story \
      --milestone M2 --body-file /tmp/story.md | grep -o '[0-9]*$') && [ -n "$N" ] || { echo "create failed"; exit 1; }
gh api repos/$OWNER/$REPO/issues/$EPIC/sub_issues \
  -F sub_issue_id="$(gh api repos/$OWNER/$REPO/issues/$N -q .id)" -q .number
move_on_board "$N" "$FIRST_COLUMN"   # the loop's first stage
```

Sub-issue linking takes the **REST numeric id** with `-F`, not the issue number with `-f`. `gh issue create` prints the new URL on stdout and errors on stderr. Without the `[ -n "$N" ]` gate a failed create leaves `$N` empty and the next steps run against nothing. Before retrying, check whether the issue exists — `gh issue list --search` lags a few seconds behind creation, so use `gh issue list --limit 5` and read the titles.

Body follows the **Story** template in `references/templates.md` (Problem / Change / Acceptance / Proof / For the implementer). No acceptance list you can write → the story isn't ready; say so rather than filing a vague one.

## Add an epic

```bash
N=$(gh issue create --title "E18 — <scope> (M3)" --label type:epic \
      --milestone M3 --body-file /tmp/epic.md | grep -o '[0-9]*$') && [ -n "$N" ] || { echo "create failed"; exit 1; }
gh api --method POST repos/$OWNER/$REPO/issues/$N/dependencies/blocked_by -F issue_id="$(gh api repos/$OWNER/$REPO/issues/$PREREQ_EPIC -q .id)"
move_on_board "$N" "$FIRST_COLUMN"
```

Body follows the **Epic** template in `references/templates.md` (Problem / Scope / Rules for stories / Done when / Not now / For the implementer). Write stories only when the epic is picked up. An unscoped epic is legitimate — say "not scoped yet" under Scope instead of inventing filler stories.

## Add a milestone

```bash
gh api repos/$OWNER/$REPO/milestones -f title=M6 -f description="$(cat /tmp/m6.txt)" -q '[.number,.title]|@tsv'
```

Description follows the **Milestone** shape in `references/templates.md`: theme, outcome, epics, exit criteria as a checklist, why it sits here. A milestone whose exit criteria you can't state is a wish, not a milestone.

## Move an item through the loop

```bash
move_on_board "$N" Build      # the column for the loop stage the ticket just entered
```

Move the ticket at the same step that changes its state label or opens its PR, so the two can't drift. A project that ships its own move command (named in its docs) uses that instead.

Park: the project's waiting-for-a-human label + its column for that, and state on the issue which decision you're waiting for.

Close-out: closing the issue moves it to `Done` only where the board's "Item closed" workflow is on (check `workflows{nodes{name enabled}}`; it is off on a board created through the API). Where it is off, set `Done` at the step that closes the issue. Epic sub-issue progress rolls up automatically. Record the outcome on the issue (what shipped, what's still unproven), not in a doc.

## Rules

- **One home.** Never mirror a story list into markdown. Design docs describe the target; the board holds the work.
- **Dependencies are `blocked by` links**, not sentences.
- **PR bodies follow the Pull request template** in `references/templates.md` and describe the branch at merge time.
- **Batch via script** past ~3 items; re-read `field-list` after any field mutation (option ids change).
- **Don't bulk-close or re-milestone** existing items unless asked.
- Labels, field names and option names are the project's — take them from its `AGENTS.md` or discover them; the recipes here use the `type:*` labels and a `Build` column as examples.

## Verify before claiming done

```bash
gh api repos/$OWNER/$REPO/issues/$EPIC -q .sub_issues_summary        # total reflects new stories
gh project view "$NUM" --owner "$OWNER" --format json | jq '.items.totalCount'
gh api repos/$OWNER/$REPO/issues/$N/dependencies/blocked_by -q '.[]|.number'
```

Projects **workflows and a view's grouping are web-UI only** — auto-add, item closed and group-by-parent cannot be set from `gh` or the API (`createProjectV2View` makes a view, not its grouping). Report them as manual steps; never claim they're configured.
