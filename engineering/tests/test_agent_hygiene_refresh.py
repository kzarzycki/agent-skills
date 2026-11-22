"""agent-hygiene brings a drifting checkout up to a landed pack bump itself when that is safe, never pulls one that runs
services, never leaves a rewritten lock, tells managers what is theirs, and installs a forwarder's missing target
(#1783). Names are fake."""

from __future__ import annotations

import os
import subprocess

from test_agent_hygiene_drift import world

LOCK = "lockfile_version: '1'\ngenerated_at: '2026-01-01T00:00:00Z'\n"


def tool(home, name, body):
    path = home / "fakebin" / name
    path.write_text(f"#!/bin/sh\n{body}\n")
    path.chmod(0o755)


def managed(tmp_path, monkeypatch, files=None):
    """One clone behind its origin, whose new commits add an APM manifest and lock (and files); a doctor that reports a
    stale copy until the clone holds `installed`; a fake apm that records its call, rewrites the lock's generated_at
    and writes `installed`."""
    clones, _heads, run, calls, git = world(tmp_path, monkeypatch, ["acme/managed"])
    home, clone = tmp_path.resolve(), clones["acme/managed"]
    other = home / "other-managed"
    for name, text in {"apm.yml": "name: x\n", "apm.lock.yaml": LOCK, **(files or {})}.items():
        (other / name).parent.mkdir(parents=True, exist_ok=True)
        (other / name).write_text(text)
    git(other, "add", ".")
    git(other, "commit", "-q", "-m", "pin")
    git(other, "push", "-q", "origin", "main")
    run.hygiene.DOTAGENTS.write_text(
        f'#!/bin/sh\n[ -e {clone}/installed ] && exit 0\necho "stale skill copy: {clone}/.claude/skills/x"\nexit 1\n'
    )
    record = f'echo "$PWD $*" >> {home}/installs\n'
    rewrite = "printf \"generated_at: 'now'\\n\" >> apm.lock.yaml\n"
    tool(home, "apm", record + rewrite + "touch installed")
    tool(home, "mise", record + rewrite + "touch installed")
    installs = lambda: (
        (home / "installs").read_text().splitlines() if (home / "installs").exists() else []
    )
    return clone, git(other, "rev-parse", "HEAD"), run, calls, git, installs


def test_a_clean_clone_behind_is_pulled_and_installed_from_its_committed_lock(
    tmp_path, monkeypatch
):
    clone, head, run, calls, git, installs = managed(tmp_path, monkeypatch)
    out = run()
    assert git(clone, "rev-parse", "HEAD") == head and f"pulled {clone}" in out, out
    assert installs() == [f"{clone} install --frozen"], out
    assert (clone / "apm.lock.yaml").read_text() == LOCK, "the rewritten lock is put back"
    assert "CLEARED: stale skill copy" in out and calls == [], (out, calls)


def test_a_repo_with_a_sync_task_installs_through_it(tmp_path, monkeypatch):
    clone, _head, run, _calls, _git, installs = managed(
        tmp_path, monkeypatch, {"mise.toml": "[tasks.agent-sync]\nrun = 'apm install'\n"}
    )
    run()
    assert installs() == [f"{clone} run agent-sync --frozen"]


def test_a_clone_a_process_has_open_is_not_pulled_but_installed(tmp_path, monkeypatch):
    clone, _head, run, calls, git, installs = managed(tmp_path, monkeypatch)
    git(
        clone, "pull", "-q", "--ff-only"
    )  # it holds the lock already; its origin moves on once more
    other = tmp_path.resolve() / "other-managed"
    (other / "later").write_text("1")
    git(other, "add", ".")
    git(other, "commit", "-q", "-m", "later")
    git(other, "push", "-q", "origin", "main")
    before = git(clone, "rev-parse", "HEAD")
    tool(tmp_path.resolve(), "lsof", f"echo p1; echo fcwd; echo n{clone}")
    out = run()
    assert git(clone, "rev-parse", "HEAD") == before and "pulled" not in out, out
    assert f"not pulling {clone}: a process has it open" in out and installs() == [
        f"{clone} install --frozen"
    ], out
    assert calls == [], calls


def test_a_clone_a_service_unit_points_at_is_not_pulled(tmp_path, monkeypatch):
    clone, _head, run, _calls, git, _installs = managed(tmp_path, monkeypatch)
    units = tmp_path.resolve() / ".config/systemd/user"
    units.mkdir(parents=True)
    (units / "app.service").write_text(
        f"[Service]\nWorkingDirectory={clone}\nExecStart={clone}/run\n"
    )
    before = git(clone, "rev-parse", "HEAD")
    out = run()
    assert git(clone, "rev-parse", "HEAD") == before, out
    assert "the service unit" in out and "app.service points at it" in out, out


