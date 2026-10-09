"""scripts/labels.py: the repo's labels become the loop's set plus the tracker file's, renamed in place, and a label
in use is never deleted."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "skills" / "engineering-loop" / "scripts"
sys.path.insert(
    0, str(SCRIPTS)
)  # as when run: labels.py reads the label names from approvals.py beside it
SPEC = importlib.util.spec_from_file_location("labels", SCRIPTS / "labels.py")
assert SPEC and SPEC.loader
labels = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(labels)

TRACKER = """Tracker: GitHub (engineering-loop's github.md)

## Components

- **`api`**: the HTTP service.
- `area:web`: the browser UI.

## Extra labels

- `triaged-by-bot`: classifies only.

## Renamed labels

- `frontend` becomes `area:web`
"""


class Repo:
    """A repo's labels and which issues carry each, behind the gh calls labels.py makes; every write is logged."""

    def __init__(self, existing: dict[str, tuple[str, str]], carried: dict[str, list[int]]) -> None:
        self.labels = dict(existing)
        self.carried = {name: list(numbers) for name, numbers in carried.items()}
        self.writes: list[tuple[str, ...]] = []

    def gh(self, *args: str) -> str:
        fields = dict(
            arg.split("=", 1) for arg in args if "=" in arg and not arg.startswith("repos/")
        )
        if args[:2] == ("api", "--paginate") and args[2].startswith("repos/{owner}/{repo}/labels"):
            return "".join(
                json.dumps({"name": name, "color": colour, "description": text}) + "\n"
                for name, (colour, text) in self.labels.items()
            )
        if "repos/{owner}/{repo}/issues" in args and "GET" in args:
            return "".join(f"{number}\n" for number in self.carried.get(fields["labels"], []))
        method = args[args.index("-X") + 1] if "-X" in args else "POST"
        path = next(arg for arg in args if arg.startswith("repos/"))
        self.writes.append((method, unquote(path), *sorted(f"{k}={v}" for k, v in fields.items())))
        name = unquote(path.rsplit("/", 1)[1])
        if path == "repos/{owner}/{repo}/labels":
            self.labels[fields["name"]] = (fields["color"], fields["description"])
        elif "/issues/" in path and method == "POST":
            self.carried.setdefault(fields["labels[]"], []).append(int(path.split("/")[4]))
        elif "/issues/" in path:
            self.carried[name].remove(int(path.split("/")[4]))
        elif method == "DELETE":
            del self.labels[name]
        elif "new_name" in fields:
            self.labels[fields["new_name"]] = self.labels.pop(name)
            self.carried[fields["new_name"]] = self.carried.pop(name, [])
        else:
            self.labels[name] = (fields["color"], fields["description"])
        return ""


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Repo:
    """GitHub's default labels, one in use, a Dependabot label, the old categories and a component's bare name."""
    agents = tmp_path / "docs" / "agents"
    agents.mkdir(parents=True)
    (agents / "issue-tracker.md").write_text(TRACKER)
    monkeypatch.setattr(labels, "toplevel", lambda: tmp_path)
    found = Repo(
        {
            "bug": ("d73a4a", "Something isn't working"),
            "chore": ("ededed", ""),
            "documentation": ("0075ca", "Improvements or additions to documentation"),
            "api": ("ededed", ""),
            "frontend": ("ededed", ""),
            "wontfix": ("ffffff", "This will not be worked on"),
            "question": ("d876e3", "Further information is requested"),
            "dependencies": ("0366d6", "Pull requests that update a dependency file"),
            "python": ("2b67c6", "Pull requests that update Python code"),
        },
        {"bug": [1, 4], "chore": [2], "documentation": [3], "api": [1], "wontfix": [5]},
    )
    monkeypatch.setattr(labels, "gh", found.gh)
    return found


def test_a_run_renames_in_place_folds_creates_and_deletes_only_what_nothing_carries(
    repo: Repo, capsys: pytest.CaptureFixture[str]
) -> None:
    assert labels.main([]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[:5] == [
        "rename frontend to area:web",
        "rename bug to kind:bug",
        "rename chore to kind:chore",
        "fold documentation into kind:chore on 1 issue(s) or PR(s)",
        "rename api to area:api",
    ]
    assert out[-2:] == ["delete question", "kept wontfix: 1 issue(s) or PR(s) carry it"]
    # a rename is one PATCH, never a delete and a create, so every issue keeps its label
    assert ("PATCH", "repos/{owner}/{repo}/labels/bug", "new_name=kind:bug") in repo.writes
    assert repo.carried["kind:bug"] == [1, 4] and repo.carried["area:api"] == [1]
    assert sorted(repo.carried["kind:chore"]) == [2, 3] and "documentation" not in repo.labels
    assert set(repo.labels) == set(labels.wanted(TRACKER)) | {"wontfix", "dependencies", "python"}
    assert repo.labels["area:api"] == (labels.AREA, "the HTTP service.")
    assert repo.labels["size:XS"] == labels.LOOP_LABELS["size:XS"]


def test_a_second_run_changes_nothing(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    labels.main([])
    writes = len(repo.writes)
    capsys.readouterr()
    assert labels.main([]) == 0
    assert len(repo.writes) == writes
    assert capsys.readouterr().out == "kept wontfix: 1 issue(s) or PR(s) carry it\n"


def test_a_dry_run_writes_nothing(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    assert labels.main(["--dry-run"]) == 0
    assert repo.writes == []
    assert capsys.readouterr().out.startswith("would rename frontend to area:web\n")


def test_without_the_tracker_file_it_refuses(
    repo: Repo, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "docs" / "agents" / "issue-tracker.md").unlink()
    assert labels.main([]) == 1
    assert repo.writes == []
    assert "nothing says which labels are the repo's" in capsys.readouterr().out


def test_gh_failing_exits_1_with_its_reason(monkeypatch: pytest.MonkeyPatch, repo: Repo) -> None:
    def refuse(*args: str) -> str:
        raise subprocess.CalledProcessError(1, "gh", stderr="HTTP 403: Resource not accessible")

    monkeypatch.setattr(labels, "gh", refuse)
    assert labels.main([]) == 1


def test_the_tracker_can_send_documentation_elsewhere_before_the_loops_fold() -> None:
    tracker = "## Extra categories\n\n- `docs`: only docs change.\n\n## Renamed labels\n\n- `documentation` -> `kind:docs`\n"
    actions, _ = labels.plan({"documentation": ("0075ca", "")}, tracker)
    assert actions[0] == ("rename", "documentation", "kind:docs", "")
    assert ("create", "kind:chore", *labels.LOOP_LABELS["kind:chore"]) in actions
