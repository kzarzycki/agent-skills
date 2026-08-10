from __future__ import annotations

import json

from tools.capability_pack.outcome import new_attempt, write_result


def test_result_and_summary_are_deterministic_and_redacted(tmp_path) -> None:
    result = new_attempt(None)
    result["diagnostics"] = [
        {"code": "bootstrap_failure", "detail": "Authorization: token secret-value"}
    ]
    write_result(tmp_path, result)
    first = (tmp_path / "result.json").read_bytes(), (tmp_path / "summary.md").read_bytes()
    write_result(tmp_path, result)
    second = (tmp_path / "result.json").read_bytes(), (tmp_path / "summary.md").read_bytes()
    assert first == second
    stored = json.loads(first[0])
    assert stored["source_tag"] is None
    assert "secret-value" not in first[0].decode()
    assert stored["diagnostics"][0]["detail"] == "[redacted]"


def test_redaction_is_recursive_and_covers_gate_output_and_urls(tmp_path) -> None:
    result = new_attempt(None)
    result["gates"] = [
        {
            "name": "tests",
            "status": "fail",
            "detail": "password=hunter2\nhttps://user:pass@example.test/path\nghp_abcdefghijklmnopqrstuvwxyz",
        }
    ]
    result["diagnostics"] = [{"code": "failure", "nested": {"token": "raw"}}]
    write_result(tmp_path, result)
    serialized = (tmp_path / "result.json").read_text()
    assert all(value not in serialized for value in ("hunter2", "user:pass", "ghp_", '"raw"'))
    assert "[redacted]" in serialized


def test_qualified_summary_contains_exact_release_handoff(tmp_path) -> None:
    result = new_attempt("1" * 40)
    result.update(
        outcome="qualified",
        code="candidate_qualified",
        source_tag="v1.2.4",
        source_commit="2" * 40,
        proposed_version="0.4.0",
    )
    write_result(tmp_path, result)
    summary = (tmp_path / "summary.md").read_text()
    assert "`engineering-v0.4.0`" in summary
    assert "root APM ref exactly to `engineering-v0.4.0`" in summary
    assert "`mise run agent-sync --refresh`" in summary
    assert "`PACKAGE_COMMIT=$(git rev-parse engineering-v0.4.0^{commit})`" in summary
    assert (
        '`mise run assert-engineering-codex-inventory -- engineering-v0.4.0 "$PACKAGE_COMMIT"`'
        in summary
    )
    assert "2" * 40 not in summary.split("verify Codex", 1)[-1]
