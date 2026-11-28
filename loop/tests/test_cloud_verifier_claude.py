"""scripts/cloud_verifier.py verify --harness claude: a Claude verifier pass in the worker's VM runs `claude -p` on the
brief in the same checkout, keeps what it prints as the final message, and reports, posts and returns the checkout on
the Codex pass's own code path; `--effort` is refused before anything is touched (#1186)."""

from __future__ import annotations

import json
import os
import sys

import pytest
from test_cloud_verifier import checkout, cv, git  # noqa: F401 - `checkout` is a fixture

FAKE = """#!{python}
import json, os, pathlib, subprocess, sys
rec = pathlib.Path(os.environ["FAKE_CLAUDE_DIR"])
brief = sys.stdin.read()
(rec / "call.json").write_text(json.dumps({{
    "argv": sys.argv[1:], "stdin": brief, "seeded": "CODEX_AUTH_JSON" in os.environ,
    "head": subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip(),
}}))
do = (rec / "do").read_text() if (rec / "do").exists() else ""
print("a warning on stderr", file=sys.stderr)
if do == "report":
    pathlib.Path("tmp/loop").mkdir(parents=True, exist_ok=True)
    pathlib.Path("tmp/loop/pr7-v1.md").write_text("# Report\\nVERDICT: 0 blocker\\nSATISFIED: yes\\n")
    print("Report written to tmp/loop/pr7-v1.md")
elif do == "fail":
    print("SATISFIED: yes")
    sys.exit(1)
else:
    print("# Report\\nSATISFIED: yes, from the final message")
"""


@pytest.fixture
def claude(checkout, tmp_path, monkeypatch):  # noqa: F811 - the imported fixture, used by name
    """The `checkout` fixture with a fake `claude` first on PATH that records its argv, stdin and environment."""
    bin_dir, rec = tmp_path / "bin", tmp_path / "rec"
    bin_dir.mkdir(), rec.mkdir()
    (bin_dir / "claude").write_text(FAKE.format(python=sys.executable))
    (bin_dir / "claude").chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ['PATH']}")
    monkeypatch.setenv("FAKE_CLAUDE_DIR", str(rec))
    monkeypatch.setenv("CODEX_AUTH_JSON", "c2VlZGVkLWxvZ2luLWZvci10ZXN0cw==")

    def no_codex() -> None:
        raise AssertionError("ensure_codex ran on a Claude pass")

    monkeypatch.setattr(cv, "ensure_codex", no_codex)

    def call() -> dict:
        path = rec / "call.json"
        return json.loads(path.read_text()) if path.exists() else {}

    return (*checkout, rec, call)


def test_a_claude_pass_posts_the_report_file_returns_the_checkout_and_passes_the_model(
    claude, capsys
) -> None:
    work, head, brief, posted, seen, rec, call = claude
    (rec / "do").write_text("report")
    assert cv.verify(7, brief, "claude-sonnet-5-5", None, "claude") == 0
    got = call()
    assert got["argv"] == [
        "-p",
        "--permission-mode",
        "bypassPermissions",
        "--output-format",
        "text",
        "--model",
        "claude-sonnet-5-5",
    ]
    assert got["stdin"] == "AGENT_SIGNATURE=cc/sonnet-5.5/?\n" + brief.read_text()
    assert got["head"] == head  # it ran in the checkout, at the PR's head
    assert got["seeded"] is False  # the seeded Codex login stays out of the verifier's environment
    assert "cmd" not in seen  # Codex never ran
    assert posted == [cv.folded_report("# Report\nVERDICT: 0 blocker\nSATISFIED: yes\n")]
    out = capsys.readouterr()
    assert out.out.strip().endswith("https://example.com/comment/1")
    assert "a warning on stderr" in out.err
    assert git(work, "symbolic-ref", "--short", "HEAD") == "claude/worker"


def test_a_claude_pass_without_a_report_file_posts_its_final_message_and_no_model_means_none(
    claude,
) -> None:
    _, _, brief, posted, _, _, call = claude
    assert cv.verify(7, brief, None, None, "claude") == 0
    # stdout only: the stderr warning never joins the report
    assert posted == [cv.folded_report("# Report\nSATISFIED: yes, from the final message\n")]
    assert "--model" not in call()["argv"]


def test_a_claude_pass_that_exits_1_fails_and_posts_nothing(claude, capsys) -> None:
    work, _, brief, posted, _, rec, _ = claude
    (rec / "do").write_text("fail")
    assert cv.verify(7, brief, None, None, "claude") == 1
    assert posted == []
    assert "claude exit 1" in capsys.readouterr().out
    assert git(work, "symbolic-ref", "--short", "HEAD") == "claude/worker"


def test_claude_with_an_effort_exits_2_before_any_checkout(claude, monkeypatch, capsys) -> None:
    work, _, brief, posted, _, _, call = claude
    calls: list[tuple] = []
    monkeypatch.setattr(cv, "run", lambda *cmd, **kw: calls.append(cmd))
    argv = ["verify", "--pr", "7", "--brief", str(brief), "--harness", "claude", "--effort", "high"]
    assert cv.command(argv) == 2
    assert calls == [] and call() == {} and posted == []
    assert "--effort" in capsys.readouterr().err
    assert git(work, "symbolic-ref", "--short", "HEAD") == "claude/worker"


def test_verify_without_a_harness_still_runs_codex(checkout) -> None:  # noqa: F811
    _, _, brief, posted, seen = checkout
    assert cv.command(["verify", "--pr", "7", "--brief", str(brief)]) == 0
    assert seen["cmd"][:2] == ["codex", "exec"] and posted == [
        cv.folded_report("final\nSATISFIED: yes\n")
    ]
    assert seen["brief"].startswith("AGENT_SIGNATURE=codex/?/?\n")


def test_the_signature_names_a_claude_model_as_the_launcher_does() -> None:
    assert cv.signature("claude-opus-5-5", None, "claude") == "cc/opus-5.5/?"
    assert cv.signature(None, None, "claude") == "cc/?/?"
    assert cv.signature("gpt-6.1-terra", "medium") == "codex/terra-6.1/med"


def test_the_relay_keeps_stdout_only_and_still_relays_both(tmp_path, capsys) -> None:
    final = tmp_path / "final.md"
    script = "import sys; print(sys.stdin.read().upper()); print('noise', file=sys.stderr)"
    assert cv.relay_exec([sys.executable, "-c", script], "brief\n", final) == 0
    assert final.read_text() == "BRIEF\n\n"
    out = capsys.readouterr()
    assert "BRIEF" in out.out and "noise" in out.err


def test_the_codex_relay_keeps_nothing_and_merges_stderr(capsys) -> None:
    script = "import sys; print('said'); print('noise', file=sys.stderr)"
    assert cv.codex_exec([sys.executable, "-c", script], "") == 0
    assert {"said", "noise"} <= set(capsys.readouterr().out.split())
