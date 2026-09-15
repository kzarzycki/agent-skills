# First-time board setup

Read only when the repo has no board yet. Day-2 work (adding milestones, epics, stories) is in `SKILL.md` and does not need this file.

## Hard constraints (learned the hard way)

- **Repo-owned projects do not exist.** ProjectsV2 owners are users or orgs only. A repo gets a *linked* project. Org ownership requires transferring the repo — reversible, but it changes URLs and any install paths embedding `owner/repo`. Ask before doing that.
- **Issue types (Epic/Story/Task/Bug) are org-only.** On personal repos use `type:*` labels + a `Kind` single-select field. Same board grouping; you lose the `type:` search qualifier and the badge on the issue list.
- **`gh project link` exits 0 without linking when `has_projects` is false.** Always enable first, always verify after.
- `gh repo view --json projectsV2` returns an **object wrapping a `Nodes` array** — `-q '.projectsV2.Nodes[]|…'` (capital N). A bare `.projectsV2[]` errors with `expected an array but got: object`, which looks exactly like a failed link.

## Procedure

### 1. Create and link

```bash
gh api -X PATCH repos/OWNER/REPO -F has_projects=true -q '.has_projects'   # must print true
NUM=$(gh project create --owner OWNER --title REPO --format json | jq -r .number)
gh project link "$NUM" --owner OWNER --repo OWNER/REPO
gh repo view OWNER/REPO --json projectsV2 -q '.projectsV2.Nodes[]|[.number,.title]|@tsv'   # must list it
gh project edit "$NUM" --owner OWNER --visibility PUBLIC \
  --description "Engineering board: milestones, epics and stories for REPO" \
  --readme "$(cat board-readme.md)"     # --readme takes a string; there is no --readme-file
```

### 2. Fields

`Status` already exists with `Todo|In Progress|Done`. Replace the option set — `updateProjectV2Field` **replaces**, so list every option you want:

```bash
FID=$(gh project field-list "$NUM" --owner OWNER --format json | jq -r '.fields[]|select(.name=="Status").id')
cat > /tmp/q.graphql <<EOF
mutation{updateProjectV2Field(input:{fieldId:"$FID",singleSelectOptions:[
 {name:"Backlog",color:GRAY,description:""},{name:"Todo",color:BLUE,description:""},
 {name:"In progress",color:YELLOW,description:""},{name:"In review",color:ORANGE,description:""},
 {name:"Done",color:GREEN,description:""}]}){projectV2Field{... on ProjectV2SingleSelectField{options{id name}}}}}
EOF
gh api graphql -F query=@/tmp/q.graphql
```

Then the loop fields:

```bash
gh project field-create "$NUM" --owner OWNER --name Phase --data-type SINGLE_SELECT \
  --single-select-options "TRIAGED,SPEC,SPEC_APPROVED,PLAN,PLAN_APPROVED,IMPLEMENTED,BRANCH_APPROVED,GATES_GREEN,MERGED,PARKED"
gh project field-create "$NUM" --owner OWNER --name Kind --data-type SINGLE_SELECT --single-select-options "Epic,Story,Task,Bug"
gh project field-create "$NUM" --owner OWNER --name Session --data-type TEXT
```

`Status` and `Phase` are different axes: Status is where the item sits for a human reader, Phase is where it sits inside the engineering loop. A loop driver maps phase→status (e.g. PARKED→Backlog, BRANCH_APPROVED/GATES_GREEN→In review), so keep `Backlog` and `In review` or the mapping lands on nothing.

### 3. Labels

```bash
for l in "type:epic|8250DF|Epic: milestone-sized umbrella; stories are its sub-issues" \
         "type:story|1D76DB|Story: one engineering-loop iteration" \
         "type:task|0E8A16|Task: small, well-specified work item" \
         "type:bug|D73A4A|Bug: something is broken" \
         "loop:needs-human|FBCA04|loop parked: needs a human decision" \
         "ready-for-agent|0E8A16|spec published; ready for an implementation session"; do
  IFS='|' read -r n c d <<<"$l"; gh label create "$n" --color "$c" --description "$d" --force
done
```

