"""scripts/cloud_verifier.py: the copy a VM gets holds no refresh token, a seed refreshes only a login that is running
out, and a verifier pass runs on the PR's pushed head, posts its report byte for byte and puts the checkout back."""

from __future__ import annotations

import base64
import importlib.util
import json
import subprocess
import time
from pathlib import Path

import pytest

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "skills"
    / "engineering-loop"
    / "scripts"
    / "cloud_verifier.py"
)
SPEC = importlib.util.spec_from_file_location("cloud_verifier", SCRIPT)
assert SPEC and SPEC.loader
cv = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cv)


def jwt(expires_in_days: float) -> str:
    claims = base64.urlsafe_b64encode(
        json.dumps({"exp": time.time() + expires_in_days * 86400}).encode()
    )
    return f"h.{claims.decode().rstrip('=')}.s"


def login(days: float) -> dict:
    return {
        "OPENAI_API_KEY": None,
        "tokens": {
            "id_token": "id",
            "access_token": jwt(days),
            "refresh_token": "secret",
            "account_id": "acc",
        },
        "last_refresh": "2026-01-01T00:00:00Z",
    }


def test_the_vm_copy_keeps_the_tokens_but_not_the_refresh_token() -> None:
    auth = login(9)
    copy = cv.reader_copy(auth)
    assert copy["tokens"] == {**auth["tokens"], "refresh_token": ""}
    assert auth["tokens"]["refresh_token"] == "secret"  # the seed's own login is untouched


def test_expiry_is_read_from_the_token() -> None:
    assert abs(cv.expires_at(jwt(3)) - (time.time() + 3 * 86400)) < 5


@pytest.fixture
def seeded(tmp_path, monkeypatch):
    """A seed home, and the calls `seed` makes to the two services, recorded."""
    calls: list[tuple[str, dict | None]] = []
    environment = {
        "name": "dev",
        "description": "d",
        "config": {
            "environment": {"KEEP": "1"},
            "network_config": {"allowed_hosts": ["example.com"]},
        },
    }

    def post_json(url: str, body: dict | None, headers: dict) -> dict:
        calls.append((url, body))
        if url == cv.REFRESH_URL:
            return {"access_token": jwt(10), "refresh_token": "rotated", "id_token": "id2"}
        return json.loads(json.dumps(environment))

    monkeypatch.setenv("CODEX_CLOUD_HOME", str(tmp_path))
    monkeypatch.setattr(cv, "post_json", post_json)
    monkeypatch.setattr(cv, "claude_headers", dict)
    return tmp_path / "auth.json", calls


def stored(calls: list) -> tuple[dict, dict]:
    """The config `seed` posted to the environment, and the login inside its variable."""
    config = calls[-1][1]["config"]
    return config, json.loads(base64.b64decode(config["environment"][cv.VAR]))


def test_seed_stores_a_fresh_login_without_refreshing_it(seeded) -> None:
    path, calls = seeded
    path.write_text(json.dumps(login(9)))
    assert cv.seed("env_1", min_days=5) == 0
    assert cv.REFRESH_URL not in [url for url, _ in calls]
    config, copy = stored(calls)
    assert copy["tokens"]["refresh_token"] == "" and copy["tokens"]["account_id"] == "acc"
    assert config["environment"]["KEEP"] == "1"  # the environment's other variables stay
    assert set(config["network_config"]["allowed_hosts"]) == {"example.com", *cv.HOSTS}
    assert json.loads(path.read_text())["tokens"]["refresh_token"] == "secret"


def test_seed_refreshes_a_login_that_is_running_out_and_keeps_the_new_refresh_token(seeded) -> None:
    path, calls = seeded
    path.write_text(json.dumps(login(2)))
    assert cv.seed("env_1", min_days=5) == 0
    assert calls[0] == (
        cv.REFRESH_URL,
        {"client_id": cv.CLIENT_ID, "grant_type": "refresh_token", "refresh_token": "secret"},
    )
    kept = json.loads(path.read_text())
    assert kept["tokens"]["refresh_token"] == "rotated" and kept["tokens"]["account_id"] == "acc"
    assert kept["last_refresh"] != "2026-01-01T00:00:00Z"
    _, copy = stored(calls)
    assert copy["tokens"]["access_token"] == kept["tokens"]["access_token"]
    assert copy["tokens"]["refresh_token"] == ""


