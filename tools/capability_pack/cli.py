from __future__ import annotations

import argparse
import shutil
import sys
from collections.abc import Sequence
from pathlib import Path

from tools.capability_pack.consumer import assert_codex_inventory, prepare_consumer
from tools.capability_pack.github import GitHubError, reconcile_draft_pr
from tools.capability_pack.qualify import (
    BreakingDriftError,
    ConfigurationError,
    PortRequiredError,
    QualificationError,
    qualify,
    upstream_deltas,
    validate_release_candidate,
)


def write_deltas(directory: Path, error: PortRequiredError) -> list[dict]:
    """Save each pending upstream delta for the porter; a fetch failure is evidence too."""
    shutil.rmtree(directory / "deltas", ignore_errors=True)
    diagnostics = [
        {
            "code": "port_required",
            "path": f"skills/{name}",
            "detail": f"{source} {error.old_commit}..{error.new_commit}",
        }
        for name, source in error.skills
    ]
    try:
        deltas = upstream_deltas(error)
    except QualificationError as fetch_error:
        return [*diagnostics, {"code": "delta_unavailable", "detail": str(fetch_error)}]
    folder = directory / "deltas"
    folder.mkdir(parents=True, exist_ok=True)
    for name, diff in deltas.items():
        (folder / f"{name}.diff").write_text(diff)
    return diagnostics


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
    consumer = subparsers.add_parser("prepare-consumer")
    consumer.add_argument("repository", type=Path)
    consumer.add_argument("source_tag")
    consumer.add_argument("source_commit")
    inventory = subparsers.add_parser("assert-codex-inventory")
    inventory.add_argument("repository", type=Path)
    inventory.add_argument("source_tag")
    inventory.add_argument("source_commit")
    proposal = subparsers.add_parser("reconcile-draft-pr")
    proposal.add_argument("repository", type=Path)
    proposal.add_argument("--branch", required=True)
    proposal.add_argument("--title", required=True)
    proposal.add_argument("--body-file", type=Path, required=True)
    proposal.add_argument("--commit-message", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
    except SystemExit as error:
        return int(error.code)
    try:
        if args.command == "reconcile-draft-pr":
            reconcile_draft_pr(
                args.repository,
                branch=args.branch,
                title=args.title,
                body=args.body_file.read_text(),
                commit_message=args.commit_message,
            )
            return 0
        if args.command == "prepare-consumer":
            prepare_consumer(args.repository, args.source_tag, args.source_commit)
            return 0
        if args.command == "assert-codex-inventory":
            assert_codex_inventory(args.repository, args.source_tag, args.source_commit)
            return 0
        if args.command == "release-check":
            validate_release_candidate(args.package, args.tag)
            return 0
        mode = "update" if args.command == "update" else "locked"
        result = qualify(args.package, mode, args.summary)
    except PortRequiredError as error:
        print(error, file=sys.stderr)
        directory = args.package.resolve().parent / "artifacts" / f"{args.package.name}-deltas"
        for item in write_deltas(directory, error):
            print(f"  {item.get('path', item['code'])}: {item['detail']}", file=sys.stderr)
        print(f"deltas: {directory / 'deltas'}", file=sys.stderr)
        return 5
    except ConfigurationError as error:
        print(error, file=sys.stderr)
        return 2
    except BreakingDriftError as error:
        print(error, file=sys.stderr)
        return 3
    except (QualificationError, GitHubError, OSError, ValueError) as error:
        print(error, file=sys.stderr)
        return 4
    if result.summary:
        print(result.summary, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
