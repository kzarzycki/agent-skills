"""A package script's module docstring stays short (#2834).

A docstring is the script's `--help` and the first thing an agent reads, so it says what the script is and points to
its docs. A rule goes in the docs and in a test, never only in `--help`: gatekeeper.py's docstring grew to 72 KB
because each change wrote its rule there. Files already over the cap are listed with their size: each may shrink,
never grow.

    uv run python -m tools.script_docstring_size

`mise run check-fast` runs it; exit 1 and one line per script over the cap.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CAP = 4096  # bytes of the module docstring
# Over the cap today (#2834): each may shrink, never grow. Shrink one in its own change and delete its line.
ALLOWED = {
    "omnigent/skills/omnigent-agents/scripts/omnigent_agent.py": 29364,
    "loop/skills/engineering-loop/scripts/cloud_verifier.py": 8407,
    "loop/skills/engineering-loop/scripts/mutate.py": 5023,
}
GLOBS = ("*/skills/*/scripts/*.py", "tools/*.py", "tools/*/*.py", "engineering-hooks/hooks/*.py")
HOME = (
    "say what the script is and point to its docs; a rule belongs in policy.md (or the skill's docs), "
    "in the subcommand's help= and in a function's docstring, with a test"
)


def docstring_size(path: Path) -> int:
    """The bytes of `path`'s module docstring; 0 when it has none or does not parse."""
    try:
        doc = ast.get_docstring(ast.parse(path.read_text(encoding="utf-8")), clean=False)
    except Exception:  # a file that does not parse or decode has no docstring to size
        return 0
    return len((doc or "").encode())


def oversize(root: Path = ROOT, cap: int = CAP, allowed: dict[str, int] = ALLOWED) -> list[str]:
    """One line per script under `root` whose docstring is over `cap` (or over its allowlisted size)."""
    found = []
    for pattern in GLOBS:
        for path in sorted(root.glob(pattern)):
            name, size = path.relative_to(root).as_posix(), docstring_size(path)
            if name.startswith((".", "apm_modules/")):  # vendored copies follow their source
                continue
            if name in allowed and size > allowed[name]:
                found.append(
                    f"{name}: module docstring is {size} bytes, over its listed {allowed[name]}: {HOME}"
                )
            elif name not in allowed and size > cap:
                found.append(
                    f"{name}: module docstring is {size} bytes, over the {cap}-byte cap: {HOME}"
                )
    return found


def main() -> int:
    found = oversize()
    print("\n".join(found))
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