def test_a_failed_install_restores_the_lock_and_is_told_to_the_manager(tmp_path, monkeypatch):
    clone, _head, run, calls, git, _installs = managed(tmp_path, monkeypatch)
    tool(
        tmp_path.resolve(),
        "apm",
        "printf 'generated_at: now\\n' >> apm.lock.yaml\necho broken >&2\nexit 4",
    )
    out = run()
    assert (clone / "apm.lock.yaml").read_text() == LOCK and git(
        clone, "status", "--porcelain"
    ) == "", out
    assert f"FAIL apm install --frozen in {clone}: exit 4: broken" in out, out
    assert [repo for repo, _ in calls] == ["acme/managed"] and "failed in" in calls[0][1], calls


def test_a_finding_addresses_the_manager_not_the_owner(tmp_path, monkeypatch):
    clones, _heads, run, calls, _git = world(tmp_path, monkeypatch, ["acme/managed"])
    (clones["acme/managed"] / "base").write_text("changed")
    run()
    assert "for you to settle as this repo's manager" in calls[0][1], calls
    assert "for the owner to decide" not in calls[0][1], calls


def forwarder_world(tmp_path, monkeypatch, install):
    _clones, _heads, run, calls, _git = world(tmp_path, monkeypatch, ["acme/managed"])
    home = tmp_path.resolve()
    skills = home / ".agents/skills"
    script = skills / "orchestrating-agents/scripts/omnigent_agent.py"
    script.parent.mkdir(parents=True)
    script.write_text(
        '"""A forwarder."""\nif __name__ != "__main__":\n'
        '    raise ImportError(f"{__file__} only forwards to another skill\'s script: import that script")\n'
        'skill = "omnigent-agents"\n'
    )
    (skills / "orchestrating-agents/SKILL.md").write_text("x")
    run.hygiene.REPO = home / "dotagents"
    run.hygiene.REPO.mkdir()
    run.hygiene.DOTAGENTS.write_text(f'#!/bin/sh\n[ "$1" = install ] || exit 0\n{install}\n')
    return skills, run, calls


def test_a_forwarder_without_its_target_gets_the_target_installed(tmp_path, monkeypatch):
    skills, run, calls = forwarder_world(
        tmp_path,
        monkeypatch,
        f"mkdir -p {tmp_path.resolve()}/.agents/skills/omnigent-agents && "
        f"touch {tmp_path.resolve()}/.agents/skills/omnigent-agents/SKILL.md",
    )
    out = run()
    assert (skills / "omnigent-agents/SKILL.md").is_file(), out
    assert "CLEARED: forwarder" in out and "DRIFT:" not in out and calls == [], (out, calls)


def test_a_forwarder_whose_target_stays_missing_is_drift(tmp_path, monkeypatch):
    _skills, run, calls = forwarder_world(tmp_path, monkeypatch, "true")
    out = run()
    assert "DRIFT: forwarder" in out and "needs the `omnigent-agents` skill" in out, out
    assert len(calls) == 1 and calls[0][0] is None and "omnigent-agents" in calls[0][1], calls


def self_checkout(tmp_path, monkeypatch):
    """The account's dotagents checkout, up to date with its origin, whose lock is committed."""
    _clones, _heads, run, calls, git = world(tmp_path, monkeypatch, ["acme/managed"])
    home = tmp_path.resolve()
    git(home, "init", "-q", "--bare", "-b", "main", str(home / "self.git"))
    checkout = home / "self"
    git(home, "clone", "-q", str(home / "self.git"), str(checkout))
    (checkout / "apm.lock.yaml").write_text(LOCK)
    git(checkout, "add", ".")
    git(checkout, "commit", "-q", "-m", "pin")
    git(checkout, "push", "-q", "origin", "main")
    run.hygiene.REPO = checkout
    run.hygiene.DOTAGENTS.write_text("#!/bin/sh\nexit 0\n")
    return checkout, run, calls, git


def test_a_lock_an_earlier_install_rewrote_is_restored_and_pins_nothing_older(
    tmp_path, monkeypatch
):
    checkout, run, calls, git = self_checkout(tmp_path, monkeypatch)
    (checkout / "apm.lock.yaml").write_text(
        LOCK.replace("2026-01-01T00:00:00Z", "2026-11-22T13:15:00Z")
    )
    out = run()
    assert "STALE" not in out and calls == [], (out, calls)
    assert git(checkout, "status", "--porcelain") == "" and "restored" in out, out