### 4. Milestones carry the decisions

A roadmap file holds more than tables: exit criteria, sequencing rationale, the through-line. That prose has no home on a board unless you give it one, and deleting the file silently drops it.

- per-milestone **exit criteria + why this milestone sits here** → milestone `description`
- **through-line + board conventions** → project README
- **release scope** → the current epic's body

```bash
gh api repos/OWNER/REPO/milestones -f title=M0 -f description="$(cat m0.txt)" -q '[.number,.title]|@tsv'
gh api -X PATCH repos/OWNER/REPO/milestones/1 -F description=@m0.txt -q .title
```

### 5. Epics, stories, hierarchy

Script it over the roadmap table; never hand-type N `gh issue create` calls. Create epics first, collect the number map, then create stories referencing parents.

```bash
gh issue create --title "E00 — Bridge foundation (M0)" --label type:epic --milestone M0 --body-file epic.md
```

Sub-issues take the **REST numeric id**, not the issue number, and `-F` (not `-f`) or the API rejects it as a string:

```bash
SUB_ID=$(gh api repos/OWNER/REPO/issues/126 -q .id)
gh api repos/OWNER/REPO/issues/125/sub_issues -F sub_issue_id="$SUB_ID" -q .number
gh api repos/OWNER/REPO/issues/125 -q .sub_issues_summary     # {"completed":0,"total":9}
```

Dependencies from the roadmap's deps column:

```bash
gh issue edit 135 --add-blocked-by 125
gh api repos/OWNER/REPO/issues/135/dependencies/blocked_by -q '.[]|.number'
```

### 6. Board items and fields

```bash
ITEM=$(gh project item-add "$NUM" --owner OWNER --url https://github.com/OWNER/REPO/issues/125 --format json | jq -r .id)
PID=$(gh project view "$NUM" --owner OWNER --format json | jq -r .id)
gh project item-edit --project-id "$PID" --id "$ITEM" --field-id "$KIND_FIELD_ID" --single-select-option-id "$EPIC_OPTION_ID"
```

Re-read `field-list` after any field mutation; option ids change.

### 7. Web-UI-only steps — report these, don't pretend they're done

`gh` cannot configure Projects workflows or views:

1. **Workflows → Auto-add to project**, filter `is:issue is:open`. Without it only explicitly-added items appear.
2. **Group table view by Parent issue** → hierarchy view with sub-issue progress bars.
3. Optional **Roadmap view** with a date field.

closed→Done is enabled by default.

## Repo-side cleanup

Delete `ROADMAP.md` and `epics/` **after** verifying the content landed (milestone descriptions non-empty, epic bodies carry scope). Then repoint every cross-reference — grep for `ROADMAP|epics/` across `docs/`, root `README.md`, `CONTRIBUTING.md` and any skill files. Leave a "Where the work lives" table in `docs/README.md` mapping board / milestones / epics / stories to their URLs.

## Spec-in-issue vs spec-in-repo

Two valid shapes; pick deliberately:

- **Spec in the issue body** (powerpoint-mcp): contributors read everything on GitHub; epic scope is not diffable in PRs.
- **Spec in repo, issue as thin pointer** (flowbench): scope changes go through review; readers need the repo.

## Verify before claiming done

```bash
gh project view "$NUM" --owner OWNER --format json | jq '{items:.items.totalCount,public,shortDescription}'
gh repo view OWNER/REPO --json projectsV2 -q '.projectsV2.Nodes[]|.number'
gh api repos/OWNER/REPO/milestones -q '.[]|[.title,(.description|length)]|@tsv'   # no zero-length descriptions
gh api repos/OWNER/REPO/issues/EPIC -q .sub_issues_summary
```
