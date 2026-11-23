"""The root conftest's trap `gh` (#2035): no test reaches GitHub through the real gh."""

from __future__ import annotations

import os
import shlex
import tempfile
from collections.abc import MutableMapping
from pathlib import Path

# No test reaches GitHub through the real `gh` (#2035): every test runs with a `gh` first on PATH that answers each call
# with gh's no-GitHub-host error and exit 1; a test that needs a fake puts its own ahead of it. In a cloud worker's or
# verifier's checkout, whose remote is github.com, an un-stubbed call otherwise spends the owner's quota on every suite and
# mutation run. A `live_agent` test keeps the real gh, and so does a run with GH_REAL_IN_TESTS=1.
# gh's own answer in a checkout whose remotes name no GitHub host, as a test's temporary repo has: the answer most tests
# already got from the real gh, so the trap changes no path a test takes
NO_GH = (
    "none of the git remotes configured for this repository point to a known GitHub host."
    " (the test suite reaches no GitHub: GH_REAL_IN_TESTS=1 lets it)"
)


def install_trap(env: MutableMapping[str, str], parent: str | None = None) -> Path | None:
    """Put the trap `gh` first on `env`'s PATH and return its folder; None with GH_REAL_IN_TESTS=1, or when `env`
    already carries a trap that is on its PATH (a worker under its controller), which is then left as it is. A new
    folder goes under `parent` (default: the system temp folder), never the checkout, so no run leaves a file there."""
    if env.get("GH_REAL_IN_TESTS") == "1":
        return None
    known = env.get("GH_NO_GITHUB_TRAP", "")
    if known and known in env.get("PATH", "").split(os.pathsep) and Path(known, "gh").is_file():
        return None
    trap = Path(tempfile.mkdtemp(prefix="no-gh-", dir=parent))
    (trap / "gh").write_text(f"#!/bin/sh\necho {shlex.quote(NO_GH)} >&2\nexit 1\n")
    (trap / "gh").chmod(0o755)
    env["PATH"] = f"{trap}{os.pathsep}{env.get('PATH', '')}"
    env["GH_NO_GITHUB_TRAP"] = str(trap)
    return trap


def without_trap(path: str, trap: str) -> str:
    """`path` with every copy of the `trap` folder taken out."""
    return os.pathsep.join(entry for entry in path.split(os.pathsep) if entry != trap)
