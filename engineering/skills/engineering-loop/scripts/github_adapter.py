"""The gatekeeper's GitHub adapter: the tracker, forge and evidence ports (gatekeeper.py, Ports) through `gh`, in the
checkout's repo. gatekeeper.py loads it beside itself; nothing else imports it."""

from __future__ import annotations

import json
import re
import subprocess
from typing import Any

# the collaborator permissions that can write; GitHub's `permission` field reads `maintain` as `write`
WRITE = {"admin", "maintain", "write"}


NOTE = "id author { login } body createdAt lastEditedAt isMinimized viewerCanMinimize"


SPECCED = f"number body createdAt lastEditedAt labels(first: 50) {{ nodes {{ name }} }} comments(last: 100) {{ totalCount nodes {{ {NOTE} }} }}"


ASSIGNEES = "assignees(first: 10) { nodes { login } }"


# who added `approved:spec` (approver) and who was assigned when (release); ponytail: the newest 100 such events
EVENTS = """timelineItems(last: 100, itemTypes: [LABELED_EVENT, ASSIGNED_EVENT]) { nodes { __typename
  ... on LabeledEvent { createdAt actor { __typename login } label { name } }
  ... on AssignedEvent { createdAt assignee { ... on User { login } ... on Bot { login } } } } }"""


# an issue with its author and its native parent (an epic), which spec_policy() reads, its assignees and events
ISSUE = f"{SPECCED} author {{ login }} parent {{ {SPECCED} }} {ASSIGNEES} {EVENTS}"


PULL = f"""id number title isCrossRepository author {{ __typename login }} {ASSIGNEES} state isDraft mergeStateStatus autoMergeRequest {{ enabledAt }} isInMergeQueue mergeQueueEntry {{ state enqueuedAt headCommit {{ checkSuites {{ totalCount }} }} }} body baseRefName baseRefOid headRefName headRefOid baseRepository {{ nameWithOwner defaultBranchRef {{ name }} }} labels(first: 50) {{ nodes {{ name }} }} comments(last: 100) {{ totalCount nodes {{ {NOTE} }} }}
  files(first: 100) {{ totalCount nodes {{ path changeType }} }} latestReviews(first: 100) {{ nodes {{ state author {{ login }} }} }}
  reviews(last: 100) {{ totalCount nodes {{ author {{ login }} state body commit {{ oid }} }} }}
  reviewThreads(first: 100) {{ totalCount nodes {{ isResolved }} }}
  authored: commits(first: 100) {{ totalCount nodes {{ commit {{ authors(first: 5) {{ totalCount nodes {{ user {{ login }} }} }} committer {{ user {{ login }} }} }} }} }}
  timelineItems(last: 100, itemTypes: [LABELED_EVENT, READY_FOR_REVIEW_EVENT]) {{ nodes {{ __typename
    ... on LabeledEvent {{ createdAt label {{ name }} }} ... on ReadyForReviewEvent {{ createdAt }} }} }}
  commits(last: 1) {{ nodes {{ commit {{ statusCheckRollup {{ contexts(first: 100) {{ totalCount nodes {{
    __typename ... on CheckRun {{ name status conclusion startedAt completedAt checkSuite {{ status workflowRun {{ workflow {{ name }} }} }} }}
    ... on StatusContext {{ context state createdAt targetUrl }} }} }} }} }} }} }}
  closingIssuesReferences(first: 50) {{ nodes {{ {ISSUE} }} }}"""


DEQUEUE = "mutation($id: ID!) { dequeuePullRequest(input: {id: $id}) { clientMutationId } }"


def merged_labelled(branch: str, name: str) -> list[int]:
    """The merged PRs into `branch` that carry the label `name`."""
    # ponytail: one page of 100; page when a feature branch takes more such PRs than that
    found = gh(
        "pr",
        "list",
        "--base",
        branch,
        "--state",
        "merged",
        "--label",
        name,
        "--limit",
        "100",
        "--json",
        "number",
        "--jq",
        ".[].number",
    )
    return [int(number) for number in found.split()]


def gh(*args: str, data: str | None = None) -> str:
    return subprocess.run(
        ["gh", *args], input=data, check=True, capture_output=True, text=True
    ).stdout