def test_seed_without_a_login_says_to_log_in(seeded, capsys) -> None:
    assert cv.main(["seed", "--env", "env_1"]) == 2
    assert "cloud_verifier.py login" in capsys.readouterr().err


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture
def checkout(tmp_path, monkeypatch):
    """A clone on a worker's branch whose PR head is one commit ahead on the remote, with `gh` and `codex` stubbed."""
    origin, work = tmp_path / "origin", tmp_path / "work"
    git(tmp_path, "init", "-q", "-b", "main", str(origin))
    for key, value in (("user.email", "t@example.com"), ("user.name", "t")):
        git(origin, "config", key, value)
    (origin / "a.txt").write_text("one\n")
    (origin / "old.txt").write_text("only on the worker's branch\n")
    (origin / ".gitignore").write_text("local.txt\n")  # a rule the PR's head drops
    git(origin, "add", "."), git(origin, "commit", "-qm", "one")
    git(tmp_path, "clone", "-q", str(origin), str(work))
    git(work, "checkout", "-qb", "claude/worker")
    git(origin, "checkout", "-qb", "feat/pr")
    (origin / "a.txt").write_text("two\n")
    (origin / "new.txt").write_text("only on the PR's head\n")
    git(origin, "rm", "-q", "old.txt", ".gitignore"), git(origin, "add", ".")
    git(origin, "commit", "-qm", "two")
    head = git(origin, "rev-parse", "HEAD")
    posted: list[str] = []
    seen: dict = {}

    def run(*cmd: str, check: bool = True, **kw):
        if cmd[:2] == ("gh", "api") and "/pulls/" in cmd[2]:
            return subprocess.CompletedProcess(
                cmd, 0, json.dumps({"head": {"sha": head, "ref": "feat/pr"}}), ""
            )
        if cmd[:2] == ("gh", "api") and seen.get("post fails"):
            raise cv.Refused("`gh api` exited 1: HTTP 502")
        if cmd[:2] == ("git", "checkout") and "--detach" in cmd and "half" in seen:
            (work / "a.txt").write_text(seen["half"])
            return subprocess.CompletedProcess(cmd, 1, "", "error: external filter failed")
        if cmd[:2] == ("gh", "api"):
            assert "body=@-" in cmd  # the body goes in through stdin
            posted.append(kw["input"])
            return subprocess.CompletedProcess(cmd, 0, "https://example.com/comment/1\n", "")
        return real_run(*cmd, check=check, **kw)

    def codex(cmd: list[str], brief: str) -> int:
        seen.update(cmd=cmd, brief=brief, head=git(work, "rev-parse", "HEAD"))
        Path(cmd[cmd.index("-o") + 1]).write_text(seen.get("final", "final\nSATISFIED: yes\n"))
        (work / "tmp/loop").mkdir(parents=True, exist_ok=True)
        for key, name in (("report", "pr7-v1.md"), ("question", "pr7-v1.md.question")):
            if key in seen:
                (work / "tmp/loop" / name).write_text(seen[key])
        if "do" in seen:
            seen["do"]()
        return seen.get("exit", 0)

    real_run = cv.run
    monkeypatch.chdir(work)
    monkeypatch.setattr(cv, "run", run)
    monkeypatch.setattr(cv, "ensure_codex", lambda: None)
    monkeypatch.setattr(cv, "codex_exec", codex)
    brief = tmp_path / "brief.md"
    brief.write_text("Review PR #7.\n- Report: tmp/loop/pr7-v1.md\n")
    return work, head, brief, posted, seen


