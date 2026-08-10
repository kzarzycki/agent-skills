from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

PIPELINE = "engineering-upstream-refresh"
SECRET_ASSIGNMENT = re.compile(
    r"(?im)^.*\b(?:authorization|token|secret|password|private[_ -]?key)\s*[:=].*$"
)
GITHUB_TOKEN = re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,})\b")
CREDENTIAL_URL = re.compile(r"(https?://)[^/@\s]+:[^/@\s]+@")
PRIVATE_KEY = re.compile(
    r"-----BEGIN [^-]*PRIVATE KEY-----.*?-----END [^-]*PRIVATE KEY-----",
    re.DOTALL,
)
SENSITIVE_KEYS = {"authorization", "token", "secret", "password", "private_key"}


def new_attempt(previous_commit: str | None) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "pipeline": PIPELINE,
        "outcome": "internal_error",
        "code": "bootstrap_incomplete",
        "phase": "resolve",
        "source_tag": None,
        "source_commit": None,
        "previous_commit": previous_commit,
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


def sanitize(value: str) -> str:
    value = PRIVATE_KEY.sub("[redacted private key]", value)
    value = CREDENTIAL_URL.sub(r"\1[redacted]@", value)
    value = GITHUB_TOKEN.sub("[redacted token]", value)
    return SECRET_ASSIGNMENT.sub("[redacted]", value)[:4000]


def _redact(value: Any, key: str | None = None) -> Any:
    if key and key.lower() in SENSITIVE_KEYS:
        return "[redacted]"
    if isinstance(value, str):
        return sanitize(value)
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, dict):
        return {name: _redact(item, str(name)) for name, item in value.items()}
    return value


def write_result(directory: Path, result: dict[str, Any]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    normalized = _redact(json.loads(json.dumps(result)))
    (directory / "result.json").write_text(json.dumps(normalized, indent=2, sort_keys=True) + "\n")
    (directory / "summary.md").write_text(render_summary(normalized))


def load_result(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def render_summary(result: dict[str, Any]) -> str:
    delta = result["inventory_delta"]
    names = lambda values: ", ".join(values) if values else "none"
    lines = [
        f"# Engineering upstream refresh: {result['outcome']}",
        "",
        f"- Code: `{result['code']}`",
        f"- Phase: `{result['phase']}`",
        f"- Source: `{result['source_tag'] or 'unresolved'}` / `{result['source_commit'] or 'unresolved'}`",
        f"- Previous commit: `{result['previous_commit'] or 'unresolved'}`",
        f"- Added skills: {names(delta['added'])}",
        f"- Removed skills: {names(delta['removed'])}",
        f"- Changed skills: {names(delta['changed'])}",
        f"- Proposed package version: `{result['proposed_version'] or 'none'}`",
        "",
        "## Gates",
        "",
    ]
    gates = result.get("gates", [])
    lines.extend(
        f"- {gate['name']}: **{gate['status']}**"
        + (f" — {gate['detail']}" if gate.get("detail") else "")
        for gate in gates
    )
    if not gates:
        lines.append("- none")
    if result.get("diagnostics"):
        lines.extend(["", "## Diagnostics", ""])
        lines.extend(
            f"- `{item['code']}`" + (f" at `{item['path']}`" if item.get("path") else "")
            for item in result["diagnostics"]
        )
    lines.extend(["", "## Next action", ""])
    if result["outcome"] == "qualified":
        version = result.get("proposed_version")
        if version and result.get("source_tag") and result.get("source_commit"):
            package_tag = f"engineering-v{version}"
            lines.extend(
                [
                    f"Review the draft, merge it, and create `{package_tag}` after its checks pass.",
                    f"The consumer PR must set the root APM ref exactly to `{package_tag}`.",
                    "Run `mise run agent-sync --refresh` after merging the consumer PR.",
                    (
                        f"Resolve `PACKAGE_COMMIT=$(git rev-parse {package_tag}^{{commit}})`, then "
                        "verify Codex with `mise run assert-engineering-codex-inventory -- "
                        f'{package_tag} "$PACKAGE_COMMIT"`.'
                    ),
                ]
            )
        else:
            lines.append(
                "Review the publishing canary; it must remain draft and must not be merged."
            )
    elif result["outcome"] == "no_update":
        lines.append("No maintainer action is required.")
    else:
        lines.append("Resolve the recorded diagnostic and rerun this workflow.")
    return "\n".join(lines) + "\n"
