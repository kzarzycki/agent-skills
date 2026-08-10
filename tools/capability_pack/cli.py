from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from tools.capability_pack.consumer import assert_codex_inventory, prepare_consumer
from tools.capability_pack.github import (
    GitHubError,
    finalize_publication,
    mark_publication,
    normalize_incomplete_publication,
    reconcile_blocked_issue,
    reconcile_draft_pr,
    validate_final_state,
)
from tools.capability_pack.outcome import new_attempt, write_result
from tools.capability_pack.qualify import (
    BreakingDriftError,
    ConfigurationError,
    QualificationError,
    qualify,
    validate_release_candidate,
)
from tools.capability_pack.refresh import refresh


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
    refresh_parser = subparsers.add_parser("refresh")
    refresh_parser.add_argument("package", type=Path)
    refresh_parser.add_argument("--artifacts", type=Path, required=True)
    report = subparsers.add_parser("report")
    report.add_argument("result", type=Path)
    report.add_argument("--run-url", required=True)
    report.add_argument("--artifact-url", required=True)
    publication = subparsers.add_parser("publication")
    publication.add_argument("result", type=Path)
    publication.add_argument("state")
    publication.add_argument("--branch")
    publication.add_argument("--pull-request", type=int)
    consumer = subparsers.add_parser("prepare-consumer")
    consumer.add_argument("repository", type=Path)
    consumer.add_argument("source_tag")
    consumer.add_argument("source_commit")
    inventory = subparsers.add_parser("assert-codex-inventory")
    inventory.add_argument("repository", type=Path)
    inventory.add_argument("source_tag")
    inventory.add_argument("source_commit")
    smoke = subparsers.add_parser("smoke-result")
    smoke.add_argument("--artifacts", type=Path, required=True)
    smoke.add_argument("--marker", type=Path)
    smoke.add_argument("--confirmation")
    finalize = subparsers.add_parser("finalize-publication")
    finalize.add_argument("result", type=Path)
    finalize.add_argument("--mode", required=True)
    finalize.add_argument("--candidate-outcome", required=True)
    finalize.add_argument("--token-outcome", required=True)
    finalize.add_argument("--token-present", action="store_true")
    finalize.add_argument("--proposal-outcome", required=True)
    finalize.add_argument("--branch")
    finalize.add_argument("--pull-request", type=int)
    final_status = subparsers.add_parser("final-status")
    final_status.add_argument("result", type=Path)
    final_status.add_argument("--mode", required=True)
    normalize = subparsers.add_parser("normalize-publication")
    normalize.add_argument("result", type=Path)
    normalize.add_argument("--mode", required=True)
    proposal = subparsers.add_parser("reconcile-draft-pr")
    proposal.add_argument("repository", type=Path)
    proposal.add_argument("--branch", required=True)
    proposal.add_argument("--title", required=True)
    proposal.add_argument("--body-file", type=Path, required=True)
    proposal.add_argument("--commit-message", required=True)
    proposal.add_argument("--result", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
    except SystemExit as error:
        return int(error.code)
    try:
        if args.command == "smoke-result":
            if args.marker and args.confirmation != "PUBLISH-SMOKE":
                result = new_attempt(None)
                result.update(
                    outcome="blocked",
                    code="invalid_smoke_confirmation",
                    phase="publish",
                    diagnostics=[{"code": "invalid_smoke_confirmation"}],
                )
                write_result(args.artifacts, result)
                return 1
            if args.marker:
                args.marker.write_text("engineering upstream publisher smoke\n")
            result = new_attempt(None)
            result.update(
                outcome="qualified",
                code=("publish_smoke_qualified" if args.marker else "smoke_fixture_passed"),
                phase="qualify",
                gates=[{"name": "smoke-marker", "status": "pass", "detail": None}],
            )
            write_result(args.artifacts, result)
            return 0
        if args.command == "finalize-publication":
            finalize_publication(
                args.result,
                mode=args.mode,
                candidate_outcome=args.candidate_outcome,
                token_outcome=args.token_outcome,
                token_present=args.token_present,
                proposal_outcome=args.proposal_outcome,
                branch=args.branch,
                pull_request=args.pull_request,
            )
            return 0
        if args.command == "final-status":
            return 0 if validate_final_state(args.result, args.mode) else 1
        if args.command == "normalize-publication":
            normalize_incomplete_publication(args.result, args.mode)
            return 0
        if args.command == "reconcile-draft-pr":
            result = reconcile_draft_pr(
                args.repository,
                branch=args.branch,
                title=args.title,
                body=args.body_file.read_text(),
                commit_message=args.commit_message,
                result_path=args.result,
            )
            return 0 if result["publication"]["state"] == "draft_ready" else 1
        if args.command == "prepare-consumer":
            prepare_consumer(args.repository, args.source_tag, args.source_commit)
            return 0
        if args.command == "assert-codex-inventory":
            assert_codex_inventory(args.repository, args.source_tag, args.source_commit)
            return 0
        if args.command == "refresh":
            _, exit_code = refresh(args.package, args.artifacts)
            return exit_code
        if args.command == "report":
            result = reconcile_blocked_issue(args.result, args.run_url, args.artifact_url)
            return 1 if result["reporting"]["issue"] == "failed" else 0
        if args.command == "publication":
            mark_publication(
                args.result,
                args.state,
                branch=args.branch,
                pull_request=args.pull_request,
            )
            return 0
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
    except (QualificationError, GitHubError, OSError, ValueError) as error:
        print(error, file=sys.stderr)
        return 4
    if result.summary:
        print(result.summary, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
