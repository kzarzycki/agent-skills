"""scripts/nightly.py red: a red nightly's issue lists the merges since the last green commit (#1158); the text
tests of lead.md and SKILL.md are in test_contract.py, which `mise run test-engineering-package` runs."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

LOOP = Path(__file__).resolve().parents[1] / "skills" / "engineering-loop"
NIGHTLY = LOOP / "scripts" / "nightly.py"
REPO = "acme/widgets"
RUN = "https://github.com/acme/widgets/actions/runs/7"

# A fake gh: answers the REST calls nightly.py makes from a JSON state file, keeps the issues and comments it is
# asked to create there, and logs every call.
FAKE_GH = r"""#!/usr/bin/env python3
import json, os, re, sys
from pathlib import Path

args = sys.argv[1:]
state_path = Path(os.environ["FAKE_GH_STATE"])
state = json.loads(state_path.read_text())
with open(os.environ["FAKE_GH_LOG"], "a") as log:
    log.write(json.dumps(args) + "\n")
assert args[0] == "api", args
args = args[1:]
method = "GET"
if args[:2] == ["-X", "GET"]:
    args = args[2:]
path, rest = args[0], args[1:]
fields = dict(rest[i + 1].split("=", 1) for i, a in enumerate(rest) if a == "-f")
payload = None
if "--input" in rest:
    method = "POST"
    payload = json.loads(Path(rest[rest.index("--input") + 1]).read_text())
prefix = "repos/" + os.environ["FAKE_GH_REPO"] + "/"
assert path.startswith(prefix), path
path = path[len(prefix):]


def answer(value):
    print(json.dumps(value))
    raise SystemExit(0)


def issue(number):
    found = state["issues"].get(str(number))
    if found is None:
        print("HTTP 404: Not Found", file=sys.stderr)
        raise SystemExit(1)
    return found


def save():
    state_path.write_text(json.dumps(state))


if method == "POST" and path == "issues":
    number = state["next"]
    state["next"] += 1
    made = {"number": number, "title": payload["title"], "body": payload["body"], "state": "open",
            "html_url": f"https://github.com/x/y/issues/{number}"}
    state["issues"][str(number)] = made
    save()
    answer(made)
if method == "POST" and (m := re.fullmatch(r"issues/(\d+)/comments", path)):
    issue(m.group(1))
    comment = {"body": payload["body"], "html_url": f"https://github.com/x/y/issues/{m.group(1)}#c{len(state['comments'])}"}
    state["comments"].setdefault(m.group(1), []).append(comment)
    state["posted_comments"] = state.get("posted_comments", 0) + 1
    save()
    answer(comment)
if m := re.fullmatch(r"pulls/(\d+)", path):
    answer(state["pulls"][m.group(1)])
if m := re.fullmatch(r"commits/([0-9a-f]+)/pulls", path):
    answer(
        [
            p
            for p in state["pulls"].values()
            if m.group(1) == p.get("merge_commit_sha") or m.group(1) in p.get("contains", [])
        ]
    )
if path == "issues":
    page, size = int(fields.get("page", 1)), int(fields.get("per_page", 30))
    listed = [i for i in state["issues"].values() if i.get("state") == fields.get("state", "open")]
    answer(listed[(page - 1) * size: page * size])
if m := re.fullmatch(r"issues/(\d+)/comments", path):
    page, size = int(fields.get("page", 1)), int(fields.get("per_page", 30))
    answer(state["comments"].get(m.group(1), [])[(page - 1) * size : page * size])
if m := re.fullmatch(r"issues/(\d+)/parent", path):
    answer(issue(issue(m.group(1))["parent"]))
if m := re.fullmatch(r"issues/(\d+)", path):
    found = dict(issue(m.group(1)))
    if found.get("parent"):
        found["parent_issue_url"] = "https://api.github.com/repos/x/y/issues/" + str(found["parent"])
    answer(found)
