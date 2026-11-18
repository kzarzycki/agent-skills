"""The tests a change touches, for the landing gate (`mise run check-fast`): prints one pytest target per line.

The changed files come from `git diff` against the base (origin/main, or argv[1]). A changed test file runs. A changed
script or module runs every test file that names its stem. Any other file (a skill's prose, docs, config) runs only
the cheap repo-wide checks, `tests/test_skill_*.py`. No base to diff, or a change to the test setup itself
(pyproject.toml, uv.lock, mise.toml, tools/), runs everything, since the map cannot say what that touches.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ALL = ["tests", "engineering/tests"]
EVERYTHING = ("pyproject.toml", "uv.lock", "mise.toml", "tools/", "conftest.py")
CHEAP = sorted(str(p) for p in Path("tests").glob("test_skill_*.py"))


def changed(base: str) -> list[str] | None:
    done = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    return done.stdout.split() if done.returncode == 0 else None


def targets(files: list[str] | None) -> list[str]:
    if files is None or any(f.startswith(EVERYTHING) for f in files):
        return ALL
    tests = [
        p for r in ALL for p in sorted(Path(r).rglob("test_*.py")) if "/e2e/" not in p.as_posix()
    ]
    picked = set(CHEAP)
    for f in files:
        path = Path(f)
        if path.name.startswith("test_") and path.suffix == ".py" and path.exists():
            picked.add(f)
        elif path.suffix == ".py":
            picked.update(str(t) for t in tests if path.stem in t.read_text(errors="ignore"))
    return sorted(picked)


if __name__ == "__main__":
    print("\n".join(targets(changed(sys.argv[1] if len(sys.argv) > 1 else "origin/main"))))
