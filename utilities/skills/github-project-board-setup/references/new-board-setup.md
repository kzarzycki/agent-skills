# First-time board setup

Read only when the repo has no board yet. Day-2 work (adding milestones, epics, stories) is in `SKILL.md` and does not need this file.

## Hard constraints (learned the hard way)

- **Repo-owned projects do not exist.** ProjectsV2 owners are users or orgs only. A repo gets a *linked* project. Org ownership requires transferring the repo — reversible, but it changes URLs and any install paths embedding `owner/repo`. Ask before doing that.
- **Issue types (Epic/Story/Task/Bug) are org-only.** On personal repos use `type:*` labels; the board's built-in Labels field groups by them. You lose the `type:` search qualifier and the badge on the issue list.
- **`gh project link` exits 0 without linking when `has_projects` is false.** Always enable first, always verify after.
- `gh repo view --json projectsV2` returns an **object wrapping a `Nodes` array** — `-q '.projectsV2.Nodes[]|…'` (capital N). A bare `.projectsV2[]` errors with `expected an array but got: object`, which looks exactly like a failed link.

## Procedure

### 1. Create and link

```bash
gh api -X PATCH repos/OWNER/REPO -F has_projects=true -q '.has_projects'   # must print true
OWNER_ID=$(gh api graphql -f query='query($l:String!){repositoryOwner(login:$l){id}}' -f l=OWNER -q .data.repositoryOwner.id)   # a user or an org
REPO_ID=$(gh api repos/OWNER/REPO -q .node_id)
read -r NUM PID < <(gh api graphql -f query='mutation($o:ID!,$r:ID!){createProjectV2(input:{ownerId:$o,title:"REPO",repositoryId:$r}){projectV2{number id}}}' \
  -f o="$OWNER_ID" -f r="$REPO_ID" -q '.data.createProjectV2.projectV2|"\(.number) \(.id)"')
[ -n "$PID" ] || { echo "create failed"; exit 1; }
gh repo view OWNER/REPO --json projectsV2 -q '.projectsV2.Nodes[]|[.number,.title]|@tsv'   # must list it
gh api graphql -f query='mutation($p:ID!,$d:String!,$m:String!){updateProjectV2(input:{projectId:$p,shortDescription:$d,readme:$m}){projectV2{public}}}' \
  -f p="$PID" -f d="Engineering board: the tickets of REPO in their loop stage" -f m="$(cat board-readme.md)"
```

`repositoryId` links the board to the repo in the same call. A new board is private; whether to open it (`public:true` in `updateProjectV2`) is the project's choice. Opening it does not expose a private repo's items: [GitHub's visibility docs](https://docs.github.com/en/issues/planning-and-tracking-with-projects/managing-your-project/managing-visibility-of-your-projects) keep each item visible only to people who can see its repo. `gh project create` and `gh project edit` fail on gh 2.87.0 with `Variable $query is used by CreateProjectV2 but not declared`, hence the API calls; on a gh where they work, `gh project create --owner OWNER --title REPO`, `gh project link` and `gh project edit --visibility … --description … --readme "$(cat board-readme.md)"` do the same (`--readme` takes a string; there is no `--readme-file`). The token needs the `project` scope (`gh auth refresh -s project`); `read:project` lists boards and refuses every write with `INSUFFICIENT_SCOPES`.

### 2. Fields and views

`Status` already exists with `Todo|In Progress|Done`. Replace the option set with the stages of the project's engineering loop, in order, ending in `Done` (the names below are an example; take the real ones from the project's docs). `updateProjectV2Field` **replaces**, so list every option you want:

```bash
FID=$(gh project field-list "$NUM" --owner OWNER --format json | jq -r '.fields[]|select(.name=="Status").id')
cat > /tmp/q.graphql <<EOF
mutation{updateProjectV2Field(input:{fieldId:"$FID",singleSelectOptions:[
 {name:"Intent",color:GRAY,description:""},{name:"Needs owner",color:RED,description:""},
 {name:"Ready",color:BLUE,description:""},{name:"Build",color:YELLOW,description:""},
 {name:"Verify",color:ORANGE,description:""},{name:"Done",color:GREEN,description:""}]}){projectV2Field{... on ProjectV2SingleSelectField{options{id name}}}}}
EOF
gh api graphql -F query=@/tmp/q.graphql
FIELDS=$(gh project field-list "$NUM" --owner OWNER --format json)   # re-read: the replace gave every option a new id
STATUS_FIELD_ID=$(jq -r '.fields[]|select(.name=="Status").id' <<<"$FIELDS")
FIRST_COLUMN_OPTION_ID=$(jq -r '.fields[]|select(.name=="Status").options[0].id' <<<"$FIELDS")
```

