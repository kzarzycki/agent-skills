from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = (
    Path(__file__).resolve().parents[1] / "skills" / "chief-of-staff" / "scripts" / "pin_update.py"
)
APM_YML = "dependencies:\n  apm:\n  - git: acme/pack/engineering\n    ref: engineering-v1.2.0\n"
LOCK = "dependencies:\n- name: engineering\n  deployed_files:\n  - .agents/skills/a.md\n"


def sh(cwd, *cmd):
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@t",
    }
    subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, env=env)


@pytest.fixture
def world(tmp_path):
    remote = tmp_path / "remote"
    remote.mkdir()
    sh(remote, "git", "init", "-q")
    (remote / "f").write_text("x")
    sh(remote, "git", "add", "f")
    sh(remote, "git", "commit", "-qm", "c")
    for t in ("engineering-v1.2.0", "engineering-v1.10.0", "engineering-v1.9.0", "other-v9.0.0"):
        sh(remote, "git", "tag", t)
    repo = tmp_path / "consumer"
    (repo / ".agents" / "skills").mkdir(parents=True)
    sh(repo, "git", "init", "-q")
    (repo / "apm.yml").write_text(APM_YML)
    (repo / "apm.lock.yaml").write_text(LOCK)
    (repo / ".agents/skills/a.md").write_text("orig")
    sh(repo, "git", "add", "-A")
    sh(repo, "git", "commit", "-qm", "c")
    home = tmp_path / "home"
    home.mkdir()
    (home / "cos-values.yml").write_text("pin:\n  tag_prefix: engineering-v\ncos_session: sess-1\n")
    sent = tmp_path / "sent.txt"
    (tmp_path / "oa.py").write_text(
        f"import sys\nopen({str(sent)!r}, 'a').write(' '.join(sys.argv[1:]) + '\\n')\n"
    )
    ok = tmp_path / "apm-ok"
    ok.write_text("#!/bin/sh\necho new > .agents/skills/a.md\necho n > .agents/skills/added.md\n")
    bad = tmp_path / "apm-bad"
    bad.write_text(
        "#!/bin/sh\necho half > .agents/skills/a.md\necho n > .agents/skills/added.md\necho boom >&2\nexit 3\n"
    )
    ok.chmod(0o755)
    bad.chmod(0o755)
    return {
        "repo": repo,
        "home": home,
        "remote": remote,
        "sent": sent,
        "ok": ok,
        "bad": bad,
        "oa": tmp_path / "oa.py",
    }


def run(w, apm="ok", *extra, repo=None):
    return subprocess.run(
        [
            sys.executable,
            "-B",
            str(SCRIPT),
            "--home",
            str(w["home"]),
            "--repo",
            str(repo or w["repo"]),
            "--remote",
            str(w["remote"]),
            "--apm",
            str(w[apm]),
            "--omnigent",
            str(w["oa"]),
            *extra,
        ],
        capture_output=True,
        text=True,
        check=False,
        env={
            **os.environ,
            "COS_VALUES": "",
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@t",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@t",
        },
    )


def test_moves_to_newest_tag_by_version_not_text(world):
    r = run(world)
    assert r.returncode == 0, r.stderr
    assert "ref: engineering-v1.10.0" in (world["repo"] / "apm.yml").read_text()
    assert "compare/engineering-v1.2.0...engineering-v1.10.0" in r.stdout
    assert (world["repo"] / ".agents/skills/a.md").read_text().strip() == "new"


def test_notifies_cos_session_with_action_needed(world):
    run(world)
    line = world["sent"].read_text()
    assert line.startswith("relay sess-1 ACTION NEEDED:") and "engineering-v1.10.0" in line


def test_skips_when_a_deployed_file_has_local_edits(world):
    (world["repo"] / ".agents/skills/a.md").write_text("mine")
    r = run(world)
    assert r.returncode == 0 and "skipped" in r.stdout and ".agents/skills/a.md" in r.stdout
    assert "engineering-v1.2.0" in (world["repo"] / "apm.yml").read_text()
    assert (world["repo"] / ".agents/skills/a.md").read_text() == "mine"


def test_failed_install_is_rolled_back(world):
    r = run(world, "bad")
    assert r.returncode == 1 and "rolled back" in r.stdout
    assert (world["repo"] / "apm.yml").read_text() == APM_YML
    assert (world["repo"] / ".agents/skills/a.md").read_text() == "orig"
    assert not (world["repo"] / ".agents/skills/added.md").exists()


def test_up_to_date_changes_nothing(world):
    (world["repo"] / "apm.yml").write_text(APM_YML.replace("1.2.0", "1.10.0"))
    sh(world["repo"], "git", "commit", "-qam", "pin")
    r = run(world)
    assert r.returncode == 0 and "newest" in r.stdout and not world["sent"].exists()


def test_refuses_the_packs_own_checkout(world):
    (world["repo"] / ".claude-plugin").mkdir()
    (world["repo"] / ".claude-plugin" / "marketplace.json").write_text("{}")
    r = run(world)
    assert r.returncode == 2 and "pack itself" in r.stderr