def test_a_pass_runs_on_the_pr_head_posts_the_report_file_and_returns_the_checkout(
    checkout, capsys
) -> None:
    work, head, brief, posted, seen = checkout
    (work / "tmp/loop").mkdir(parents=True)
    (work / "tmp/loop/proof.log").write_text(
        "untracked, as in a fresh clone\n"
    )  # not a reason to refuse
    seen["report"] = "# Report\n\nHead: x\nVERDICT: 0 blocker\nSATISFIED: yes\nRisk: low\n"
    assert cv.verify(7, brief, "gpt-x", "medium") == 0
    assert seen["head"] == head  # Codex ran on the PR's head, not the worker's branch
    assert seen["brief"] == "AGENT_SIGNATURE=codex/x/med\n" + brief.read_text()
    assert seen["cmd"][-5:] == ["-m", "gpt-x", "-c", "model_reasoning_effort=medium", "-"]
    assert posted == [seen["report"]]  # the file the brief names, byte for byte
    assert capsys.readouterr().out.strip().endswith("https://example.com/comment/1")
    assert git(work, "symbolic-ref", "--short", "HEAD") == "claude/worker"


def test_the_final_message_is_the_report_when_the_brief_names_no_file(checkout) -> None:
    _, _, brief, posted, seen = checkout
    brief.write_text("Review PR #7.\n")
    assert cv.verify(7, brief, None, None) == 0
    assert posted == ["final\nSATISFIED: yes\n"]
    assert (
        "-m" not in seen["cmd"] and "-c" not in seen["cmd"]
    )  # no model named: Codex's configured default


def test_a_report_without_a_satisfied_line_is_not_posted(checkout) -> None:
    work, _, brief, posted, seen = checkout
    seen["final"] = "I ran out of time.\n"
    assert cv.verify(7, brief, None, None) == 1
    assert posted == []
    assert git(work, "symbolic-ref", "--short", "HEAD") == "claude/worker"


def test_a_tree_with_uncommitted_changes_is_refused_before_codex_runs(checkout) -> None:
    work, _, brief, posted, seen = checkout
    (work / "a.txt").write_text("edited\n")
    with pytest.raises(cv.Refused, match="uncommitted"):
        cv.verify(7, brief, None, None)
    assert "cmd" not in seen and posted == []


def test_the_signature_names_the_model_and_effort_as_the_launcher_does() -> None:
    assert cv.signature("gpt-6.1-terra", "medium") == "codex/terra-6.1/med"
    assert cv.signature(None, None) == "codex/?/?"


def test_a_question_is_posted_instead_of_a_report_and_an_earlier_pass_is_not_reused(
    checkout,
) -> None:
    work, _, brief, posted, seen = checkout
    (work / "tmp/loop").mkdir(parents=True)
    (work / "tmp/loop/pr7-v1.md").write_text("an earlier pass\nSATISFIED: yes\n")
    seen.update(
        final="tmp/loop/pr7-v1.md.question\n", question="Please run the gate at this head.\n"
    )
    assert cv.verify(7, brief, None, None) == 3
    assert posted == ["## Verifier question\n\nPlease run the gate at this head.\n"]


def edit_gitignore(work: Path) -> None:
    (work / ".git/info/exclude").write_text("")  # what hid private.txt is gone


LEFTOVERS = {
    "a tracked edit and a new file": lambda work: (
        (work / "a.txt").write_text("the verifier's\n"),
        (work / "stray.txt").write_text("new\n"),
    ),
    "a file named like a git pattern": lambda work: (work / ":(glob)**").write_text("new\n"),
    "an ignored file, staged": lambda work: git(work, "add", "-f", "private.txt"),
    "an ignore rule removed": edit_gitignore,
    "a repository inside the checkout": lambda work: git(work, "init", "-q", "scratch"),
}


