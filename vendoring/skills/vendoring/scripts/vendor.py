#!/usr/bin/env -S uv run -q --script
# /// script
# requires-python = ">=3.14,<3.15"
# dependencies = ["PyYAML==6.0.3"]
# ///
"""Run the capability-pack tool with its own runtime, from any checkout.

    uv run <this skill>/scripts/vendor.py check <pack>
    uv run <this skill>/scripts/vendor.py update <pack>

`uv run` provisions Python 3.14 and PyYAML from the header above, so the consuming project
needs no Python environment of its own. The package beside this file is on `sys.path` as the
script's own folder.
"""

import sys

from capability_pack.cli import main

sys.exit(main())
