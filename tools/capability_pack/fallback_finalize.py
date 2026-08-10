"""Dependency-free report finalization for workflow bootstrap failures."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def _empty() -> dict:
    return {
        "schema_version": 1,
        "pipeline": "engineering-upstream-refresh",
        "outcome": "internal_error",
        "code": "report_bootstrap_failed",
        "phase": "publish",
        "source_tag": None,
        "source_commit": None,
        "previous_commit": None,
        "inventory_delta": {"added": [], "removed": [], "changed": []},
        "proposed_version": None,
        "gates": [],
        "diagnostics": [],
        "publication": {
            "state": "not_requested",
            "branch": None,
            "pull_request": None,
            "attempts": [],
        },
        "reporting": {"issue": "not_needed", "issue_number": None},
    }


def finalize(result_path: Path, summary_path: Path) -> None:
    try:
        result = json.loads(result_path.read_text())
        if not isinstance(result, dict):
            raise TypeError("result is not an object")
    except (
        OSError,
        ValueError,
        TypeError,
    ):
        result = _empty()
    result.update(outcome="internal_error", code="report_bootstrap_failed", phase="publish")
    diagnostics = result.setdefault("diagnostics", [])
    if not any(item.get("code") == "report_bootstrap_failed" for item in diagnostics):
        diagnostics.append({"code": "report_bootstrap_failed"})
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    summary_path.write_text(
        "# Engineering upstream refresh: internal_error\n\n"
        "- Code: `report_bootstrap_failed`\n"
        "- Phase: `publish`\n\n"
        "The reporting toolchain failed to bootstrap; inspect the workflow log.\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("result", type=Path)
    parser.add_argument("summary", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        try:
            result = json.loads(args.result.read_text())
        except (
            OSError,
            ValueError,
        ):
            return 1
        return 1 if result.get("code") == "report_bootstrap_failed" else 0
    finalize(args.result, args.summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
