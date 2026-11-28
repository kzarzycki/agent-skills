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


HEADING = "# Loop\n\n## Loop settings\n\n```yaml\n{body}```\n"
CASES = [
    # (text, whether the hook keeps the run on the host)
    ("# Loop\n\nCloud worker: none, heavy runs stay on hosts\n", True),
    ("# Loop\n\nCloud worker: claude-cloud, gate test\n", False),
    ("# Loop\n\nProse only.\n", False),
    (BLOCK.format(body="cloud_worker: none\n"), True),
    (BLOCK.format(body="cloud_worker: none  # kept on hosts\n"), True),
    (BLOCK.format(body='cloud_worker: "none"\ngate: full\n'), True),
    (BLOCK.format(body="gate_cost:\n  cores: 4\n  gb: 8\ncloud_worker: none\n"), True),
    (BLOCK.format(body="cloud_worker:\n  agent: claude-cloud\n  gate: test\n"), False),
    (BLOCK.format(body="gate: full\n"), False),
    # flow, a nested value on the next line: not read by the hook (the loader reads them as none)
    (BLOCK.format(body="{cloud_worker: none}\n"), False),
    (BLOCK.format(body='{"cloud_worker": "none", gate: full}\n'), False),
    (BLOCK.format(body='"cloud_worker": none\n'), True),
    (BLOCK.format(body="cloud_worker:\n  none\n"), False),
    # prose after the closing fence is no setting (the loader reads the block only)
    ("# Loop\n\n## Loop settings\n\n```yaml\ngate: full\n```\n\ncloud_worker: none\n", False),
    # a legacy line beside a block that sets the key: the loader refuses the duplicate
    (
        "# Loop\n\nCloud worker: none\n\n"
        + BLOCK.format(body="cloud_worker:\n  agent: claude-cloud\n"),
        False,
    ),
    (
        "# Loop\n\nCloud worker: none\n\n" + BLOCK.format(body="cloud_worker: none\n"),
        False,
    ),
    # a yaml block under another heading is no setting; a second one under the same heading is refused by the loader
    (BLOCK.format(body="cloud_worker: none\n") + "\n```yaml\nafected_tests: x\n```\n", True),
    (HEADING.format(body="cloud_worker: none\n") + "\n```yaml\nafected_tests: x\n```\n", False),
    (BLOCK.format(body="cloud_worker: None\n"), False),
    # the string that holds the words is no key: the loader reads no cloud_worker
    (BLOCK.format(body='{test_report: "notes cloud_worker: none, continue"}\n'), False),
    (BLOCK.format(body='test_report: "notes cloud_worker: none, continue"\n'), False),
    (BLOCK.format(body="test_report: notes cloud_worker: none, continue\n"), False),
    # the key beside a misspelt one: the loader refuses the block
    (BLOCK.format(body="cloud_worker: none\nafected_tests: x\n"), False),
    (BLOCK.format(body="cloud_worker: none\nextra: x\n"), False),
    # the heading twice: a second block hides behind the first
    (
        HEADING.format(body="cloud_worker: none\n")
        + "\n## Loop settings\n\n```yaml\nafected_tests: x\n```\n",
        False,
    ),
    (HEADING.format(body="cloud_worker: none\n") + "\n## Loop settings\n\nProse.\n", False),
    # anchors, tags, duplicates, a block scalar, a quote left open
    (BLOCK.format(body="cloud_worker: none\ncloud_worker: none\n"), False),
    (BLOCK.format(body="x: &a 1\ncloud_worker: none\n"), False),
    (BLOCK.format(body="gate: |\n  full\ncloud_worker: none\n"), False),
    (BLOCK.format(body='test_report: "open\ncloud_worker: none"\n'), False),
    (BLOCK.format(body="cloud_worker: none\n---\nafected_tests: x\n"), False),
    (BLOCK.format(body="cloud_worker: !!str none\n"), False),
]


@pytest.mark.parametrize(("text", "hook"), CASES)
def test_the_hook_and_the_loader_agree_on_whether_workers_stay_on_hosts(
    tmp_path: Path, text: str, hook: bool
) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "docs" / "agents").mkdir(parents=True)
    (tmp_path / "docs" / "agents" / "loop.md").write_text(text)
    gatekeeper.loop_block.cache_clear()
    try:
        loader_none = gatekeeper.loop_setting(text, "cloud_worker") == "none"
    except gatekeeper.Refused:
        loader_none = False  # a block the loader refuses never lets a heavy run stay on the host
    on_hosts = guard.loop_repo(tmp_path) is None
    assert on_hosts == hook
    assert not on_hosts or loader_none  # the hook is never looser than the loader


def test_the_hooks_key_set_is_the_loaders_top_level_schema() -> None:
    assert guard.SCHEMA_KEYS == set(gatekeeper.LOOP_KEYS)
