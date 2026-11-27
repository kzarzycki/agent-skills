"""The heavy-run hook reads loop.md's `Cloud worker: none` with the stdlib only, so it reads `cloud_worker: none` of the
`## Loop settings` block itself (#2830); it must agree with the gatekeeper's loader on every shape."""

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def load(name: str, path: Path) -> object:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


guard = load("heavy_run_guard_2830", ROOT / "engineering-hooks" / "hooks" / "heavy_run_guard.py")
gatekeeper = load(
    "gatekeeper_2830", ROOT / "gatekeeper" / "skills" / "gatekeeper" / "scripts" / "gatekeeper.py"
)
BLOCK = "# Loop\n\n## Loop settings\n\n```yaml\n{body}```\n\n## Other\n\ncloud_worker: none\n"


@pytest.mark.parametrize(
    "text",
    [
        "# Loop\n\nCloud worker: none, heavy runs stay on hosts\n",
        "# Loop\n\nCloud worker: claude-cloud, gate test\n",
        "# Loop\n\nProse only.\n",
        BLOCK.format(body="cloud_worker: none\n"),
        BLOCK.format(body="cloud_worker: none  # kept on hosts\n"),
        BLOCK.format(body="cloud_worker:\n  agent: claude-cloud\n  gate: test\n"),
        BLOCK.format(body="gate: full\n"),
    ],
)
def test_the_hook_and_the_loader_agree_on_whether_workers_stay_on_hosts(
    tmp_path: Path, text: str
) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "docs" / "agents").mkdir(parents=True)
    (tmp_path / "docs" / "agents" / "loop.md").write_text(text)
    on_hosts = gatekeeper.loop_setting(text, "cloud_worker") == "none"
    assert (guard.loop_repo(tmp_path) is None) == on_hosts
