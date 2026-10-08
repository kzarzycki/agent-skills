#!/usr/bin/env python3
"""The old name of approvals.py, kept for one release: runs it with the same arguments, so its output and exit code
are approvals.py's."""

import runpy
import sys
from pathlib import Path

sys.argv[0] = str(Path(__file__).with_name("approvals.py"))
runpy.run_path(sys.argv[0], run_name="__main__")
