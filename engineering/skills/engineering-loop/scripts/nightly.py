#!/usr/bin/env -S uv run -q --script
# /// script
# requires-python = ">=3.9"
# dependencies = ["PyYAML==6.0.3"]
# ///
"""engineering-loop/scripts/nightly.py: the nightly script's former path, which the `engineering-loop` skill's scripts/nightly.py is now.
Kept for one release line, so a project pinned to engineering keeps its commands, in a checkout of this repo as in
an install: it runs that script with the same arguments, input and exit code, after one deprecation line on stderr.
It goes away with the release that drops engineering's dependencies on the packages split out of it."""

import runpy
import sys
from pathlib import Path

# a forwarder, never a module: an import that found it took the wrong folder
if __name__ != "__main__":
    raise ImportError(f"{__file__} only forwards to another skill's script: import that script")

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _installed import installed  # noqa: E402

skill = "engineering-loop"
target = installed(skill) / "nightly.py"
print(
    f"engineering-loop/scripts/nightly.py is deprecated: run the `{skill}` skill's scripts/{target.name}",
    file=sys.stderr,
)
# as if the target ran itself, so no forwarder beside this one is importable
sys.path[0] = str(target.parent)
runpy.run_path(str(target), run_name="__main__")