print(f"fake gh: no answer for {method} {path}", file=sys.stderr)
raise SystemExit(1)
"""


def git(repo: Path, *args: str) -> str:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@invalid",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@invalid",
    }
    return subprocess.run(
        ["git", *args], cwd=repo, env=env, capture_output=True, text=True, check=True
    ).stdout.strip()


def change(repo: Path, name: str, message: str) -> str:
    (repo / name).write_text(message + "\n")
    git(repo, "add", name)
    git(repo, "commit", "-q", "-m", message)
    return git(repo, "rev-parse", "HEAD")


def squash(repo: Path, name: str, title: str, pr: int) -> str:
    return change(repo, name, f"{title} (#{pr})")


def merge(repo: Path, branch: str, pr: int) -> str:
    git(repo, "checkout", "-q", "-b", branch)
    change(repo, f"{branch}.txt", "work on the branch")
    git(repo, "checkout", "-q", "main")
    git(
        repo, "merge", "-q", "--no-ff", branch, "-m", f"Merge pull request #{pr} from acme/{branch}"
    )
    return git(repo, "rev-parse", "HEAD")


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict:
    """A repo whose main has, after its last green commit, two squashes and one merge commit, and a fake gh holding
    their PRs (each linking its spec, two specs under epics) and the specs."""
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    green = change(repo, "base.txt", "the last green commit")
    first = squash(repo, "a.txt", "Add the importer", 11)
    second = merge(repo, "feature-b", 12)
    third = squash(repo, "c.txt", "Fix the exporter", 13)

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "gh"
    fake.write_text(FAKE_GH)
    fake.chmod(0o755)
    state = {
        "next": 100,
        "comments": {},
        "pulls": {
            "11": {
                "number": 11,
                "title": "Add the importer",
                "body": "Part of #21\nCloses #21\n",
                "merge_commit_sha": first,
            },
            "12": {
                "number": 12,
                "title": "Rework the parser",
                "body": "Part of #22\n",
                "merge_commit_sha": second,
            },
            "13": {
                "number": 13,
                "title": "Fix the exporter",
                "body": "Fixes #23\nPart of #11, a PR, so no issue\n\n`Closes #99` is quoted, not a link.\n",
                "merge_commit_sha": third,
            },
        },
        "issues": {
            "20": {"number": 20, "title": "Epic: data flow", "state": "open", "html_url": "u20"},
            "21": {
                "number": 21,
                "title": "Importer",
                "state": "closed",
                "parent": 20,
                "html_url": "u21",
            },
            "22": {
                "number": 22,
                "title": "Parser",
                "state": "closed",
                "parent": 20,
                "html_url": "u22",
            },
            "23": {"number": 23, "title": "Exporter bug", "state": "closed", "html_url": "u23"},
            "11": {
                "number": 11,
                "title": "Add the importer",
                "state": "closed",
                "pull_request": {},
            },
        },
    }
    state_path = tmp_path / "gh-state.json"
    state_path.write_text(json.dumps(state))
    log = tmp_path / "gh-log.jsonl"
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("FAKE_GH_STATE", str(state_path))
    monkeypatch.setenv("FAKE_GH_LOG", str(log))
    monkeypatch.setenv("FAKE_GH_REPO", REPO)
    monkeypatch.delenv("LOOP_DENY_LIST", raising=False)
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    return {
        "repo": repo,
        "green": green,
        "red": third,
        "state": state_path,
        "log": log,
        "tmp": tmp_path,
    }


def nightly(
    project: dict, *args: str, red: str | None = None, repo: str | None = REPO
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(NIGHTLY),
            "red",
            "--last-green",
            project["green"],
            "--red",
            red or project["red"],
            "--run",
            RUN,
            *(["--repo", repo] if repo else []),
            *args,
        ],
        cwd=project["repo"],
        capture_output=True,
        text=True,
        check=False,
    )


def state(project: dict) -> dict:
    return json.loads(project["state"].read_text())


def created(project: dict) -> list[dict]:
    return [issue for number, issue in state(project)["issues"].items() if int(number) >= 100]


def posts(project: dict) -> list[list[str]]:
    """Each call that wrote to GitHub."""
    if not project["log"].exists():  # gh was never called
        return []
    return [call for call in calls(project) if "--input" in call]


def calls(project: dict) -> list[list[str]]:
    if not project["log"].exists():  # gh was never called
        return []
    return [json.loads(line) for line in project["log"].read_text().splitlines()]


def listed(body: str) -> list[str]:
    return [line for line in body.splitlines() if line.startswith("- ")]


def test_a_red_night_opens_one_issue_listing_exactly_the_three_merges_with_their_issues_and_epics(
    project: dict,
) -> None:
    result = nightly(project)

    assert result.returncode == 0, result
    assert result.stdout.strip() == "https://github.com/x/y/issues/100"
    [issue] = created(project)
    short = project["green"][:7]
    assert issue["title"] == f"Nightly red since {short}"
    assert RUN in issue["body"]
    log = git(
        project["repo"],
        "log",
        "--first-parent",
        "--format=%h",
        f"{project['green']}..{project['red']}",
    )
    merges = log.split()[::-1]
    assert listed(issue["body"]) == [
        f"- #11 Add the importer (squash `{merges[0]}`): closes #21, epic #20",
        f"- #12 Rework the parser (merge `{merges[1]}`): part of #22, epic #20",
        f"- #13 Fix the exporter (squash `{merges[2]}`): closes #23",
    ]
    assert (
        f"<!-- nightly-red last-green={project['green']} red={project['red']} -->" in issue["body"]
    )
    # each PR came from its commit's subject, with no commit-to-PR lookup
    assert not [call for call in calls(project) if "/commits/" in call[1]]


def test_run_again_after_a_fourth_merge_it_comments_on_that_issue_with_only_the_new_merge(
    project: dict,
) -> None:
    assert nightly(project).returncode == 0
    fourth = squash(project["repo"], "d.txt", "Speed up the loader", 14)
    current = state(project)
    current["pulls"]["14"] = {
        "number": 14,
        "title": "Speed up the loader",
        "body": "Closes #22",
        "merge_commit_sha": fourth,
    }
    project["state"].write_text(json.dumps(current))

    result = nightly(project, red=fourth)

    assert result.returncode == 0, result
    assert len(created(project)) == 1
    [comment] = state(project)["comments"]["100"]
    assert result.stdout.strip() == comment["html_url"]
    assert comment["body"].startswith(f"Still red on `{fourth[:7]}`: {RUN}")
    assert listed(comment["body"]) == [
        f"- #14 Speed up the loader (squash `{fourth[:7]}`): closes #22, epic #20"
    ]
    assert f"red={fourth} -->" in comment["body"]


def test_the_same_red_commit_again_comments_that_nothing_new_merged(project: dict) -> None:
    assert nightly(project).returncode == 0

    result = nightly(project)

    assert result.returncode == 0, result
    [comment] = state(project)["comments"]["100"]
    assert listed(comment["body"]) == [
        f"- none since `{project['red'][:7]}`, the red commit the last post names"
    ]


def test_a_closed_issue_of_the_same_title_gets_a_new_one(project: dict) -> None:
    assert nightly(project).returncode == 0
    current = state(project)
    current["issues"]["100"]["state"] = "closed"
    project["state"].write_text(json.dumps(current))

    assert nightly(project).returncode == 0

    assert [issue["number"] for issue in created(project)] == [100, 101]


def test_a_body_naming_a_deny_listed_term_is_refused_before_posting(
    project: dict, monkeypatch
) -> None:
    deny = project["tmp"] / "deny.txt"
    deny.write_text("# private names\nPARSER   # a product\n")
    monkeypatch.setenv("LOOP_DENY_LIST", str(deny))

    result = nightly(project)

    assert result.returncode == 1, result
    assert "names `PARSER` from the deny list (LOOP_DENY_LIST); nothing posted" in result.stderr
    assert posts(project) == []
    assert created(project) == []


def test_a_deny_list_that_cannot_be_read_refuses_too(project: dict, monkeypatch) -> None:
    monkeypatch.setenv("LOOP_DENY_LIST", str(project["tmp"] / "missing.txt"))

    result = nightly(project)

    assert result.returncode == 1, result
    assert "can't be read" in result.stderr
    assert posts(project) == []


def test_a_term_inside_a_longer_word_is_not_denied(project: dict, monkeypatch) -> None:
    deny = project["tmp"] / "deny.txt"
    deny.write_text("# a comment line names no term\npars\n")
    monkeypatch.setenv("LOOP_DENY_LIST", str(deny))

    assert nightly(project).returncode == 0
    assert len(created(project)) == 1


def test_a_listed_host_inside_a_session_link_is_denied_only_outside_one(
    tmp_path: Path, monkeypatch
) -> None:
    """nightly.py runs the gatekeeper's denylist.py: a listed host inside an Omnigent session link passes (#2571)."""
    spec = importlib.util.spec_from_file_location("nightly_under_test", NIGHTLY)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    deny = tmp_path / "deny.txt"
    deny.write_text("build-host.local\n")
    monkeypatch.setenv("LOOP_DENY_LIST", str(deny))
    link = "https://build-host.local:8443/c/" + "ab" * 16

    module.denied(f"Session: {link}\n")
    with pytest.raises(module.Refused, match="line 2 names `build-host.local`"):
        module.denied(f"Session: {link}\nran on build-host.local\n")


