"""The tests a CI run ran and failed, as JSON: `python3 tools/failed_tests.py <junit.xml>... <out.json>`.

`qualify` uploads the file as the `failed-tests` artifact, which the gatekeeper's break-glass proof reads (its
breakglass.md): `{"failed": [test ids], "selected": [test ids]}`, each id `<classname>::<name>`. A run whose tests never
started (no JUnit file, or none readable) writes both lists empty, which the proof reads as a failure with no test ids.
"""

from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def collect(paths: list[Path]) -> dict[str, list[str]]:
    """Every test case of the JUnit files, and those with a failure or an error, each once, in order."""
    selected: list[str] = []
    failed: list[str] = []
    for path in paths:
        try:
            root = ET.parse(path).getroot()
        except OSError, ET.ParseError:
            continue
        for case in root.iter("testcase"):
            name = f"{case.get('classname', '')}::{case.get('name', '')}".strip(":")
            if name not in selected:
                selected.append(name)
            if (
                case.find("failure") is not None or case.find("error") is not None
            ) and name not in failed:
                failed.append(name)
    return {"failed": failed, "selected": selected}


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: failed_tests.py <junit.xml>... <out.json>", file=sys.stderr)
        return 2
    out = Path(argv[-1])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(collect([Path(p) for p in argv[:-1]]), indent=2) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