No other field is needed, except `Priority` where the project ranks work: a view sorts and groups by a single-select field, not by a label.

```bash
gh api graphql -f p="$PID" -f query='mutation($p:ID!){createProjectV2Field(input:{projectId:$p,dataType:SINGLE_SELECT,name:"Priority",singleSelectOptions:[
 {name:"P0",color:RED,description:"Now"},{name:"P1",color:ORANGE,description:"Next"},
 {name:"P2",color:YELLOW,description:"Planned"},{name:"P3",color:GRAY,description:"Someday"}]}){projectV2Field{... on ProjectV2SingleSelectField{id}}}}'
```

Views come from REST, which sets a view's layout, filter, visible fields, grouping (`group_by`, swimlanes), board columns (`vertical_group_by`) and sort (`sort_by`) when it creates it. GraphQL's `createProjectV2View` and `updateProjectV2View` set only the first three, and nothing regroups an existing view, so create every view this way, in the order the tabs should show, then delete the default `View 1`. REST takes the fields' numeric REST ids. The built-in "Assignees", "Parent issue" and "Sub-issues progress" fields show only where a view lists them.

```bash
BASE=orgs/OWNER/projectsV2/$NUM   # users/OWNER/projectsV2/$NUM for a user's board
F=$(gh api "$BASE/fields" --paginate); f() { jq --arg n "$1" '.[]|select(.name==$n).id' <<<"$F"; }
T=$(f Title) S=$(f Status) A=$(f Assignees) L=$(f Labels) PA=$(f "Parent issue") SP=$(f "Sub-issues progress") P=$(f Priority)
view() { gh api -X POST "$BASE/views" --input - -q '[.number,.name]|@tsv' <<<"$1"; }
view '{"name":"Board","layout":"board","vertical_group_by":['$S'],"sort_by":[['$P',"asc"]],"visible_fields":['$T,$P,$A,$L,$PA,$SP']}'
view '{"name":"By epic","layout":"table","filter":"-label:epic","group_by":['$PA'],"sort_by":[['$P',"asc"]],"visible_fields":['$T,$S,$P,$A,$L']}'
view '{"name":"Epics","layout":"table","filter":"label:epic","visible_fields":['$T,$S,$P,$A,$SP']}'
V1=$(gh api graphql -f p="$PID" -f query='query($p:ID!){node(id:$p){... on ProjectV2{views(first:1){nodes{id}}}}}' -q '.data.node.views.nodes[0].id')
gh api graphql -f v="$V1" -f query='mutation($v:ID!){deleteProjectV2View(input:{viewId:$v}){clientMutationId}}'
```

Without a Priority field, drop `$P` and the `sort_by` entries. `Title`, `Reviewers`, `Linked pull requests` and `Sub-issues progress` can't be grouped on.

A board created through the API has the built-in "Item closed" and "Item added to project" workflows switched off; only "Auto-add sub-issues to project" is on. Which ones a board keeps on is the project's rule (a loop whose own script moves every ticket keeps them off); `scripts/project_workflows.py` switches on the ones it wants (step 7). Where "Item closed" stays off, nothing moves a closed issue to `Done`: the loop sets `Done` itself at the step that closes the issue.

### 3. Labels

On a repo the engineering loop runs, skip this step: the loop's label sync (engineering-loop's `github.md`, Labels) owns the labels and its names (`kind:bug`, `approved:spec`) replace these, so labels made here would only be deleted or renamed by its next run.

```bash
for l in "epic|8250DF|An outcome the owner tracks; its work items are sub-issues" \
         "type:story|1D76DB|Story: one engineering-loop iteration" \
         "type:task|0E8A16|Task: small, well-specified work item" \
         "type:bug|D73A4A|Bug: something is broken" \
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
gh issue create --title "E00 — Bridge foundation (M0)" --label epic --milestone M0 --body-file epic.md
```

Sub-issues take the **REST numeric id**, not the issue number, and `-F` (not `-f`) or the API rejects it as a string:

