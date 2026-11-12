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
    git(origin, "add", "."), git(origin, "commit", "-qm", "one")
    git(tmp_path, "clone", "-q", str(origin), str(work))
    git(work, "checkout", "-qb", "claude/worker")
    git(origin, "checkout", "-qb", "feat/pr")
    (origin / "a.txt").write_text("two\n")
    git(origin, "commit", "-qam", "two")
    head = git(origin, "rev-parse", "HEAD")
    posted: list[str] = []
    seen: dict = {}

    def run(*cmd: str, check: bool = True, **kw):
        if cmd[:2] == ("gh", "api") and "/pulls/" in cmd[2]:
            return subprocess.CompletedProcess(
                cmd, 0, json.dumps({"head": {"sha": head, "ref": "feat/pr"}}), ""
            )
        if cmd[:2] == ("gh", "api"):
            posted.append(next(a for a in cmd if a.startswith("body="))[5:])
            return subprocess.CompletedProcess(cmd, 0, "https://example.com/comment/1\n", "")
        return real_run(*cmd, check=check, **kw)

    def codex(cmd: list[str], brief: str) -> int:
        seen.update(cmd=cmd, brief=brief, head=git(work, "rev-parse", "HEAD"))
        Path(cmd[cmd.index("-o") + 1]).write_text(seen.get("final", "final\nSATISFIED: yes\n"))
        (work / "tmp/loop").mkdir(parents=True, exist_ok=True)
        for key, name in (("report", "pr7-v1.md"), ("question", "pr7-v1.md.question")):
            if key in seen:
                (work / "tmp/loop" / name).write_text(seen[key])
        if "edit" in seen:
            (work / "a.txt").write_text(seen["edit"])
            (work / "stray.txt").write_text("untracked\n")
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


def test_what_the_verifier_left_in_the_tree_is_dropped_and_the_checkout_returns(
    checkout, capsys
) -> None:
    work, _, brief, posted, seen = checkout
    seen.update(edit="the verifier's leftover\n", report="# Report\nSATISFIED: no\n")
    assert cv.verify(7, brief, None, None) == 0
    assert posted == [seen["report"]]  # the report's folder is kept, so the report still counts
    err = capsys.readouterr().err
    assert "a.txt" in err and "stray.txt" in err
    assert not (work / "stray.txt").exists()
    assert git(work, "symbolic-ref", "--short", "HEAD") == "claude/worker"
    assert git(work, "status", "--porcelain", "--untracked-files=no") == ""
    assert (work / "a.txt").read_text() == "one\n"


def test_an_untracked_file_outside_the_report_folder_is_refused(checkout) -> None:
    work, _, brief, posted, seen = checkout
    (work / "conftest.py").write_text("# never pushed\n")
    with pytest.raises(cv.Refused, match="conftest.py"):
        cv.verify(7, brief, None, None)
    assert "cmd" not in seen and posted == []


def test_a_leftover_named_like_a_git_pattern_takes_nothing_else_with_it(checkout) -> None:
    work, _, brief, posted, seen = checkout
    (work / "tmp/loop").mkdir(parents=True)
    (work / "tmp/loop/proof.log").write_text("from before the pass\n")
    seen.update(report="# Report\nSATISFIED: yes\n")
    seen["do"] = lambda: (work / ":(glob)**").write_text("a valid file name\n")
    assert cv.verify(7, brief, None, None) == 0
    assert posted == [seen["report"]]
    assert (work / "tmp/loop/proof.log").exists() and not (work / ":(glob)**").exists()
    assert (work / "a.txt").read_text() == "one\n"


def test_an_ignored_file_the_verifier_staged_is_unstaged_not_deleted(checkout) -> None:
    work, _, brief, posted, seen = checkout
    (work / ".git/info/exclude").write_text("private.txt\n")
    (work / "private.txt").write_text("the worker's own\n")
    seen["do"] = lambda: git(work, "add", "-f", "private.txt")
    assert cv.verify(7, brief, None, None) == 0
    assert posted == ["final\nSATISFIED: yes\n"]
    assert (work / "private.txt").read_text() == "the worker's own\n"
    assert git(work, "status", "--porcelain") == ""
    assert git(work, "symbolic-ref", "--short", "HEAD") == "claude/worker"
