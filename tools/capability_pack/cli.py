from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from tools.capability_pack.qualify import (
    BreakingDriftError,
    ConfigurationError,
    QualificationError,
    qualify,
    validate_release_candidate,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="capability-pack")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("update", "check"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("package", type=Path)
        subparser.add_argument("--summary", type=Path)
    release = subparsers.add_parser("release-check")
    release.add_argument("package", type=Path)
    release.add_argument("tag")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
    except SystemExit as error:
        return int(error.code)
    try:
        if args.command == "release-check":
            validate_release_candidate(args.package, args.tag)
            return 0
        mode = "update" if args.command == "update" else "locked"
        result = qualify(args.package, mode, args.summary)
    except ConfigurationError as error:
        print(error, file=sys.stderr)
        return 2
    except BreakingDriftError as error:
        print(error, file=sys.stderr)
        return 3
    except (QualificationError, OSError, ValueError) as error:
        print(error, file=sys.stderr)
        return 4
    if result.summary:
        print(result.summary, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