```bash
SUB_ID=$(gh api repos/OWNER/REPO/issues/126 -q .id)
gh api repos/OWNER/REPO/issues/125/sub_issues -F sub_issue_id="$SUB_ID" -q .number
gh api repos/OWNER/REPO/issues/125 -q .sub_issues_summary     # {"completed":0,"total":9}
```

Dependencies from the roadmap's deps column:

```bash
gh api --method POST repos/OWNER/REPO/issues/135/dependencies/blocked_by -F issue_id="$(gh api repos/OWNER/REPO/issues/125 -q .id)"   # the blocker's REST id; gh 2.87.0 has no --add-blocked-by
gh api repos/OWNER/REPO/issues/135/dependencies/blocked_by -q '.[]|.number'
```

### 6. Board items and fields

```bash
ITEM=$(gh project item-add "$NUM" --owner OWNER --url https://github.com/OWNER/REPO/issues/125 --format json | jq -r .id)
gh project item-edit --project-id "$PID" --id "$ITEM" --field-id "$STATUS_FIELD_ID" --single-select-option-id "$FIRST_COLUMN_OPTION_ID"
```

Re-read `field-list` after any field mutation; option ids change.

### 7. Workflows

No public API switches a workflow on: GraphQL has only `deleteProjectV2Workflow`, and REST has no workflow endpoint. `scripts/project_workflows.py` sends the web UI's own requests from a background tab of a browser signed in to GitHub, from a spec naming each workflow and its field value by name (its docstring has the format):

```bash
cat > /tmp/workflows.json <<'JSON'
{"owner": "OWNER", "number": 12, "workflows": [
  {"name": "Auto-add to project", "query": "is:issue is:open", "repository": "OWNER/REPO"},
  {"name": "Item closed", "set": {"Status": "Done"}}]}
JSON
export CDP_URL=http://127.0.0.1:9222   # the signed-in browser's debugging port
uv run --with playwright python scripts/project_workflows.py /tmp/workflows.json --dry-run   # prints the requests
uv run --with playwright python scripts/project_workflows.py /tmp/workflows.json
gh api graphql -f p="$PID" -f query='query($p:ID!){node(id:$p){... on ProjectV2{workflows(first:20){nodes{name enabled}}}}}' -q '.data.node.workflows.nodes[]|[.name,.enabled]|@tsv'
```

It exits 1, naming the page it reached, when the browser isn't signed in or an org's SSO asks for a sign-in: the person completes it in that browser and the script runs again. "Auto-add sub-issues to project" is on by default: adding a parent issue pulls in its sub-issues, closed ones included, with no Status. Give them a column in the same pass.

## A board of pull requests

A view of every PR in flight, merged and closed, kept current by the built-in workflows alone: no token, Actions workflow or sync script.

- **Unlinked.** Create it with `createProjectV2` and no `repositoryId`, owned by the repo's org or user. A board script that takes the repo's first linked project as the issue board would otherwise move tickets on the PR board. `gh repo view --json projectsV2` lists only the issue board; check it after creating the PR board and whenever a board move fails.
- **Status** `Open`, `Merged`, `Closed`, replacing the default options (step 2).
- **Workflows** (step 7): "Auto-add to project" with `is:pr is:open` for the repo; "Item added to project" and "Item reopened", content type pull request, set `Open`; "Item closed" sets `Closed`; "Pull request merged" sets `Merged`, which wins over "Item closed" on a merge. "Code review approved" and "Code changes requested" fire only on a GitHub review with that verdict, never on a comment review.
- **Drafts are a filter, not a column.** No workflow fires on draft or ready for review, but the view filter `is:draft` is always current: a `Ready` view filtered `is:open -is:draft`, a `Drafts` view filtered `is:open is:draft`, and a board of every PR by Status.
- **Backfill** the existing PRs once: `gh project item-add` each, then set its Status from `gh pr list --state all --json number,state`.

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
gh api graphql -f p="$PID" -f query='query($p:ID!){node(id:$p){... on ProjectV2{views(first:10){nodes{name filter fields(first:20){nodes{... on ProjectV2FieldCommon{name}}}}}}}}' -q '.data.node.views.nodes[]|[.name,.filter,([.fields.nodes[].name]|join(","))]|@tsv'   # Epics view, label:epic, Parent issue + Sub-issues progress shown
gh api repos/OWNER/REPO/milestones -q '.[]|[.title,(.description|length)]|@tsv'   # no zero-length descriptions
gh api repos/OWNER/REPO/issues/EPIC -q .sub_issues_summary
```