def test_no_prefix_set_is_a_values_error(world):
    (world["home"] / "cos-values.yml").write_text("cos_session: s\n")
    r = run(world)
    assert r.returncode == 2 and "pin.tag_prefix" in r.stderr


def test_dry_run_changes_nothing(world):
    r = run(world, "ok", "--dry-run")
    assert "would move" in r.stdout and (world["repo"] / "apm.yml").read_text() == APM_YML


def test_rollback_survives_a_new_untracked_file_in_the_lock(world):
    (world["repo"] / "apm.lock.yaml").write_text(LOCK + "  - .agents/skills/added.md\n")
    sh(world["repo"], "git", "commit", "-qam", "lock lists a file not yet tracked")
    r = run(world, "bad")
    assert r.returncode == 1
    assert (world["repo"] / "apm.yml").read_text() == APM_YML
    assert not (world["repo"] / ".agents/skills/added.md").exists()


def release_with_floor(w, oldest, via):
    """The newest release ships `bump-from.yml` in its package folder, as the pack does."""
    remote = w["remote"]
    (remote / "engineering").mkdir()
    (remote / "engineering" / "bump-from.yml").write_text(f"oldest: {oldest}\nvia: {via}\n")
    sh(remote, "git", "add", "-A")
    sh(remote, "git", "commit", "-qm", "floor")
    sh(remote, "git", "tag", "engineering-v2.0.0")


def test_a_jump_past_the_releases_floor_is_refused_naming_the_stepping_stone(world):
    """#2709: a pack-bump PR from too old a base passes neither gate, so the updater stops at the stone."""
    release_with_floor(world, "1.5.0", "1.9.0")
    r = run(world)
    assert r.returncode == 0, r.stderr
    assert "refused" in r.stdout and "engineering-v1.9.0 first" in r.stdout
    assert "from 1.5.0 or newer" in r.stdout
    assert (world["repo"] / "apm.yml").read_text() == APM_YML
    assert (world["repo"] / ".agents/skills/a.md").read_text() == "orig"


def test_a_pin_at_the_floor_moves(world):
    release_with_floor(world, "1.2.0", "1.9.0")
    r = run(world)
    assert "ref: engineering-v2.0.0" in (world["repo"] / "apm.yml").read_text(), r.stdout


def stub(w, name, body):
    f = w["ok"].parent / name
    f.write_text("#!/bin/sh\n" + body)
    f.chmod(0o755)
    w[name] = f


def test_runs_apm_update_and_moves_a_transitive_pin(world):
    """#2706: `apm install` keeps a sibling's locked ref, so the updater runs `apm update` too."""
    lock = "dependencies:\n- name: loop\n  repo_url: acme/pack\n  virtual_path: loop\n  resolved_ref: loop-v1.0.0\n"
    (world["repo"] / "apm.lock.yaml").write_text(
        lock + "  deployed_files:\n  - .agents/skills/a.md\n"
    )
    sh(world["repo"], "git", "commit", "-qam", "lock")
    new = lock.replace("1.0.0", "1.1.0") + "  deployed_files:\n  - .agents/skills/a.md\n"
    stub(world, "apm-up", f'[ "$1" = update ] && cat > apm.lock.yaml <<"E"\n{new}E\nexit 0\n')
    r = run(world, "apm-up")
    assert r.returncode == 0, r.stderr
    assert "resolved_ref: loop-v1.1.0" in (world["repo"] / "apm.lock.yaml").read_text()
    assert "compare/loop-v1.0.0...loop-v1.1.0" in r.stdout


def test_a_failing_audit_rolls_back(world):
    """#2706: `apm audit` catches a committed local edit to an installed skill."""
    stub(
        world,
        "apm-audit",
        'echo new > .agents/skills/a.md\n[ "$1" = audit ] && { echo drift >&2; exit 1; }\nexit 0\n',
    )
    r = run(world, "apm-audit")
    assert r.returncode == 1 and "rolled back" in r.stdout and "audit" in r.stdout
    assert (world["repo"] / ".agents/skills/a.md").read_text() == "orig"
    assert (world["repo"] / "apm.yml").read_text() == APM_YML


def test_an_install_that_removes_a_skill_is_rolled_back(world):
    """#2706: a deployed file the install deletes is a lost skill, not an update."""
    stub(world, "apm-rm", "rm .agents/skills/a.md\n")
    r = run(world, "apm-rm")
    assert r.returncode == 1 and "removed" in r.stdout
    assert (world["repo"] / ".agents/skills/a.md").read_text() == "orig"


def test_commits_with_a_compare_link_per_moved_pin(world):
    """#2706: the run ends in a commit whose message links each moved pin."""
    r = run(world)
    assert r.returncode == 0, r.stderr
    msg = subprocess.run(
        ["git", "-C", str(world["repo"]), "log", "-1", "--format=%B"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert "compare/engineering-v1.2.0...engineering-v1.10.0" in msg
    status = subprocess.run(
        [
            "git",
            "-C",
            str(world["repo"]),
            "status",
            "--porcelain",
            "apm.yml",
            ".agents/skills/a.md",
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert status == ""