@pytest.mark.parametrize("leftover", LEFTOVERS)
def test_a_tree_the_verifier_changed_is_reported_and_nothing_in_it_is_deleted(
    checkout, capsys, leftover
) -> None:
    work, head, brief, posted, seen = checkout
    older = {
        "private.txt": "ignored, the worker's own\n",
        "scratch/keep.txt": "ignored, in a folder\n",
        "tmp/loop/proof.log": "from before the pass\n",
    }
    (work / ".git/info/exclude").write_text("private.txt\nscratch/keep.txt\n")
    for name, text in older.items():
        (work / name).parent.mkdir(parents=True, exist_ok=True)
        (work / name).write_text(text)
    seen.update(report="# Report\nSATISFIED: no\n", do=lambda: LEFTOVERS[leftover](work))
    assert cv.verify(7, brief, None, None) == 4
    assert posted == [seen["report"]]  # the report still counts
    assert "stays as it is" in capsys.readouterr().err
    assert {name: (work / name).read_text() for name in older} == older
    assert git(work, "rev-parse", "HEAD") == head  # where the verifier left it, for someone to look
    assert git(work, "rev-parse", "claude/worker") != head
    with pytest.raises(cv.Refused, match="uncommitted"):  # and the next pass says so
        cv.verify(7, brief, None, None)


def test_an_untracked_file_outside_the_report_folder_is_refused(checkout) -> None:
    work, _, brief, posted, seen = checkout
    (work / "conftest.py").write_text("# never pushed\n")
    with pytest.raises(cv.Refused, match="conftest.py"):
        cv.verify(7, brief, None, None)
    assert "cmd" not in seen and posted == []


def test_a_commit_by_the_verifier_never_moves_the_workers_branch(checkout) -> None:
    work, head, brief, posted, seen = checkout
    git(work, "fetch", "-q", "origin", "feat/pr")
    git(work, "reset", "-q", "--hard", head)  # the worker's branch is already at the PR's head
    seen["do"] = lambda: git(
        work,
        "-c",
        "user.email=v@example.com",
        "-c",
        "user.name=v",
        "commit",
        "-q",
        "--allow-empty",
        "-m",
        "stray",
    )
    assert cv.verify(7, brief, None, None) == 0
    assert posted == ["final\nSATISFIED: yes\n"]
    assert git(work, "symbolic-ref", "--short", "HEAD") == "claude/worker"
    assert git(work, "rev-parse", "claude/worker") == head


def test_an_ignored_file_where_the_pr_head_has_one_stops_the_pass_and_stays(checkout) -> None:
    work, _, brief, posted, seen = checkout
    (work / ".git/info/exclude").write_text("new.txt\n")
    (work / "new.txt").write_text("the worker's own\n")
    with pytest.raises(cv.Refused, match=r"new\.txt"):
        cv.verify(7, brief, None, None)
    assert (work / "new.txt").read_text() == "the worker's own\n"
    assert "cmd" not in seen and posted == []
    assert git(work, "symbolic-ref", "--short", "HEAD") == "claude/worker"


def test_an_ignored_file_in_the_way_of_the_return_stays_and_is_reported(checkout, capsys) -> None:
    work, head, brief, posted, seen = checkout
    (work / ".git/info/exclude").write_text("old.txt\n")
    seen["do"] = lambda: (work / "old.txt").write_text("the verifier's notes\n")
    assert cv.verify(7, brief, None, None) == 4
    assert posted == ["final\nSATISFIED: yes\n"]
    assert (work / "old.txt").read_text() == "the verifier's notes\n"
    assert "old.txt" in capsys.readouterr().err
    assert git(work, "rev-parse", "HEAD") == head


def test_a_failed_pass_that_left_changes_also_says_the_checkout_needs_a_look(checkout) -> None:
    work, _, brief, posted, seen = checkout
    seen.update(exit=1, do=lambda: (work / "a.txt").write_text("the verifier's\n"))
    assert cv.verify(7, brief, None, None) == 4
    assert posted == [] and (work / "a.txt").read_text() == "the verifier's\n"


