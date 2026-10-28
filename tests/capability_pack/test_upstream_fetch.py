from __future__ import annotations

import shlex
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from tools.capability_pack import qualify
from tools.capability_pack.qualify import ConfigurationError, QualificationError

FIXTURE_UPSTREAM = Path(__file__).parents[1] / "fixtures" / "upstreams" / "mattpocock-skills"


def _remote(tmp_path: Path) -> Path:
    remote = tmp_path / "remote"
    shutil.copytree(FIXTURE_UPSTREAM, remote)
    subprocess.run(["git", "init", "--quiet", "-b", "main", str(remote)], check=True)
    subprocess.run(["git", "-C", str(remote), "add", "-A"], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(remote),
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@t",
            "commit",
            "--quiet",
            "-m",
            "upstream",
        ],
        check=True,
    )
    return remote


def _stage(tmp_path: Path, url: str, skills: int = 3) -> Path:
    stage = tmp_path / "stage"
    stage.mkdir()
    git = {
        "url": url,
        "ref": "origin/main",
    }  # one mapping, dumped as YAML aliases like the real manifest
    config = {
        "apiVersion": "vendir.k14s.io/v1alpha1",
        "kind": "Config",
        "directories": [
            {
                "path": f"skills/s{n}",
                "contents": [{"path": ".", "git": git}],
            }
            for n in range(skills)
        ],
    }
    (stage / "vendir.yml").write_text(yaml.safe_dump(config, sort_keys=False))
    return stage


def _bin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, vendir: str) -> Path:
    """A ``git`` that logs its arguments before running the real one, and a fake ``vendir``."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    real_git = subprocess.run(
        ["which", "git"], check=True, capture_output=True, text=True
    ).stdout.strip()
    log = tmp_path / "git.log"
    quoted = shlex.quote
    (bin_dir / "git").write_text(
        f'#!/bin/sh\necho "$*" >> {quoted(str(log))}\nexec {quoted(real_git)} "$@"\n'
    )
    (bin_dir / "vendir").write_text(vendir)
    for tool in ("git", "vendir"):
        (bin_dir / tool).chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}:{Path(real_git).parent}:/usr/bin:/bin")
    return log


def test_sync_fetches_the_upstream_once_for_every_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    remote = _remote(tmp_path)
    stage = _stage(tmp_path, str(remote))
    seen = tmp_path / "seen.yml"
    git_log = _bin(
        tmp_path,
        monkeypatch,
        f'#!/bin/sh\nstage="$3"\ncp "$stage/vendir.yml" {shlex.quote(str(seen))}\n',
    )
    before = (stage / "vendir.yml").read_text()

    qualify._sync_manifest(stage, "update")

    clones = [line for line in git_log.read_text().splitlines() if line.startswith("clone ")]
    assert len(clones) == 1 and str(remote) in clones[0], clones
    urls = {
        content["git"]["url"]
        for directory in yaml.safe_load(seen.read_text())["directories"]
        for content in directory["contents"]
    }
    assert len(urls) == 1 and str(remote) not in urls
    assert (stage / "vendir.yml").read_text() == before


def test_sync_timeout_reads_qualify_timeout_and_names_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stage = _stage(tmp_path, str(_remote(tmp_path)))
    _bin(tmp_path, monkeypatch, "#!/bin/sh\nsleep 5\n")
    monkeypatch.setenv("QUALIFY_TIMEOUT", "1")

    with pytest.raises(
        QualificationError, match="vendir sync timed out after 1 seconds.*QUALIFY_TIMEOUT"
    ):
        qualify._sync_manifest(stage, "update")


@pytest.mark.parametrize("value", ["0", "-5", "soon"])
def test_a_timeout_that_is_no_whole_number_of_seconds_is_refused(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("QUALIFY_TIMEOUT", value)

    with pytest.raises(ConfigurationError, match="QUALIFY_TIMEOUT"):
        qualify._timeout()


def test_package_tests_default_to_300_seconds_and_read_qualify_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "tests").mkdir()
    limits = []

    def timing_out(*args, timeout, **kwargs):
        limits.append(timeout)
        raise subprocess.TimeoutExpired(args[0], timeout)

    monkeypatch.setattr(qualify.subprocess, "run", timing_out)
    monkeypatch.delenv("QUALIFY_TIMEOUT", raising=False)
    with pytest.raises(QualificationError, match="after 300 seconds.*QUALIFY_TIMEOUT"):
        qualify._run_package_tests(tmp_path)
    monkeypatch.setenv("QUALIFY_TIMEOUT", "900")
    with pytest.raises(QualificationError, match="after 900 seconds"):
        qualify._run_package_tests(tmp_path)

    assert limits == [300, 900]
