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
        "tools": tools,
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


def test_a_base_variable_written_on_the_line_never_overrides_the_narrowed_base(
    repo: dict[str, Any],
) -> None:
    repo["loop"]("# Loop\n\nAffected tests: GATE_BASE=elsewhere SELECTOR\n")
    base = repo["base"]()
    assert approvals.main(["affected-tests", "--base", base]) == 0
    assert repo["ran"]() == [f"selected app.py against {base}"]
    with approvals.narrowed_to(base):
        assert approvals.gate()[2] == {"GATE_BASE": base}


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


def batch_of(repo: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Two PR heads pushed to origin, each adding one file to `main`'s tip, as `land` reads them: candidates_of names
    them, and merges, the GitHub part, is replaced by a log of what it was given."""
    work, pulls = repo["work"], []
    for number, name in ((7, "b.py"), (8, "c.py")):
        git_in(work, "checkout", "-q", "-b", f"pr{number}", "origin/main")
        (work / name).write_text("x = 1\n")
        git_in(work, "add", name)
        git_in(work, "commit", "-qm", name)
        git_in(work, "push", "-q", "origin", f"pr{number}")
        pulls.append(
            {
                "number": number,
                "headRefOid": repo["head"](),
                "baseRefName": "main",
                "isDraft": False,
            }
        )
    git_in(work, "checkout", "-q", "work")
    monkeypatch.setattr(approvals, "candidates_of", lambda named, *_a: (named, {}, {}))
    merged: list[tuple[Any, ...]] = []
    monkeypatch.setattr(approvals, "merges", lambda *args: merged.append(args))
    repo["merged"] = merged
    return pulls


def test_land_gates_the_batch_with_the_selector_against_the_tip_it_merges_onto(
    repo: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """With a working tree: merge_batch's gate selects over the batch's combined diff against the tip."""
    repo["loop"]("# Loop\n\nAffected tests: SELECTOR\n")
    pulls = batch_of(repo, monkeypatch)
    tip = repo["base"]()
    assert approvals.local_queue(pulls, "main", None, None, set()) == (0, False)
    assert repo["ran"]() == [f"selected b.py c.py against {tip}"]
    [(landed, *_)] = repo["merged"]
    assert [pull["number"] for pull, *_ in landed] == [7, 8]
    assert {how for *_, how in landed} == {"run"}


def test_a_red_main_is_not_read_green_by_the_selector_and_nobody_is_evicted(
    repo: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A PR red twice makes `land` gate the bare base; the selector selects nothing there (no diff), so only the full
    gate can tell a main carrying breakage from an innocent PR."""
    work, tools = repo["work"], repo["tools"]
    # main's breakage: the selector fails once any change is selected (its tests reach app.py), the full check always
    (tools / "selector.py").write_text(
        SELECTOR
        + 'if changed and "BROKEN" in pathlib.Path("app.py").read_text():\n    sys.exit(1)\n'
    )
    (tools / "mise").write_text(MISE + "grep -q BROKEN app.py && exit 1\nexit 0\n")
    repo["loop"]("# Loop\n\nAffected tests: SELECTOR\n")
    git_in(work, "checkout", "-q", "main")
    (work / "app.py").write_text("value = BROKEN\n")
    git_in(work, "commit", "-qam", "breakage")
    git_in(work, "push", "-q", "origin", "main")
    git_in(work, "checkout", "-q", "work")
    pulls = batch_of(repo, monkeypatch)
    evicted: list[int] = []
    monkeypatch.setattr(approvals, "evict", lambda pull, *_a: evicted.append(pull["number"]))
    assert approvals.local_queue(pulls, "main", None, None, set())[0] != 0
    assert "main itself is red" in capsys.readouterr().out
    assert evicted == [] and repo["merged"] == []


def test_land_in_a_clone_with_no_working_tree_looks_up_the_narrowed_pass_on_the_batch_tree(
    repo: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Without one: merged_trees finds the pass recorded against the tip, and refuses, naming that command, without."""
    repo["loop"]("# Loop\n\nAffected tests: SELECTOR\n")
    pulls = batch_of(repo, monkeypatch)
    tip = repo["base"]()
    monkeypatch.setattr(approvals, "working_tree", lambda root: False)
    monkeypatch.delenv(
        approvals.WORKING_TREE_POLICY
    )  # the policy is origin's, as a clone with no files reads it
    with pytest.raises(approvals.Refused) as refused:
        approvals.local_queue(pulls, "main", None, None, set())
    assert f"`approvals.py local-ci --record --base {tip}`" in str(refused.value)
    assert repo["ran"]() == []  # no gate runs there
    # the printed command's equivalent, on a head with the batch's tree: the lookup then finds that record
    monkeypatch.setenv(approvals.WORKING_TREE_POLICY, "1")
    monkeypatch.setattr(approvals, "working_tree", lambda root: True)
    git_in(repo["work"], "checkout", "-q", "-B", "batch", "origin/main")
    for pull in pulls:
        git_in(repo["work"], "merge", "-q", "--no-ff", "--no-edit", pull["headRefOid"])
    assert approvals.main(["local-ci", "--record", "--base", tip]) == 0
    assert repo["ran"]() == [f"selected b.py c.py against {tip}"]
    git_in(repo["work"], "checkout", "-q", "work")
    monkeypatch.setattr(approvals, "working_tree", lambda root: False)
    monkeypatch.delenv(approvals.WORKING_TREE_POLICY)
    assert approvals.local_queue(pulls, "main", None, None, set()) == (0, False)
    assert repo["ran"]() == [f"selected b.py c.py against {tip}"]  # nothing ran again
    assert {how for *_, how in repo["merged"][0][0]} == {"reused"}


def test_the_full_gate_keeps_its_refusal_text(
    repo: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    repo["loop"]("# Loop\n\nAffected tests: SELECTOR\n\nGate: full\n")
    pulls = batch_of(repo, monkeypatch)
    monkeypatch.setattr(approvals, "working_tree", lambda root: False)
    monkeypatch.delenv(approvals.WORKING_TREE_POLICY)
    with pytest.raises(approvals.Refused) as refused:
        approvals.local_queue(pulls, "main", None, None, set())
    assert "(`approvals.py local-ci --record` on a head with this tree)" in str(refused.value)


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
    repo: dict[str, Any],
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    text: str,
    said: bool,
) -> None:
    repo["loop"](text)
    monkeypatch.setattr(
        approvals, "unbuilt", lambda *_a: 0
    )  # the spec check is GitHub's; the line is `check`'s
    assert approvals.main(["check", "build", "--issue", "1"]) == 0
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


def pr_ready(repo: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """`local-ci 7 --run` against a stand-in GitHub: the PR's head, base and the comments it posts."""
    head = repo["head"]()
    monkeypatch.setattr(approvals, "settled_head", lambda pr, want: head)
    monkeypatch.setattr(approvals, "pull_status", lambda pr: {"baseRefName": "main"})
    monkeypatch.setattr(approvals, "base_branch", lambda pr: "main")
    posted: list[str] = []
    monkeypatch.setattr(approvals, "comment", lambda pr, body: posted.append(body))
    return posted


def test_local_ci_for_a_pr_on_a_project_with_ci_is_not_narrowed(
    repo: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """CI runs the selector on the PR; the narrowed record is only `ci: false`'s gate of record."""
    repo["loop"]("# Loop\n\nAffected tests: SELECTOR\n")
    posted = pr_ready(repo, monkeypatch)
    assert approvals.main(["local-ci", "7", "--run"]) == 0
    assert repo["ran"]() == ["mise run check:all base=unset"]
    assert "(narrowed)" not in posted[0]


def test_under_ci_false_a_head_with_a_full_pass_takes_it_and_is_not_gated_again(
    repo: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    repo["loop"](f"# Loop\n\nAffected tests: SELECTOR\n\n{NO_CI}")
    posted = pr_ready(repo, monkeypatch)
    approvals.run_local_ci(
        None, None, []
    )  # the full gate's pass on the head, as `Gate: full` records it
    assert repo["ran"]() == ["mise run check:all base=unset"]
    assert approvals.main(["local-ci", "7", "--run"]) == 0
    assert repo["ran"]() == ["mise run check:all base=unset"]  # nothing ran again
    assert "(narrowed)" not in posted[0]


def test_local_ci_base_without_record_is_refused(
    repo: dict[str, Any], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo["loop"]("# Loop\n\nAffected tests: SELECTOR\n")
    pr_ready(repo, monkeypatch)
    assert approvals.main(["local-ci", "7", "--run", "--base", repo["base"]()]) != 0
    assert "local-ci --base goes with --record" in capsys.readouterr().out
    assert repo["ran"]() == []


# a stateful selector with no state (a fresh clone, a cloud VM, a CI runner): it logs the variables it got beyond the
# caller's and whether the checkout held any untracked or ignored file, selects every test and exits with its own result
NO_STATE = """import json, os, pathlib, subprocess, sys
caller = set(json.loads(os.environ["CALLER_ENV"]))
extra = sorted(set(os.environ) - caller)
listed = subprocess.run(["git", "status", "--porcelain", "--ignored", "--untracked-files=all"], capture_output=True, text=True, check=True).stdout
log = pathlib.Path(sys.argv[1])
log.write_text(json.dumps({"extra": extra, "listed": listed, "base": os.environ.get("GATE_BASE")}))
sys.exit(4)
"""


def test_a_selector_without_state_gets_only_the_base_and_its_own_result_stands(
    repo: dict[str, Any], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`affected-tests` and land's narrowed batch gate hand the command a clean checkout and the base variable (beside
    the host gate slot's own), nothing else the pack provides: a selector with no state selects everything and its exit
    passes through."""
    import json

    script, log = tmp_path / "no_state.py", tmp_path / "no_state.json"
    script.write_text(NO_STATE)
    repo["loop"](f"# Loop\n\nAffected tests: {sys.executable} {script} {log}\n")
    monkeypatch.setenv("CALLER_ENV", json.dumps(sorted(os.environ) + ["CALLER_ENV"]))
    pack_only = {"GATE_BASE", approvals.SLOT_HELD}
    merge_base = git_in(repo["work"], "merge-base", "origin/main", "HEAD").strip()
    assert approvals.main(["affected-tests"]) == 4
    seen = json.loads(log.read_text())
    assert set(seen["extra"]) <= pack_only and "GATE_BASE" in seen["extra"]
    assert seen["listed"] == "" and seen["base"] == merge_base
    log.unlink()
    tip = repo["base"]()
    with approvals.narrowed_to(tip):
        assert approvals.gate_batch(repo["work"], [])[1] == ""  # red: the selector's exit 4
    seen = json.loads(log.read_text())
    assert set(seen["extra"]) <= pack_only and "GATE_BASE" in seen["extra"]
    assert seen["listed"] == "" and seen["base"] == tip
