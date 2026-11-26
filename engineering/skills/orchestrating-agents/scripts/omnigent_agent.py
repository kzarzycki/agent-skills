#!/usr/bin/env python3
"""orchestrating-agents/scripts/omnigent_agent.py: the Omnigent driver's former path, which the `omnigent-agents`
skill's scripts/omnigent_agent.py is now. Kept for one release line, so a project pinned to engineering keeps its
commands: it runs that script with the same arguments, input and exit code, after one deprecation line on stderr. It
goes away with the release that drops engineering's dependencies on the packages split out of it."""

import runpy
import sys
from pathlib import Path

# a forwarder, never a module: an import that found it took the wrong folder
if __name__ != "__main__":
    raise ImportError(f"{__file__} only forwards to another skill's script: import that script")


def installed(skill: str) -> Path:
    """The scripts folder of `skill`, which another package ships, found by the host's install layout: a sibling
    skill folder (APM's one skills directory), a sibling plugin's (a marketplace Claude Code loads in place), a
    native plugin APM deployed to the project's `.agents/plugins/`, else the newest version of a plugin in Claude
    Code's cache (`<marketplace>/<plugin>/<version>/`, beside the script or in `~/.claude/plugins/cache`) that no
    update has orphaned. A developer checkout of the pack (a git tree holding the marketplace file) is never
    searched, since it can sit on any branch: it counts only where AGENT_SKILLS_CHECKOUT is set, as the pack's own
    tests set it, the checkout is the GITHUB_WORKSPACE of the CI job running there, or this script is the pack's own
    `orchestrating-agents` script running from it (#2670: its siblings are the code it already runs). Exits naming the skill to install when none holds it."""
    # ponytail: four layouts, the ones APM and Claude Code use; a host with another adds its glob here.
    import os

    own = Path(__file__).resolve().parents[1]
    plugin = own.parent.parent
    root = plugin.parent
    checkout = (root / ".git").exists() and (root / ".claude-plugin" / "marketplace.json").is_file()
    # the pack's own CI runs in the workspace its job checked out: that checkout is the repo it runs in, not a stale clone
    workspace = os.environ.get("GITHUB_WORKSPACE")
    laid = (
        not checkout
        or bool(os.environ.get("AGENT_SKILLS_CHECKOUT"))
        or bool(workspace and Path(workspace).resolve() == root)
        or own.name == "orchestrating-agents"
    )
    cached = [
        *(root.parent.glob(f"[!.]*/[!.]*/skills/{skill}") if laid else []),
        *(Path.home() / ".claude" / "plugins" / "cache").glob(f"[!.]*/[!.]*/[!.]*/skills/{skill}"),
    ]
    for folder in [
        *([own.parent / skill] if laid else []),
        *(sorted(root.glob(f"[!.]*/skills/{skill}")) if laid else []),
        *(sorted(root.glob(f".agents/plugins/*/skills/{skill}")) if laid else []),
        *sorted(cached, key=lambda path: path.stat().st_mtime, reverse=True),
    ]:
        if (folder / "SKILL.md").is_file() and not (folder.parents[1] / ".orphaned_at").exists():
            return folder / "scripts"
    sys.exit(
        f"{Path(sys.argv[0]).name} needs the `{skill}` skill: install the package that ships it"
    )


skill = "omnigent-agents"
target = installed(skill) / "omnigent_agent.py"
print(
    f"orchestrating-agents/scripts/omnigent_agent.py is deprecated: run the `{skill}` skill's scripts/{target.name}",
    file=sys.stderr,
)
# as if the target ran itself, so no forwarder beside this one is importable
sys.path[0] = str(target.parent)
runpy.run_path(str(target), run_name="__main__")
