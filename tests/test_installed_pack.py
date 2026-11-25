"""#2485: the pack's scripts resolve the installed copy of the pack, never a developer checkout of it.

A checkout (a git tree that holds the marketplace file) can sit on any branch and hold a stale script, so a
resolver that finds a sibling there brings that script back into a run. The guard is a test, since a warning
lets it return."""

import importlib.util
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPOSITORY = Path(__file__).resolve().parents[1]
RESOLVERS = [
    "chief-of-staff/skills/chief-of-staff/scripts/cos_page.py",
    "engineering/skills/chief-of-staff/scripts/cos_page.py",
    "engineering/skills/chief-of-staff/scripts/memory.py",
    "engineering/skills/engineering-loop/scripts/_installed.py",
    "engineering/skills/omnigent-telemetry/scripts/omnigent_telemetry.py",
    "engineering/skills/orchestrating-agents/scripts/claude_cloud.py",
    "engineering/skills/orchestrating-agents/scripts/claude_environments.py",
    "engineering/skills/orchestrating-agents/scripts/omnigent_agent.py",
    "github/skills/github-tracker/scripts/_installed.py",
    "loop/skills/engineering-loop/scripts/_installed.py",
    "gatekeeper/skills/gatekeeper/scripts/gatekeeper.py",
    "omnigent/skills/omnigent-agents/scripts/omnigent_agent.py",
]


def function(path: Path) -> tuple[str, str]:
    found = re.search(
        r"^def (installed(?:_scripts)?)\(.*?(?=^\S|\Z)", path.read_text(), re.MULTILINE | re.DOTALL
    )
    assert found, f"{path}: no resolver"
    return found.group(1), found.group().rstrip()


def checkout_with_skill(tmp_path: Path, skill: str = "omnigent-agents") -> Path:
    """A developer checkout holding a sibling plugin that ships `skill`."""
    root = tmp_path / "checkout"
    (root / ".git").mkdir(parents=True)
    (root / ".claude-plugin").mkdir()
    (root / ".claude-plugin" / "marketplace.json").write_text("{}")
    skill_dir = root / "other" / "skills" / skill
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(skill)
    return root


def load_at(root: Path, relative: str, source: Path):
    """The resolver alone, placed at `relative` inside `root` as the script would sit there."""
    name, text = function(source)
    target = root / "pkg" / "skills" / "me" / "scripts" / "script.py"
    target.parent.mkdir(parents=True)
    target.write_text("import sys\nfrom pathlib import Path\n\n\n" + text)
    spec = importlib.util.spec_from_file_location("resolver", target)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, name)


@pytest.mark.parametrize("script", RESOLVERS)
def test_a_resolver_in_a_checkout_does_not_return_the_checkouts_sibling(
    script: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("AGENT_SKILLS_CHECKOUT", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    root = checkout_with_skill(tmp_path)
    resolve = load_at(root, script, REPOSITORY / script)
    try:
        found = resolve("omnigent-agents")
    except SystemExit as stop:
        assert "needs the `omnigent-agents` skill" in str(stop.code)
    else:
        assert found is None


@pytest.mark.parametrize("script", RESOLVERS)
def test_a_resolver_in_a_checkout_returns_the_installed_copy(
    script: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("AGENT_SKILLS_CHECKOUT", raising=False)
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    installed = home / ".claude/plugins/cache/mkt/omnigent/1.0.0/skills/omnigent-agents"
    installed.mkdir(parents=True)
    (installed / "SKILL.md").write_text("x")
    resolve = load_at(checkout_with_skill(tmp_path), script, REPOSITORY / script)
    assert resolve("omnigent-agents") == installed / "scripts"


def test_the_pack_own_tests_may_opt_into_the_checkout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AGENT_SKILLS_CHECKOUT", "1")
    root = checkout_with_skill(tmp_path)
    resolve = load_at(root, "x", REPOSITORY / RESOLVERS[3])
    assert resolve("omnigent-agents") == root / "other/skills/omnigent-agents/scripts"


def test_the_deprecated_forwarder_runs_the_installed_omnigent_agents_script(
    tmp_path: Path,
) -> None:
    """`deps-nightly` goes through the forwarder in a checkout: it must run the installed script."""
    home = tmp_path / "home"
    installed = home / ".claude/plugins/cache/mkt/omnigent/1.0.0/skills/omnigent-agents"
    (installed / "scripts").mkdir(parents=True)
    (installed / "SKILL.md").write_text("x")
    (installed / "scripts" / "omnigent_agent.py").write_text("print('installed copy')\n")
    env = {"PATH": "/usr/bin:/bin", "HOME": str(home), "PYTHONDONTWRITEBYTECODE": "1"}
    forwarder = REPOSITORY / "engineering/skills/orchestrating-agents/scripts/omnigent_agent.py"
    done = subprocess.run(
        [sys.executable, str(forwarder)], env=env, capture_output=True, text=True, check=False
    )
    assert (done.returncode, done.stdout) == (0, "installed copy\n"), done.stderr
    bare = {**env, "HOME": str(tmp_path / "empty")}
    refused = subprocess.run(
        [sys.executable, str(forwarder)], env=bare, capture_output=True, text=True, check=False
    )
    assert refused.returncode != 0
    assert "needs the `omnigent-agents` skill" in refused.stderr


def test_no_pack_script_names_a_developer_checkout() -> None:
    """The grep of the proof: a path into a developer clone of the pack in a shipped script or skill file."""
    files = subprocess.run(
        ["git", "ls-files", "*/skills/*"],
        cwd=REPOSITORY,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    pattern = re.compile(r"(~|\$HOME|\$\{HOME\}|/home/[a-z]+|/Users/[A-Za-z]+)/dev/agent-skills")
    hits = [
        f"{f}:{n}"
        for f in files
        if not f.startswith((".claude/", ".agents/")) and "/tests/" not in f
        for n, line in enumerate((REPOSITORY / f).read_text(errors="ignore").splitlines(), 1)
        if pattern.search(line)
    ]
    assert hits == []