def _graphql(query: str, **fields: object) -> Any:
    args = [arg for key, value in fields.items() for arg in ("-F", f"{key}={value}")]
    # gh fills {owner} and {repo} from the current checkout
    out = gh(
        "api", "graphql", "-f", f"query={query}", "-F", "owner={owner}", "-F", "name={repo}", *args
    )
    return json.loads(out)["data"]["repository"]


def _repository(fields: str) -> str:
    return f"query($owner: String!, $name: String!, $n: Int!) {{ repository(owner: $owner, name: $name) {{ {fields} }} }}"


def pull_request(pr: int) -> dict[str, Any]:
    pull: dict[str, Any] = _graphql(_repository(f"pullRequest(number: $n) {{ {PULL} }}"), n=pr)[
        "pullRequest"
    ]
    return pull


def pr_changes(number: int) -> list[dict[str, Any]]:
    """Every file a PR changes, with its patch, as GitHub's REST API pages them: up to 3000."""
    out = gh(
        "api",
        "--paginate",
        f"repos/{{owner}}/{{repo}}/pulls/{number}/files?per_page=100",
        "--jq",
        ".[]",
    )
    return [json.loads(line) for line in out.splitlines()]


def merged_pull(number: int) -> dict[str, Any] | None:
    """PR #number as GitHub's REST API returns it, when it was merged; None for an open or closed PR, or an issue."""
    try:
        found: dict[str, Any] = json.loads(gh("api", f"repos/{{owner}}/{{repo}}/pulls/{number}"))
    except subprocess.CalledProcessError as exc:
        if "Not Found" in exc.stderr:
            return None
        raise
    return found if found.get("merged") else None


def merge_base(base: str, head: str) -> str:
    """The commit GitHub diffs a PR's head against: where it branched from its base."""
    return gh(
        "api", f"repos/{{owner}}/{{repo}}/compare/{base}...{head}", "--jq", ".merge_base_commit.sha"
    ).strip()


# GitHub's answer to a rules read on a private repo of a free plan
PLAN_LIMIT = "Upgrade to GitHub Pro"


def required_checks(base: str) -> set[str]:
    """The checks the base branch requires, from its live rules: its rulesets' and its branch protection's. A private
    repo on GitHub's free plan has no rulesets: that 403 reads as none, and any other error raises."""
    try:
        rulesets = gh(
            "api",
            "--paginate",
            f"repos/{{owner}}/{{repo}}/rules/branches/{base}",
            "--jq",
            '.[] | select(.type == "required_status_checks") | .parameters.required_status_checks[].context',
        )
    except subprocess.CalledProcessError as error:
        if "(HTTP 403)" not in (error.stderr or "") or PLAN_LIMIT not in error.stderr:
            raise
        print(
            f"GitHub enforces no rules on {base} here (its plan has none): land's proofs are the only gate"
        )
        rulesets = ""
    protection = gh(
        "api",
        f"repos/{{owner}}/{{repo}}/branches/{base}",
        "--jq",
        ".protection.required_status_checks.contexts // [] | .[]",
    )
    return set((rulesets + protection).split())


def queue_required(base: str) -> bool:
    """Whether the base branch's rules require a merge queue; an error reads as none, so land refuses as without one."""
    try:
        rules = gh(
            "api",
            "--paginate",
            f"repos/{{owner}}/{{repo}}/rules/branches/{base}",
            "--jq",
            '.[] | select(.type == "merge_queue") | .type',
        )
    except subprocess.CalledProcessError:
        return False
    return bool(rules.split())


def auto_merge_allowed() -> bool:
    return gh("api", "repos/{owner}/{repo}", "--jq", ".allow_auto_merge").strip() == "true"


def tree(sha: str) -> dict[str, tuple[str, str]] | None:
    """The (mode, blob SHA) of every path in commit `sha`'s tree, from GitHub's trees API; None when GitHub truncates it.
    ponytail: one recursive read, up to GitHub's 100,000 entries; read each touched directory when a repo outgrows it."""
    found = json.loads(gh("api", f"repos/{{owner}}/{{repo}}/git/trees/{sha}?recursive=1"))
    if found["truncated"]:
        return None
    return {
        entry["path"]: (entry["mode"], entry["sha"])
        for entry in found["tree"]
        if entry["type"] != "tree"
    }