def test_dry_run_prints_the_body_and_posts_nothing(project: dict) -> None:
    result = nightly(project, "--dry-run")

    assert result.returncode == 0, result
    assert len(listed(result.stdout)) == 3
    assert posts(project) == []


def test_a_direct_push_is_listed_as_a_commit_with_no_pr(project: dict) -> None:
    direct = change(project["repo"], "e.txt", "hotfix the config")
    current = state(project)
    # GitHub also answers with an open PR whose branch holds the commit; it did not merge it
    current["pulls"]["17"] = {"number": 17, "title": "Later work", "body": "", "contains": [direct]}
    project["state"].write_text(json.dumps(current))

    result = nightly(project, red=direct)

    assert result.returncode == 0, result
    [issue] = created(project)
    assert listed(issue["body"])[-1] == f"- `{direct[:7]}` hotfix the config (no PR: a direct push)"


def test_a_merge_commit_with_another_subject_is_found_through_github(project: dict) -> None:
    repo = project["repo"]
    git(repo, "checkout", "-q", "-b", "feature-f")
    change(repo, "f.txt", "f work")
    git(repo, "checkout", "-q", "main")
    git(repo, "merge", "-q", "--no-ff", "feature-f", "-m", "Land the formatter")
    merged = git(repo, "rev-parse", "HEAD")
    current = state(project)
    current["pulls"]["15"] = {
        "number": 15,
        "title": "Land the formatter",
        "body": "",
        "merge_commit_sha": merged,
    }
    project["state"].write_text(json.dumps(current))

    assert nightly(project, red=merged).returncode == 0

    [issue] = created(project)
    assert (
        listed(issue["body"])[-1]
        == f"- #15 Land the formatter (merge `{merged[:7]}`): links no issue"
    )


