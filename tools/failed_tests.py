"""The tests a CI run ran and failed, as JSON: `python3 tools/failed_tests.py <junit.xml>... <out.json>`.

`--rerun <json>` prints the node ids of its `failed` tests, for a rerun of the job to run only those.

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


def node_id(test_id: str, root: Path) -> str | None:
    """The pytest node id of a `<classname>::<name>` id: the longest dotted prefix of the classname that is a .py file
    under `root`, the rest of the classname as `::Class` parts, then the test name. None when no file matches."""
    classname, _, name = test_id.rpartition("::")
    parts = classname.split(".")
    for cut in range(len(parts), 0, -1):
        file = root.joinpath(*parts[:cut]).with_suffix(".py")
        if file.is_file():
            return "::".join([file.relative_to(root).as_posix(), *parts[cut:], name])
    return None


def rerun_args(failed_json: Path, root: Path) -> list[str]:
    """The pytest node ids of the tests a `failed-tests.json` says failed: `python3 tools/failed_tests.py --rerun <json>`
    prints them, one per line, for a rerun of a failed `qualify` job to run alone. Empty when nothing failed, the file is
    missing or unreadable, or an id maps to no file (then the rerun runs the usual check, never fewer tests)."""
    try:
        failed = json.loads(failed_json.read_text()).get("failed", [])
    except OSError, ValueError, AttributeError:
        return []
    ids = [node_id(test, root) for test in failed]
    return [] if None in ids else list(dict.fromkeys(ids))


def main(argv: list[str]) -> int:
    if len(argv) == 2 and argv[0] == "--rerun":
        print("\n".join(rerun_args(Path(argv[1]), Path.cwd())))
        return 0
    if len(argv) < 2:
        print("usage: failed_tests.py <junit.xml>... <out.json>", file=sys.stderr)
        return 2
    out = Path(argv[-1])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(collect([Path(p) for p in argv[:-1]]), indent=2) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
