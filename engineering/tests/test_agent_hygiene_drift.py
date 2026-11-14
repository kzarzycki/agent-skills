"""agent-hygiene: a doctor finding in a clean checkout that is only behind is cleared by a pull; the rest go to the
repo's manager (#991). Names are fake."""

from __future__ import annotations

import contextlib
import importlib.machinery
import importlib.util
import io
import os
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "skills/agent-hygiene/scripts/agent-hygiene"
MANAGED = {"acme/managed"}


def load(name):
    loader = importlib.machinery.SourceFileLoader(name, str(SCRIPT))
    module = importlib.util.module_from_spec(importlib.util.spec_from_loader(name, loader))
    saved, sys.dont_write_bytecode = sys.dont_write_bytecode, True
    try:
        loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = saved
    return module


def world(tmp_path, monkeypatch, repos):
    """Clones of fake repos under dev/, each one commit behind its origin; a doctor that reports a stale copy in each
    clone until the clone holds the file `fixed`. Returns (clones, origin heads, run, calls)."""
    home = tmp_path.resolve()
    dev, bin_ = home / "dev", home / "fakebin"
    bin_.mkdir()
    dev.mkdir()
    for name in ("lsof", "ps"):
        (bin_ / name).write_text("#!/bin/sh\ntrue\n")
        (bin_ / name).chmod(0o755)
    (home / ".gitconfig").write_text("[user]\nname = t\nemail = t@t\n")
    env = {
        **os.environ,
        "HOME": str(home),
        "GIT_CONFIG_GLOBAL": str(home / ".gitconfig"),
        "PATH": f"{bin_}:{os.environ['PATH']}",
    }
    git = lambda cwd, *a: subprocess.run(
        ["git", "-C", str(cwd), *a], env=env, check=True, text=True, capture_output=True
    ).stdout.strip()
    clones, heads = {}, {}
    for repo in repos:
        origin = home / f"{repo.replace('/', '-')}.git"
        git(home, "init", "-q", "--bare", "-b", "main", str(origin))
        with open(home / ".gitconfig", "a") as config:
            config.write(f'[url "{origin}"]\n\tinsteadOf = https://github.com/{repo}.git\n')
        clone = dev / repo.split("/")[1]
        git(home, "clone", "-q", f"https://github.com/{repo}.git", str(clone))
        (clone / "base").write_text("1")
        git(clone, "add", ".")
        git(clone, "commit", "-q", "-m", "base")
        git(clone, "push", "-q", "origin", "main")
        git(clone, "remote", "set-head", "origin", "main")  # cloned empty: no origin/HEAD yet
        other = home / f"other-{repo.split('/')[1]}"
        git(home, "clone", "-q", f"https://github.com/{repo}.git", str(other))
        (other / "fixed").write_text("1")
        git(other, "add", ".")
        git(other, "commit", "-q", "-m", "fix")
        git(other, "push", "-q", "origin", "main")
        clones[repo], heads[repo] = clone, git(other, "rev-parse", "HEAD")
    doctor = home / "doctor/dotagents"
    doctor.parent.mkdir()
    lines = "\n".join(
        f'[ -e {c}/fixed ] || echo "stale skill copy: {c}/skills/x"' for c in clones.values()
    )
    doctor.write_text(
        f"#!/bin/sh\n{lines}\n[ -e {next(iter(clones.values()))}/fixed ] && [ -e {list(clones.values())[-1]}/fixed ] && exit 0\nexit 1\n"
    )
    doctor.chmod(0o755)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    hygiene = load("agent_hygiene_drift")
    hygiene.REPO, hygiene.DOTAGENTS, hygiene.CACHES = home / "no-checkout", doctor, []
    calls = []

    def tell(text, repo=None):
        calls.append((repo, text))
        return "pm-session" if repo in MANAGED else "cos-session"

    hygiene.tell = tell

    def run(*args):
        monkeypatch.setattr(
            sys, "argv", ["agent-hygiene", "--dev", str(dev), "--floor-gb", "0", *args]
        )
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            hygiene.main()
        return out.getvalue()

    run.hygiene = hygiene
    return clones, heads, run, calls, git


def test_a_clean_clone_that_is_only_behind_is_pulled_and_its_finding_is_not_sent(
    tmp_path, monkeypatch
):
    clones, heads, run, calls, git = world(tmp_path, monkeypatch, ["acme/managed"])
    out = run()
    clone = clones["acme/managed"]
    assert git(clone, "rev-parse", "HEAD") == heads["acme/managed"], (
        out,
        git(clone, "status", "-sb"),
    )
    assert f"pulled {clone}" in out and "CLEARED: stale skill copy" in out, out
    assert "DRIFT:" not in out and calls == [], (out, calls)


