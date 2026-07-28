from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

COMMAND = [
    "npx",
    "--yes",
    "renovate@43.285.7",
    "--platform=local",
    "--dry-run=full",
    "--require-config=required",
    "--binary-source=global",
    "--base-dir=/tmp/dotagents-renovate-vendir-probe",
]
FIXTURE = Path(__file__).parents[1] / "fixtures" / "renovate"


def main(run: Callable[..., Any] = subprocess.run) -> int:
    result = run(COMMAND, cwd=FIXTURE, timeout=120, check=False)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