def head_pushed(pull: dict[str, Any]) -> str | None:
    """When the head commit was last pushed to the PR's branch, from GitHub's repository activity (pushes, force
    pushes, the branch's creation); None when it lists none. ponytail: the newest 100 activities of a same-repo branch;
    page further, or read a fork's, when a PR here needs it."""
    out = gh(
        "api",
        f"repos/{{owner}}/{{repo}}/activity?ref=refs/heads/{pull['headRefName']}&per_page=100",
        "--jq",
        f'[.[] | select(.after == "{pull["headRefOid"]}") | .timestamp] | first // ""',
    ).strip()
    return out or None


def issue_node(number: int) -> dict[str, Any]:
    node: dict[str, Any] = _graphql(_repository(f"issue(number: $n) {{ {ISSUE} }}"), n=number)[
        "issue"
    ]
    return node


def issues(numbers: list[int]) -> list[dict[str, Any]]:
    """The issues among `numbers`, in one read; a number that is a pull request comes back empty and is dropped."""
    if not numbers:
        return []
    aliases = " ".join(
        f"i{n}: issueOrPullRequest(number: {n}) {{ ... on Issue {{ {ISSUE} }} }}" for n in numbers
    )
    found = _graphql(
        f"query($owner: String!, $name: String!) {{ repository(owner: $owner, name: $name) {{ {aliases} }} }}"
    )
    return [issue for issue in found.values() if issue]


def label(number: int, name: str, add: bool) -> None:
    """Add (GitHub creates a missing label) or remove a label on an issue or PR; removing an absent one is fine."""
    path = f"repos/{{owner}}/{{repo}}/issues/{number}/labels"
    if add:
        gh("api", path, "-f", f"labels[]={name}", "--silent")
        return
    try:
        gh("api", "-X", "DELETE", f"{path}/{name}", "--silent")
    except subprocess.CalledProcessError as exc:
        if "Label does not exist" not in exc.stderr:
            raise


def assign(number: int, login: str, add: bool) -> None:
    """Add or remove an assignee of an issue or PR; GitHub ignores an absent one."""
    gh(
        "api",
        *(() if add else ("-X", "DELETE")),
        f"repos/{{owner}}/{{repo}}/issues/{number}/assignees",
        "-f",
        f"assignees[]={login}",
        "--silent",
    )


def comment(number: int, body: str) -> None:
    gh(
        "api",
        f"repos/{{owner}}/{{repo}}/issues/{number}/comments",
        "-F",
        "body=@-",
        "--silent",
        data=body,
    )


def minimize(comment_id: str) -> None:
    """Collapse a comment on GitHub as outdated; it stays readable, and the gate still reads it."""
    gh(
        "api",
        "graphql",
        "-f",
        "query=mutation($id: ID!) { minimizeComment(input: {subjectId: $id, classifier: OUTDATED}) { clientMutationId } }",
        "-f",
        f"id={comment_id}",
        "--silent",
    )


def viewer() -> str | None:
    """The login of the account `gh` runs as; None for a token `GET /user` refuses, such as a workflow's installation
    token (`github.token`), where the PR's author and the repo's writers are the ones trusted (passes)."""
    try:
        return gh("api", "user", "--jq", ".login").strip()
    except subprocess.CalledProcessError:
        return None


def writer(login: str) -> bool:
    """Whether `login` can write to the repo, by GitHub's collaborator permission; an account GitHub refuses to look
    up can't. ponytail: a bot's GraphQL login lacks the `bot` REST needs, so a bot author fails closed; add the
    suffix when a project's bot opens sub-issues."""
    try:
        permission = gh(
            "api",
            f"repos/{{owner}}/{{repo}}/collaborators/{login}/permission",
            "--jq",
            ".permission",
        )
    except subprocess.CalledProcessError:
        return False
    return permission.strip() in WRITE


def current_pr() -> int | None:
    try:
        return int(gh("pr", "view", "--json", "number", "--jq", ".number"))
    except subprocess.CalledProcessError as exc:
        if "no pull requests found" in exc.stderr:
            return None
        raise