def test_the_self_install_after_a_fast_forward_leaves_the_lock_committed(tmp_path, monkeypatch):
    checkout, run, _calls, git = self_checkout(tmp_path, monkeypatch)
    other = tmp_path.resolve() / "self-other"
    git(tmp_path.resolve(), "clone", "-q", str(tmp_path.resolve() / "self.git"), str(other))
    (other / "apm.lock.yaml").write_text(LOCK + "# released\n")
    git(other, "add", ".")
    git(other, "commit", "-q", "-m", "release")
    git(other, "push", "-q", "origin", "main")
    run.hygiene.DOTAGENTS = tmp_path.resolve() / "self-install"
    run.hygiene.DOTAGENTS.write_text(
        f'#!/bin/sh\n[ "$1" = install ] || exit 0\nprintf "generated_at: \'now\'\\n" >> {checkout}/apm.lock.yaml\n'
    )
    run.hygiene.DOTAGENTS.chmod(0o755)
    relaunched = []
    monkeypatch.setattr(os, "execv", lambda *argv: relaunched.append(argv))
    monkeypatch.delenv("AGENT_HYGIENE_RELAUNCHED", raising=False)
    out = run()
    monkeypatch.delenv("AGENT_HYGIENE_RELAUNCHED", raising=False)
    assert relaunched and git(checkout, "status", "--porcelain") == "", out
    assert (
        subprocess.run(
            ["git", "-C", str(checkout), "diff", "--quiet", "origin/main"], check=False
        ).returncode
        == 0
    )


def test_a_checkout_without_its_install_tool_says_what_is_missing(tmp_path, monkeypatch):
    import shutil

    clone, _head, run, calls, _git, installs = managed(tmp_path, monkeypatch)
    real = shutil.which
    monkeypatch.setattr(
        shutil,
        "which",
        lambda name, *a, **k: None if name in ("apm", "mise") else real(name, *a, **k),
    )
    out = run()
    assert installs() == [] and f"pulled {clone}" in out, out
    assert "apm is not on PATH" in calls[0][1] and calls[0][0] == "acme/managed", calls


def test_an_install_that_changes_committed_copies_is_put_back_and_told(tmp_path, monkeypatch):
    clone, _head, run, calls, git, _installs = managed(
        tmp_path, monkeypatch, {".claude/skills/x/SKILL.md": "pinned\n"}
    )
    tool(
        tmp_path.resolve(),
        "apm",
        "echo unreleased > .claude/skills/x/SKILL.md\nmkdir -p .agents && touch .agents/new",
    )
    out = run()
    assert (clone / ".claude/skills/x/SKILL.md").read_text() == "pinned\n", out
    assert git(clone, "status", "--porcelain") == "", out
    assert "changed its committed" in calls[0][1] and "bump PR" in calls[0][1], calls


def test_a_unit_naming_the_clone_through_home_or_linked_from_it_keeps_it_unpulled(
    tmp_path, monkeypatch
):
    clone, _head, run, _calls, git, _installs = managed(tmp_path, monkeypatch)
    home = tmp_path.resolve()
    units = home / ".config/systemd/user"
    units.mkdir(parents=True)
    before = git(clone, "rev-parse", "HEAD")
    (units / "app.service").write_text(
        f"[Service]\nWorkingDirectory=%h/{clone.relative_to(home)}\n"
    )
    out = run()
    assert git(clone, "rev-parse", "HEAD") == before and "app.service points at it" in out, out
    (units / "app.service").unlink()
    (clone / "deploy").mkdir()
    (clone / "deploy/app.service").write_text("[Service]\nExecStart=./run\n")
    (units / "app.service").symlink_to(
        clone / "deploy/app.service"
    )  # what `systemctl --user link` makes
    assert "is a link into it" in (run.hygiene.serves(clone, (set(), [])) or ""), out


def test_the_unit_scan_reads_linked_units_the_local_share_folder_and_the_real_path(
    tmp_path, monkeypatch
):
    clone, _head, run, _calls, _git, _installs = managed(tmp_path, monkeypatch)
    home, serves, idle = tmp_path.resolve(), run.hygiene.serves, (set(), [])
    shared = home / ".local/share/systemd/user"
    shared.mkdir(parents=True)
    (shared / "app.service").write_text(f"[Service]\nWorkingDirectory={clone}\n")
    assert "points at it" in (serves(clone, idle) or "")
    (shared / "app.service").unlink()
    dotfiles = home / "dotfiles"
    dotfiles.mkdir()
    (dotfiles / "app.service").write_text(
        f"[Service]\nWorkingDirectory=%h/{clone.relative_to(home)}\n"
    )
    (shared / "app.service").symlink_to(
        dotfiles / "app.service"
    )  # linked from outside the clone: read its target
    assert "points at it" in (serves(clone, idle) or "")
    (shared / "app.service").unlink()
    (home / "links").mkdir()
    (home / "links/dev").symlink_to(
        clone.parent
    )  # the finding names the clone through a linked folder
    (shared / "app.service").write_text(
        f"[Service]\nWorkingDirectory={clone}\n"
    )  # the unit names its real path
    assert "points at it" in (serves(home / "links/dev" / clone.name, idle) or "")