def test_a_dirty_clone_is_not_pulled_and_its_finding_is_routed(tmp_path, monkeypatch):
    clones, _heads, run, calls, git = world(tmp_path, monkeypatch, ["acme/managed"])
    clone = clones["acme/managed"]
    (clone / "base").write_text("changed")
    before = git(clone, "rev-parse", "HEAD")
    out = run()
    assert git(clone, "rev-parse", "HEAD") == before and "pulled" not in out, out
    assert [repo for repo, _ in calls] == ["acme/managed"] and "stale skill copy" in calls[0][1], (
        calls
    )


def test_a_diverged_or_other_branch_clone_is_not_pulled(tmp_path, monkeypatch):
    clones, _heads, run, calls, git = world(tmp_path, monkeypatch, ["acme/managed", "acme/bare"])
    git(clones["acme/managed"], "commit", "-q", "--allow-empty", "-m", "local")
    git(clones["acme/bare"], "checkout", "-q", "-b", "topic", "--track", "origin/main")
    moved = {r: git(c, "rev-parse", "HEAD") for r, c in clones.items()}
    out = run()
    assert {r: git(c, "rev-parse", "HEAD") for r, c in clones.items()} == moved, out
    assert "pulled" not in out and "git pull" not in out, out  # not even tried
    assert len(calls) == 2, calls


def test_a_clone_whose_upstream_is_another_branch_gets_the_default_branch_not_that_branch(tmp_path, monkeypatch):
    clones, heads, run, _calls, git = world(tmp_path, monkeypatch, ["acme/managed"])
    clone = clones["acme/managed"]
    git(clone, "branch", "side", "main")
    git(clone, "worktree", "add", "-q", str(tmp_path / "wt"), "side")
    git(tmp_path / "wt", "commit", "-q", "--allow-empty", "-m", "side work")
    git(tmp_path / "wt", "push", "-q", "origin", "side")
    git(clone, "branch", "--set-upstream-to=origin/side", "main")
    out = run()
    assert git(clone, "rev-parse", "HEAD") == heads["acme/managed"], out


def test_a_finding_goes_to_its_repos_manager_and_one_in_a_repo_without_goes_to_the_chief_of_staff(
    tmp_path, monkeypatch
):
    clones, _heads, run, calls, _git = world(tmp_path, monkeypatch, ["acme/managed", "acme/bare"])
    for clone in clones.values():
        (clone / "base").write_text("changed")
    out = run()
    told = {repo: text for repo, text in calls}
    assert set(told) == {"acme/managed", "acme/bare"}, calls
    assert (
        str(clones["acme/managed"]) in told["acme/managed"]
        and str(clones["acme/bare"]) not in told["acme/managed"]
    )
    assert "told the manager of acme/managed (session pm-session)" in out, out
    assert "told the manager of acme/bare (session cos-session)" in out, (
        out
    )  # tell() falls back to the chief of staff itself
    run()
    assert len(calls) == 2, "each finding is told once"


def test_a_clone_that_is_not_behind_is_not_pulled(tmp_path, monkeypatch):
    clones, _heads, run, calls, git = world(tmp_path, monkeypatch, ["acme/managed"])
    git(clones["acme/managed"], "pull", "-q", "--ff-only")
    run.hygiene.DOTAGENTS.write_text(
        f'#!/bin/sh\necho "stale skill copy: {clones["acme/managed"]}/skills/x"\nexit 1\n'
    )
    out = run()
    assert "pulled" not in out and "git pull" not in out, out
    assert [repo for repo, _ in calls] == ["acme/managed"], (
        calls
    )  # the finding stays, and is routed


def test_a_finding_whose_manager_cannot_be_told_goes_to_the_chief_of_staff(tmp_path, monkeypatch):
    clones, _heads, run, _calls, _git = world(tmp_path, monkeypatch, ["acme/managed"])
    (clones["acme/managed"] / "base").write_text("changed")
    sent = []

    def tell(text, repo=None):
        sent.append(repo)
        if repo:
            raise RuntimeError("down")
        return "cos-session"

    run.hygiene.tell = tell
    out = run()
    assert sent == ["acme/managed", None], (sent, out)
