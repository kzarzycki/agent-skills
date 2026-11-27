from __future__ import annotations

import argparse
import os
import shutil
import sys
from collections.abc import Sequence
from pathlib import Path

from tools.capability_pack.consumer import assert_codex_inventory, prepare_consumer
from tools.capability_pack.github import GitHubError, reconcile_draft_pr
from tools.capability_pack.qualify import (
    SMOKE_REPOSITORY,
    BreakingDriftError,
    ConfigurationError,
    PortRequiredError,
    QualificationError,
    QualificationTimeoutError,
    _git_output,
    qualify,
    require_smoke_run,
    upstream_deltas,
    validate_release_candidate,
)
from tools.capability_pack.release import (
    MAGNITUDES,
    check_changelog_names,
    cut_release,
    release_tags,
    verify_release,
)

# EX_CONFIG: this machine isn't ready. A step that stops on QUALIFY_TIMEOUT failed for the
# host's load, not the change, so a loop.md naming it as machine_exit has local-ci refuse it as a
# machine fault, never a red gate.
MACHINE_EXIT = 78


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
    for command in ("update", "check", "regenerate"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("package", type=Path)
        subparser.add_argument("--summary", type=Path)
    release = subparsers.add_parser("release-check")
    release.add_argument("package", type=Path)
    release.add_argument("tag")
    release.add_argument(
        "--skip-smoke",
        action="store_true",
        help="the tag check's run: the smoke run gated the release before the tag was pushed",
    )
    cut = subparsers.add_parser(
        "cut-release",
        help="fold every package's changelog.d into its CHANGELOG.md and set its version; commits nothing",
    )
    cut.add_argument("--root", type=Path, default=Path("."))
    cut.add_argument("--magnitude", choices=MAGNITUDES, default="patch")
    cut.add_argument("--dry-run", action="store_true", help="print the releases, write nothing")
    verify = subparsers.add_parser(
        "release-verify", help="refuse unless HEAD is exactly the release cut of --base"
    )
    verify.add_argument("--root", type=Path, default=Path("."))
    verify.add_argument("--base", required=True)
    verify.add_argument("--head", default="HEAD")
    names = subparsers.add_parser(
        "changelog-check", help="refuse a changelog.d entry not named <issue>.md, as the cut does"
    )
    names.add_argument("--root", type=Path, default=Path("."))
    tags = subparsers.add_parser(
        "release-tags", help="print the tag of each package whose manifest HEAD changes"
    )
    tags.add_argument("--root", type=Path, default=Path("."))
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
        if args.command == "changelog-check":
            check_changelog_names(args.root)
            return 0
        if args.command in ("cut-release", "release-verify"):
            if args.command == "cut-release":
                releases = cut_release(args.root, magnitude=args.magnitude, dry_run=args.dry_run)
            else:
                releases = verify_release(args.root, args.base, args.head)
                print(f"{args.head} is the release cut of {args.base}")
            for release in releases:
                issues = " ".join(release.entries)
                print(f"{release.package} {release.version} ({issues})")
                if args.command == "cut-release" and args.dry_run:
                    print(release.section.rstrip("\n"))
            return 0
        if args.command == "release-tags":
            print("\n".join(release_tags(args.root)))
            return 0
        if args.command == "release-check":
            validate_release_candidate(args.package, args.tag)
            if args.skip_smoke:
                print("smoke run: skipped (--skip-smoke); the pre-tag run gated this release")
            elif not os.environ.get(SMOKE_REPOSITORY):
                # ponytail: off until a private organization repository hosts the smoke workflow (#1855)
                print(f"smoke run: off ({SMOKE_REPOSITORY} unset)")
            else:
                head = _git_output(["rev-parse", "HEAD"], cwd=args.package.resolve())
                print(f"smoke run: {require_smoke_run(head)}")
            return 0
        mode = "locked" if args.command == "check" else args.command
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
    except QualificationTimeoutError as error:
        print(error, file=sys.stderr)
        return MACHINE_EXIT
    except (QualificationError, GitHubError, OSError, ValueError) as error:
        print(error, file=sys.stderr)
        return 4
    if result.summary:
        print(result.summary, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