# a remote URL's host and `owner/repo`: `scheme://[user@]host[:port]/owner/repo` or scp-like `[user@]host:owner/repo`,
# its path maybe led by extra slashes as gh allows, matched once trailing slashes and `.git` are cut (post_demo.sh
# parses it the same way)
REMOTE_URL = re.compile(
    r"(?:[a-z][a-z0-9+.-]*://)?(?:[^@/]*@)?([^/:]+)(?::\d+)?[:/]/*([^/]+/[^/]+)", re.IGNORECASE
)


def github_repo(url: str) -> str | None:
    """The `owner/repo` a GitHub remote URL names, lowercased; None for another host."""
    found = REMOTE_URL.fullmatch(re.sub(r"(?:\.git)?/*$", "", url.rstrip("/")))
    return found[2].lower() if found and found[1].lower() == "github.com" else None


def one_repo() -> str | None:
    """Why gh can't run here, or None: a checkout whose remotes name several GitHub repos while none is gh's default (`gh repo set-default`,
    kept as `remote.<name>.gh-resolved`): gh then reads `{owner}/{repo}` and every `gh pr` as `upstream`, and a
    review or label lands on a repo nobody chose. Outside a checkout it passes, and gh says why it can't run."""
    remotes = subprocess.run(["git", "remote", "-v"], capture_output=True, text=True, check=False)
    repos = sorted(
        {
            repo
            for line in remotes.stdout.splitlines()
            if len(fields := line.split()) > 1 and (repo := github_repo(fields[1]))
        }
    )
    chosen = subprocess.run(
        ["git", "config", "--get-regexp", r"^remote\..*\.gh-resolved$"],
        capture_output=True,
        check=False,
    )
    if len(repos) > 1 and chosen.returncode:
        return (
            f"this checkout's remotes name {', '.join(repos)} and gh has no default among them, so gh would pick one"
            " itself: run `gh repo set-default <owner>/<repo>` once, naming the repo the PRs live in"
        )
    return None


def diff_lines(base: str, head: str) -> dict[str, list[int]]:
    """The lines a review at `head` can comment on, per file: the new side of GitHub's diff of base...head (added and
    context lines). ponytail: one compare, up to the 300 files it lists."""
    out = gh(
        "api",
        f"repos/{{owner}}/{{repo}}/compare/{base}...{head}",
        "--jq",
        ".files[] | {filename, patch}",
    )
    found: dict[str, list[int]] = {}
    for entry in (json.loads(line) for line in out.splitlines()):
        lines, number = found.setdefault(entry["filename"], []), 0
        for line in (entry.get("patch") or "").split("\n"):
            hunk = re.match(r"@@ -\d+(?:,\d+)? \+(\d+)", line)
            if hunk:
                number = int(hunk.group(1))
            elif line[:1] in (" ", "+"):
                lines.append(number)
                number += 1
    return found


def post_review(pr: int, review: dict[str, Any]) -> None:
    gh(
        "api",
        f"repos/{{owner}}/{{repo}}/pulls/{pr}/reviews",
        "--input",
        "-",
        "--silent",
        data=json.dumps(review, ensure_ascii=False),
    )


def dequeue(node_id: str) -> None:
    """Take the PR, by its node id, out of the merge queue."""
    gh("api", "graphql", "-f", f"query={DEQUEUE}", "-f", f"id={node_id}")


def ready(pr: int) -> None:
    gh("pr", "ready", str(pr))


def merge(pr: int, head: str, auto: bool = False) -> None:
    """Squash-merge the PR pinned to `head`, or with `auto` turn auto-merge on, merging once the required checks pass."""
    # ponytail: no --delete-branch, which also deletes the local branch a worktree has checked out; the repo's
    # delete_branch_on_merge removes the remote one. Add it when a repo lacks that setting.
    gh(
        "pr",
        "merge",
        str(pr),
        "--squash",
        "--match-head-commit",
        head,
        *(["--auto"] if auto else []),
    )


def run(run_id: str) -> dict[str, Any] | None:
    """An Actions run of this repo as `{status, url}`, or None for one gh can't read (another repo's, or gone)."""
    try:
        found: dict[str, Any] = json.loads(gh("run", "view", run_id, "--json", "status,url"))
    except subprocess.CalledProcessError:
        return None
    return found


def rerun(run_id: str) -> None:
    gh("run", "rerun", run_id)