def test_a_last_green_that_is_not_an_ancestor_of_the_red_exits_2(project: dict) -> None:
    repo = project["repo"]
    git(repo, "checkout", "-q", "--orphan", "other")
    other = change(repo, "z.txt", "unrelated")
    git(repo, "checkout", "-q", "main")

    result = nightly(project, red=other)

    assert result.returncode == 2, result
    assert "is not an ancestor" in result.stderr
    assert posts(project) == []


def test_an_unknown_commit_exits_2(project: dict) -> None:
    result = nightly(project, red="0" * 40)

    assert result.returncode == 2, result
    assert "no commit" in result.stderr


def test_a_fifth_merge_lists_only_what_merged_since_the_newest_red_post(project: dict) -> None:
    assert nightly(project).returncode == 0
    fourth = squash(project["repo"], "d.txt", "Speed up the loader", 14)
    fifth = squash(project["repo"], "e.txt", "Trim the cache", 16)
    current = state(project)
    for number, sha in ((14, fourth), (16, fifth)):
        current["pulls"][str(number)] = {
            "number": number,
            "title": f"PR {number}",
            "body": "",
            "merge_commit_sha": sha,
        }
    project["state"].write_text(json.dumps(current))
    assert nightly(project, red=fourth).returncode == 0

    assert nightly(project, red=fifth).returncode == 0

    last = state(project)["comments"]["100"][-1]
    assert listed(last["body"]) == [f"- #16 PR 16 (squash `{fifth[:7]}`): links no issue"]


