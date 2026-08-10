from __future__ import annotations

import json

from tools.capability_pack.fallback_finalize import finalize
from tools.capability_pack.outcome import new_attempt, write_result


def test_bootstrap_fallback_preserves_evidence_and_marks_internal_error(tmp_path) -> None:
    result = new_attempt("1" * 40)
    result.update(outcome="qualified", code="candidate_qualified", source_tag="v1.2.4")
    write_result(tmp_path, result)
    finalize(tmp_path / "result.json", tmp_path / "summary.md")
    stored = json.loads((tmp_path / "result.json").read_text())
    assert stored["outcome"] == "internal_error"
    assert stored["code"] == "report_bootstrap_failed"
    assert stored["source_tag"] == "v1.2.4"
    assert stored["diagnostics"][-1] == {"code": "report_bootstrap_failed"}
    assert "report_bootstrap_failed" in (tmp_path / "summary.md").read_text()
