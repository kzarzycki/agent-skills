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
        env={**os.environ, "COS_VALUES": ""},
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