def test_a_red_post_naming_a_commit_off_the_history_is_passed_over(project: dict) -> None:
    repo = project["repo"]
    assert nightly(project).returncode == 0
    git(repo, "checkout", "-q", "--orphan", "rewritten")
    gone = change(repo, "z.txt", "a commit a force-push left behind")
    git(repo, "checkout", "-q", "main")
    fourth = squash(repo, "d.txt", "Speed up the loader", 14)
    current = state(project)
    current["pulls"]["14"] = {
        "number": 14,
        "title": "PR 14",
        "body": "",
        "merge_commit_sha": fourth,
    }
    current["comments"]["100"] = [{"body": marker(project["green"], gone)}]
    project["state"].write_text(json.dumps(current))

    assert nightly(project, red=fourth).returncode == 0

    last = state(project)["comments"]["100"][-1]
    assert listed(last["body"]) == [f"- #14 PR 14 (squash `{fourth[:7]}`): links no issue"]


def test_a_red_commit_that_is_the_last_green_one_lists_none(project: dict) -> None:
    result = nightly(project, red=project["green"])

    assert result.returncode == 0, result
    [issue] = created(project)
    assert listed(issue["body"]) == ["- none: the red commit is the last green one"]


def test_a_failed_gh_call_exits_1_and_posts_nothing(project: dict) -> None:
    current = state(project)
    del current["pulls"]["13"]
    project["state"].write_text(json.dumps(current))

    result = nightly(project)

    assert result.returncode == 1, result
    assert "gh api repos/acme/widgets/pulls/13" in result.stderr
    assert posts(project) == []


def test_without_repo_it_reads_github_repository(project: dict, monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_REPOSITORY", REPO)

    assert nightly(project, repo=None).returncode == 0
    assert len(created(project)) == 1


def test_without_repo_or_github_repository_it_reads_the_origin_remote(project: dict) -> None:
    git(project["repo"], "remote", "add", "origin", f"git@github.com:{REPO}.git")

    assert nightly(project, repo=None).returncode == 0
    assert len(created(project)) == 1


def test_an_origin_that_is_not_github_exits_2(project: dict) -> None:
    git(project["repo"], "remote", "add", "origin", "https://example.invalid/acme/widgets.git")

    result = nightly(project, repo=None)

    assert result.returncode == 2, result
    assert "not a GitHub repository" in result.stderr


def marker(green: str, red: str) -> str:
    return f"<!-- nightly-red last-green={green} red={red} -->"


def test_the_open_issue_and_its_newest_red_are_found_past_the_first_page(
    project: dict, monkeypatch
) -> None:
    """In-process with a page of two, so the open issues and the issue's comments each span pages."""
    spec = importlib.util.spec_from_file_location("nightly_under_test", NIGHTLY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "PAGE", 2)
    monkeypatch.chdir(project["repo"])
    title = f"Nightly red since {project['green'][:7]}"
    current = state(project)
    current["issues"]["30"] = {"number": 30, "title": title, "state": "open", "pull_request": {}}
    current["issues"]["31"] = {"number": 31, "title": "Other", "state": "open"}
    current["issues"]["32"] = {
        "number": 32,
        "title": title,
        "state": "open",
        "body": marker(project["green"], project["green"]),
    }
    current["comments"]["32"] = [
        {"body": "a"},
        {"body": marker(project["green"], project["green"])},
        {"body": marker(project["green"], project["red"])},
    ]
    project["state"].write_text(json.dumps(current))
    args = ["red", "--last-green", project["green"], "--red", project["red"]]

    assert module.main([*args, "--run", RUN, "--repo", REPO]) == 0

    assert created(project) == []
    comment = state(project)["comments"]["32"][-1]
    assert listed(comment["body"]) == [
        f"- none since `{project['red'][:7]}`, the red commit the last post names"
    ]