def test_a_comment_that_can_not_be_posted_is_a_failed_pass_not_a_missing_precondition(
    checkout, capsys
) -> None:
    work, head, brief, posted, seen = checkout
    seen["post fails"] = True
    assert cv.main(["verify", "--pr", "7", "--brief", str(brief)]) == 1
    assert "HTTP 502" in capsys.readouterr().err and posted == []
    assert git(work, "symbolic-ref", "--short", "HEAD") == "claude/worker"
    seen["do"] = lambda: (work / "a.txt").write_text("the verifier's\n")
    assert (
        cv.main(["verify", "--pr", "7", "--brief", str(brief)]) == 4
    )  # the changed tree still shows
    assert git(work, "rev-parse", "HEAD") == head


def test_a_checkout_that_shows_changes_of_its_own_at_the_head_is_returned_and_refused(
    checkout,
) -> None:
    """A file only the worker's branch ignores is untracked at the head, where an edit to it could not be seen."""
    work, _, brief, posted, seen = checkout
    (work / "local.txt").write_text("ignored on the worker's branch only\n")
    with pytest.raises(cv.Refused, match=r"local\.txt"):
        cv.verify(7, brief, None, None)
    assert "cmd" not in seen and posted == []
    assert git(work, "symbolic-ref", "--short", "HEAD") == "claude/worker"
    assert (work / "local.txt").read_text() == "ignored on the worker's branch only\n"


def test_a_checkout_that_fails_part_way_is_reported_as_a_changed_tree(checkout, capsys) -> None:
    work, _, brief, posted, seen = checkout
    seen["half"] = "half written\n"
    assert cv.main(["verify", "--pr", "7", "--brief", str(brief)]) == 4
    assert "failed part way" in capsys.readouterr().err
    assert "cmd" not in seen and posted == []
    assert (work / "a.txt").read_text() == "half written\n"  # left for someone to look at


def test_a_report_file_the_return_checkout_writes_is_not_this_passs_report(checkout) -> None:
    work, _, brief, posted, seen = checkout
    (work / "tmp/loop").mkdir(parents=True)
    (work / "tmp/loop/pr7-v1.md").write_text("committed on the worker's branch\nSATISFIED: yes\n")
    git(work, "add", "-f", "tmp/loop/pr7-v1.md")
    git(
        work,
        "-c",
        "user.email=w@example.com",
        "-c",
        "user.name=w",
        "commit",
        "-qm",
        "a report, tracked",
    )
    seen["final"] = "I wrote no report.\n"
    assert cv.verify(7, brief, None, None) == 1
    assert posted == []
    assert git(work, "symbolic-ref", "--short", "HEAD") == "claude/worker"


def test_the_report_is_posted_with_its_line_ends_and_odd_bytes_do_not_fail_the_pass(
    checkout,
) -> None:
    work, _, brief, posted, seen = checkout
    seen["do"] = lambda: (work / "tmp/loop/pr7-v1.md").write_bytes(b"# R\r\nSATISFIED: yes\r\n\xff")
    assert cv.verify(7, brief, None, None) == 0
    assert posted == ["# R\r\nSATISFIED: yes\r\n\ufffd"]


def test_a_report_at_the_top_of_the_checkout_exempts_only_itself(checkout) -> None:
    work, *_ = checkout
    for name in ("pr7.md", "pr7.md.question", "other.md"):
        (work / name).write_text("x\n")
    assert cv.changes(Path("pr7.md")) == [("??", "other.md")]
    assert cv.changes(None) == [("??", "other.md"), ("??", "pr7.md"), ("??", "pr7.md.question")]


def test_a_change_still_showing_after_the_return_is_reported(checkout, capsys, monkeypatch) -> None:
    """A change the status at the head can't tell from the checkout's own, as inside a submodule the PR moved."""
    _, _, brief, posted, _ = checkout
    real, calls = cv.uncommitted, []

    def uncommitted(report):
        calls.append(
            real(report)
        )  # 1 the clean check, 2 the baseline, 3 after Codex, 4 back on the branch
        return calls[-1] if len(calls) < 4 else " M sub"

    monkeypatch.setattr(cv, "uncommitted", uncommitted)
    assert cv.verify(7, brief, None, None) == 4
    assert posted == ["final\nSATISFIED: yes\n"] and " M sub" in capsys.readouterr().err
