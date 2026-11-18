"""approvals.py narrowed mode (#1422): loop.md's `Affected tests:` command gates every head, `land`'s batch and a
`ci: false` project's ready head, against an explicit base or the merge base; `Gate: full` opts out, and a narrowed
pass never stands for a full one."""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path
from typing import Any

import pytest
from approvals_harness import approvals, git_in

# a selector: the files changed since the base it reads from GATE_BASE, logged with that base, so a test reads both
SELECTOR = """import os, pathlib, subprocess, sys
base = os.environ["GATE_BASE"]
changed = subprocess.run(["git", "diff", "--name-only", base, "HEAD"], capture_output=True, text=True, check=True).stdout.split()
log = pathlib.Path(__file__).parent / "ran.log"
log.open("a").write(f"selected {' '.join(changed) or 'nothing'} against {base}\\n")
"""

# a stand-in `mise` that logs its arguments and whether the base variable reached it
MISE = """#!/bin/sh
echo "mise $* base=${GATE_BASE:-unset}" >> "$(dirname "$0")/ran.log"
"""

NO_CI = "## Settings\n\n```yaml\nloop:\n  ci: false\n```\n"


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """A clone of an origin holding `main`, on a branch `work` with one code commit, a stand-in `mise` and a selector
    beside it (outside the tree, so a run leaves the checkout clean), loop.md read from the working tree. `loop(text)`
    writes and commits loop.md on `main` (pushed) and on `work`; `ran()` lists what the selector and `mise` logged."""
    origin, work = tmp_path / "origin.git", tmp_path / "repo"
    git_in(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    git_in(tmp_path, "clone", "-q", str(origin), str(work))
    git_in(work, "config", "user.email", "loop@example.com")
    git_in(work, "config", "user.name", "loop")
    git_in(work, "checkout", "-q", "-b", "main")
    (work / "docs" / "agents").mkdir(parents=True)
    (work / "app.py").write_text("value = 1\n")
    (work / "docs" / "agents" / "loop.md").write_text("# Loop\n")
    git_in(work, "add", "-A")
    git_in(work, "commit", "-qm", "base")
    git_in(work, "push", "-q", "-u", "origin", "main")
    git_in(work, "remote", "set-head", "origin", "main")
    tools = tmp_path / "tools"
    tools.mkdir()
    (tools / "selector.py").write_text(SELECTOR)
    (tools / "mise").write_text(MISE)
    (tools / "mise").chmod((tools / "mise").stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", f"{tools}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.delenv("GATE_BASE", raising=False)
    monkeypatch.setenv(approvals.WORKING_TREE_POLICY, "1")
    monkeypatch.chdir(work)
    log = tools / "ran.log"
    selector = f"{sys.executable} {tools / 'selector.py'}"

    def loop(text: str) -> None:
        body = text.replace("SELECTOR", selector)
        if "## Settings" not in body:  # project() reads a policy block, empty or not
            body += "\n## Settings\n\n```yaml\n```\n"
        for branch in ("main", "work"):
            git_in(work, "checkout", "-q", branch)
            (work / "docs" / "agents" / "loop.md").write_text(body)
            git_in(work, "commit", "-q", "--allow-empty", "-am", "loop.md")
        git_in(work, "push", "-q", "origin", "main")
        log.unlink(missing_ok=True)

    git_in(work, "checkout", "-q", "-b", "work")
    (work / "app.py").write_text("value = 2\n")
    git_in(work, "commit", "-qam", "change")
    return {
        "work": work,
        "loop": loop,
        "ran": lambda: log.read_text().splitlines() if log.exists() else [],
        "base": lambda: git_in(work, "rev-parse", "origin/main").strip(),
        "head": lambda: git_in(work, "rev-parse", "HEAD").strip(),
    }


def pull(repo: dict[str, Any]) -> dict[str, Any]:
    return {"number": 7, "headRefOid": repo["head"](), "baseRefName": "main"}


# --- affected-tests: an explicit base, an unresolvable one, the opt-out ---


def test_an_explicit_base_overrides_the_merge_base(repo: dict[str, Any]) -> None:
    repo["loop"]("# Loop\n\nAffected tests: SELECTOR\n")
    first = git_in(repo["work"], "rev-parse", "HEAD~2").strip()  # before loop.md and the change
    assert approvals.main(["affected-tests", "--base", first]) == 0
    assert repo["ran"]() == [f"selected app.py docs/agents/loop.md against {first}"]


def test_a_base_git_cannot_resolve_runs_the_full_check_and_says_so(
    repo: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    repo["loop"]("# Loop\n\nAffected tests: SELECTOR\n")
    assert approvals.main(["affected-tests", "--base", "0" * 40]) == 0
    assert repo["ran"]() == ["mise run check base=unset"]
    assert (
        f"the base {'0' * 40} is no commit here: running the full check" in capsys.readouterr().err
    )


def test_without_the_line_no_base_is_resolved(
    repo: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    repo["loop"]("# Loop\n")
    assert approvals.main(["affected-tests", "--base", "0" * 40]) == 0
    assert repo["ran"]() == ["mise run check base=unset"]
    assert "is no commit here" not in capsys.readouterr().err


def test_the_opt_out_runs_the_full_check(repo: dict[str, Any]) -> None:
    repo["loop"]("# Loop\n\nAffected tests: SELECTOR\n\nGate: full\n")
    assert approvals.main(["affected-tests", "--base", repo["base"]()]) == 0
    assert repo["ran"]() == ["mise run check base=unset"]


# --- the narrowed gate's command, key and description ---


def test_a_narrowed_gate_is_keyed_by_command_and_base_and_never_equals_a_full_one(
    repo: dict[str, Any],
) -> None:
    repo["loop"]("# Loop\n\nAffected tests: mise run check-fast\n")
    full = approvals.gate()[0]
    base = repo["base"]()
    with approvals.narrowed_to(base):
        command, words, sets = approvals.gate()
        other = approvals.narrowed_gate()
    with approvals.narrowed_to("c" * 40):
        moved = approvals.gate()[0]
    assert (words, sets) == (["mise", "run", "check-fast"], {"GATE_BASE": base})
    assert command == f"GATE_BASE={base} mise run check-fast (narrowed)" and other is not None
    assert len({full, command, moved}) == 3
    assert approvals.narrowed_base(command) == base and approvals.narrowed_base(full) is None
    tree, commit = "e" * 40, "f" * 40
    said = approvals.described(tree, commit, command)
    assert said == f"Tree {tree} on {commit[:12]}: narrowed vs {base[:12]}: mise run check-fast"
    long = f"GATE_BASE={base} mise run {'x' * 120} (narrowed)"
    assert approvals.described(tree, commit, long).endswith(
        f"narrowed vs {base[:12]}, sha256 {approvals.gate_key(long)}"
    )


def test_no_gate_command_can_take_the_narrowed_form(repo: dict[str, Any]) -> None:
    """command_line refuses `(`, and quotes a quoted one, so a full gate's command never ends in ` (narrowed)`."""
    with pytest.raises(approvals.Refused):
        approvals.command_line("mise run check (narrowed)", "gate")
    assert not approvals.command_line("mise run check '(narrowed)'", "gate")[0].endswith(
        approvals.NARROWED
    )


@pytest.mark.parametrize(
    "text",
    ["# Loop\n", "# Loop\n\nAffected tests: SELECTOR\n\nGate: full\n"],
    ids=["no line", "opt-out"],
)
def test_without_the_line_or_with_the_opt_out_every_gate_is_full(
    repo: dict[str, Any], text: str
) -> None:
    repo["loop"](text)
    with approvals.narrowed_to(repo["base"]()):
        assert approvals.narrowed_gate() is None
        assert approvals.gate()[0] == "mise run check:all"


def test_gate_steps_keep_their_steps_under_a_narrowed_base(repo: dict[str, Any]) -> None:
    repo["loop"](
        "# Loop\n\nAffected tests: SELECTOR\n\n## Settings\n\n```yaml\nloop:\n  gate_steps:\n"
        "    - name: unit\n      command: mise run unit\n      where: any\n```\n"
    )
    with approvals.narrowed_to(repo["base"]()):
        assert [step["command"] for step in approvals.gate_plan()] == ["mise run unit"]
        assert approvals.narrowed_gate() is None
        assert approvals.gate()[0] == "unit: mise run unit"


# --- land's batch gate ---


def test_lands_batch_gate_runs_the_selector_against_the_base_tip(repo: dict[str, Any]) -> None:
    repo["loop"]("# Loop\n\nAffected tests: SELECTOR\n")
    tip = repo["base"]()
    with approvals.narrowed_to(tip):
        tree, how = approvals.gate_batch(repo["work"], [])
        record = approvals.reusable(repo["head"]())
    assert how == "run"
    assert repo["ran"]() == [f"selected app.py against {tip}"]
    assert record is not None and record["env"] == {"GATE_BASE": tip}
    assert record["command"].endswith(approvals.NARROWED) and record["tree"] == tree
    # the full gate finds no pass on the same tree
    assert approvals.reusable(repo["head"]()) is None


def test_land_sets_its_base_tip_for_the_batch(monkeypatch: pytest.MonkeyPatch) -> None:
    """`land` gates each batch under narrowed_to the tip it merges onto: the narrowed base merge_batch sees."""
    import inspect

    source = inspect.getsource(approvals.local_queue)
    assert source.count("with narrowed_to(tip):") == 2


def test_the_cloud_gate_task_passes_the_base_tip(
    repo: dict[str, Any], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repo["loop"]("# Loop\n\nAffected tests: SELECTOR\n")
    script = tmp_path / "omnigent_agent.py"
    script.write_text("")
    monkeypatch.setattr(approvals, "agent_script", lambda: script)
    monkeypatch.setattr(approvals, "gate_session", lambda: {"session": "s1"})
    told: list[str] = []
    monkeypatch.setattr(
        approvals,
        "run_agent",
        lambda *args, **_: told.append(args[2]) or type("Done", (), {"returncode": 0})(),
    )
    tip = repo["base"]()
    with approvals.narrowed_to(tip):
        assert approvals.ask_cloud_gate("e" * 40) == ""
    assert f"local-ci --record --base {tip}`" in told[0]


# --- ci: false: the narrowed record, check merge and local-ci --status ---


def test_a_ci_false_record_is_narrowed_and_check_merge_takes_it(
    repo: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    repo["loop"](f"# Loop\n\nAffected tests: SELECTOR\n\n{NO_CI}")
    base = git_in(repo["work"], "merge-base", "origin/main", "HEAD").strip()
    assert approvals.main(["local-ci", "--record"]) == 0
    assert repo["ran"]() == [f"selected app.py docs/agents/loop.md against {base}"]
    loop = approvals.project()[1]
    assert approvals.ran(pull(repo), loop) == []
    # never a full pass: the full gate finds none on the head
    assert approvals.reusable(repo["head"]()) is None
    # the files a detached run leaves (detach): its exit and the commands it had to pass
    head = repo["head"]()
    _, _, exit_file = approvals.run_files(head)
    exit_file.write_text("0")
    with approvals.narrowed_to(base):
        approvals.ran_command_file(head).write_text(approvals.gate()[0])
    capsys.readouterr()
    assert approvals.main(["local-ci", "--status", head]) == 0
    assert f"narrowed against {base}" in capsys.readouterr().out


def test_with_the_opt_out_check_merge_refuses_a_narrowed_record(repo: dict[str, Any]) -> None:
    repo["loop"](f"# Loop\n\nAffected tests: SELECTOR\n\n{NO_CI}")
    assert approvals.main(["local-ci", "--record"]) == 0
    # the policy is read from the working tree: the head and its tree stay the ones the narrowed pass ran on
    (repo["work"] / "docs" / "agents" / "loop.md").write_text(
        f"# Loop\n\nAffected tests: x\n\nGate: full\n\n{NO_CI}"
    )
    loop = approvals.project()[1]
    [line] = approvals.ran(pull(repo), loop)
    assert "no local check passed on the head" in line
    assert approvals.narrowed_pass(pull(repo), []) is None


def test_with_the_opt_out_a_ci_false_record_runs_the_full_gate(repo: dict[str, Any]) -> None:
    repo["loop"](f"# Loop\n\nAffected tests: SELECTOR\n\nGate: full\n\n{NO_CI}")
    assert approvals.main(["local-ci", "--record"]) == 0
    assert repo["ran"]() == ["mise run check:all base=unset"]
    assert approvals.ran(pull(repo), approvals.project()[1]) == []


def test_with_ci_a_record_without_base_stays_full(repo: dict[str, Any]) -> None:
    repo["loop"]("# Loop\n\nAffected tests: SELECTOR\n")
    assert approvals.main(["local-ci", "--record"]) == 0
    assert repo["ran"]() == ["mise run check:all base=unset"]
    assert approvals.main(["local-ci", "--record", "--base", repo["base"]()]) == 0
    assert repo["ran"]()[-1] == f"selected app.py against {repo['base']()}"


# --- check build's line ---


@pytest.mark.parametrize(
    ("text", "said"),
    [
        ("# Loop\n", True),
        ("# Loop\n\nAffected tests: SELECTOR\n", False),
        ("# Loop\n\nGate: full\n", False),
    ],
    ids=["no line", "selector", "opt-out"],
)
def test_check_build_says_when_every_gate_runs_the_full_check(
    repo: dict[str, Any], capsys: pytest.CaptureFixture[str], text: str, said: bool
) -> None:
    repo["loop"](text)
    approvals.full_check_line()
    line = "loop.md has no `Affected tests:` line, so every gate runs the full check"
    assert (line in capsys.readouterr().err) is said


def test_local_ci_for_a_ci_false_pr_posts_its_narrowed_pass(
    repo: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    repo["loop"](f"# Loop\n\nAffected tests: SELECTOR\n\n{NO_CI}")
    head = repo["head"]()
    monkeypatch.setattr(approvals, "settled_head", lambda pr, want: head)
    monkeypatch.setattr(approvals, "pull_status", lambda pr: {"baseRefName": "main"})
    monkeypatch.setattr(approvals, "base_branch", lambda pr: "main")
    posted: list[str] = []
    monkeypatch.setattr(approvals, "comment", lambda pr, body: posted.append(body))
    assert approvals.main(["local-ci", "7", "--run"]) == 0
    assert len(repo["ran"]()) == 1 and repo["ran"]()[0].startswith("selected app.py")
    assert "(narrowed)" in posted[0]
    assert approvals.reusable(head) is None  # never a full pass
