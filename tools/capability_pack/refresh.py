from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

import yaml

from tools.capability_pack.outcome import new_attempt, write_result
from tools.capability_pack.provenance import load_provenance
from tools.capability_pack.qualify import (
    LicenseDriftError,
    PatchError,
    QualificationError,
    qualify,
)
from tools.capability_pack.releases import ReleaseResolutionError, resolve_release

GATES = (
    ("locked-vendoring", ("mise", "run", "vendor-engineering-check")),
    ("repository-tests", ("mise", "run", "test")),
    ("package-tests", ("mise", "run", "test-engineering-package")),
    ("whitespace", ("git", "diff", "--check")),
)


def _run_gate(repository: Path, command: tuple[str, ...]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=repository,
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )


def _restore_package(package: Path, backup: Path) -> None:
    shutil.rmtree(package)
    shutil.copytree(backup, package, symlinks=True)


def refresh(
    package: Path,
    artifact_directory: Path,
    *,
    gate_runner=_run_gate,
) -> tuple[dict, int]:
    attempt = new_attempt(None)
    try:
        try:
            previous = load_provenance(package / "provenance.yml")
        except (OSError, KeyError, TypeError, ValueError, yaml.YAMLError) as error:
            attempt.update(outcome="blocked", code="provenance_invalid", phase="resolve")
            attempt["diagnostics"].append({"code": "provenance_invalid", "detail": str(error)})
            write_result(artifact_directory, attempt)
            return attempt, 1
        attempt["previous_commit"] = previous.source_commit
        policy = yaml.safe_load((package / "upstream.yml").read_text())
        selection = resolve_release(
            policy["repository"],
            previous.source_commit,
            policy["stable_tag_pattern"],
        )
        attempt.update(source_tag=selection.tag, source_commit=selection.commit)
        if selection.state in {"no_update", "no_eligible_update"}:
            attempt.update(
                outcome="no_update",
                code=selection.state,
                phase="resolve",
            )
            write_result(artifact_directory, attempt)
            return attempt, 0
        attempt["phase"] = "stage"
        backup_root = Path(tempfile.mkdtemp(prefix="capability-pack-refresh-backup-"))
        backup = backup_root / package.name
        shutil.copytree(package, backup, symlinks=True)
        promoted = False
        try:
            result = qualify(
                package,
                "update",
                source_tag=selection.tag,
                candidate_commit=selection.commit,
            )
            promoted = True
            gates = []
            for name, command in GATES:
                try:
                    completed = gate_runner(package.parent, command)
                    detail = None
                    status = "pass" if completed.returncode == 0 else "fail"
                    if completed.returncode:
                        detail = (completed.stderr or completed.stdout or "gate failed").strip()
                except Exception as error:  # noqa: BLE001 - every gate must leave evidence.
                    status = "fail"
                    detail = str(error)
                gates.append({"name": name, "status": status, "detail": detail})
            failed = [gate for gate in gates if gate["status"] == "fail"]
            if failed:
                _restore_package(package, backup)
                promoted = False
                attempt.update(
                    outcome="blocked",
                    code="gate_failed",
                    phase="qualify",
                    proposed_version=result.proposed_version,
                    inventory_delta={
                        "added": list(result.added_skills),
                        "removed": list(result.removed_skills),
                        "changed": list(result.changed_skills),
                    },
                    gates=gates,
                )
                attempt["diagnostics"].extend(
                    {
                        "code": "gate_failed",
                        "path": gate["name"],
                        "detail": gate["detail"],
                    }
                    for gate in failed
                )
                write_result(artifact_directory, attempt)
                return attempt, 1
        except Exception:
            if promoted:
                _restore_package(package, backup)
            raise
        finally:
            shutil.rmtree(backup_root, ignore_errors=True)
        attempt.update(
            outcome="qualified",
            code="candidate_qualified",
            phase="qualify",
            proposed_version=result.proposed_version,
            inventory_delta={
                "added": list(result.added_skills),
                "removed": list(result.removed_skills),
                "changed": list(result.changed_skills),
            },
            gates=gates,
        )
        write_result(artifact_directory, attempt)
        return attempt, 0
    except ReleaseResolutionError as error:
        attempt.update(
            outcome="blocked",
            code=error.code,
            phase="resolve",
        )
        attempt["diagnostics"].append({"code": error.code, "detail": str(error)})
    except PatchError as error:
        attempt.update(outcome="blocked", code="patch_rejected", phase="patch")
        attempt["diagnostics"].append(
            {"code": "patch_rejected", "path": error.patch, "detail": error.detail}
        )
    except LicenseDriftError as error:
        attempt.update(outcome="blocked", code="license_drift", phase="qualify")
        attempt["diagnostics"].append({"code": "license_drift", "detail": str(error)})
    except (QualificationError, OSError, ValueError, KeyError, TypeError, yaml.YAMLError) as error:
        attempt.update(outcome="blocked", code="qualification_failed", phase="qualify")
        attempt["gates"].append({"name": "package-tests", "status": "fail", "detail": str(error)})
        attempt["diagnostics"].append({"code": "qualification_failed", "detail": str(error)})
    except Exception as error:  # noqa: BLE001 - evidence must survive unknown tool failures.
        attempt.update(outcome="internal_error", code="internal_error", phase=attempt["phase"])
        attempt["diagnostics"].append({"code": "internal_error", "detail": str(error)})
    write_result(artifact_directory, attempt)
    return attempt, 1
