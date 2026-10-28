#!/usr/bin/env -S uv run -q --script
# /// script
# requires-python = ">=3.9"
# dependencies = ["PyYAML==6.0.3"]
# ///
"""approvals.py: the gatekeeper's former name, kept for one release line. gatekeeper.py beside it holds the CLI, the
policy and every verb this name ran, under the same arguments, output and exit codes; its docstring is the manual."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gatekeeper import *  # noqa: E402, F403  the names older importers read from approvals
from gatekeeper import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
