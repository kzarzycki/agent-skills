# Update Delta Audit Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a portable `update-delta-audit` skill that performs cheap pre-install delta audits for software update prompts.

**Architecture:** The spike is skill-first. `SKILL.md` holds the core workflow and escalation rules; references hold reusable update-pattern/report details; scripts provide deterministic metadata helpers for hashing and macOS app provenance without running installers.

**Tech Stack:** Markdown skill package, JSON eval prompts, Python stdlib helper tests/scripts, POSIX shell metadata helper.

---

## Files
- Create: `update-delta-audit-spike/update-delta-audit/SKILL.md` — trigger description and cheap delta-audit workflow.
- Create: `update-delta-audit-spike/update-delta-audit/references/updater-patterns.md` — OMP/npm-style, Sparkle/macOS, GitHub release, package-manager checks.
- Create: `update-delta-audit-spike/update-delta-audit/references/report-template.md` — exact report template.
- Create: `update-delta-audit-spike/update-delta-audit/scripts/hash-artifact.py` — SHA-256 helper that emits JSON.
- Create: `update-delta-audit-spike/update-delta-audit/scripts/macos-app-provenance.sh` — codesign/spctl/xattr/plist metadata helper for `.app` bundles on macOS.
- Create: `update-delta-audit-spike/tests/test_hash_artifact.py` — unit tests for hash helper.
- Create: `update-delta-audit-spike/evals/evals.json` — OMP, Orca/StablyAI, and package-manager eval prompts.

### Task 1: Hash helper test and implementation

**Files:**
- Create: `update-delta-audit-spike/tests/test_hash_artifact.py`
- Create: `update-delta-audit-spike/update-delta-audit/scripts/hash-artifact.py`

- [ ] **Step 1: Write failing tests**

```python
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "update-delta-audit" / "scripts" / "hash-artifact.py"


def run_hash(*paths: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *(str(path) for path in paths)],
        text=True,
        capture_output=True,
        check=False,
    )


def test_hash_artifact_emits_json_for_file(tmp_path: Path):
    artifact = tmp_path / "artifact.bin"
    artifact.write_bytes(b"update artifact\n")

    result = run_hash(artifact)

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload == [
        {
            "path": str(artifact),
            "bytes": 16,
            "sha256": "8e662d4bc8c7a6f55fe4b574a24f83f9b5b9fe3473c30e76cf00b7c525d55602",
        }
    ]


def test_hash_artifact_fails_for_missing_file(tmp_path: Path):
    missing = tmp_path / "missing.tar.gz"

    result = run_hash(missing)

    assert result.returncode == 2
    assert "not a regular file" in result.stderr
```

- [ ] **Step 2: Run tests to verify RED**

Run: `python3 -m unittest discover -s update-delta-audit-spike/tests -v`

Expected: FAIL because `hash-artifact.py` does not exist.

- [ ] **Step 3: Implement helper**

Create `hash-artifact.py` with argv validation, streaming SHA-256, and JSON array output.

- [ ] **Step 4: Run tests to verify GREEN**

Run: `python3 -m unittest discover -s update-delta-audit-spike/tests -v`

Expected: PASS.

### Task 2: Skill and references

**Files:**
- Create: `update-delta-audit-spike/update-delta-audit/SKILL.md`
- Create: `update-delta-audit-spike/update-delta-audit/references/updater-patterns.md`
- Create: `update-delta-audit-spike/update-delta-audit/references/report-template.md`
- Create: `update-delta-audit-spike/update-delta-audit/scripts/macos-app-provenance.sh`

- [ ] **Step 1: Draft SKILL.md**

Include frontmatter:

```yaml
---
name: update-delta-audit
description: Cheap pre-install safety audit for software update prompts by inspecting only the delta between installed and candidate versions. Use when a user sees "update available", "new version available", "run <tool> update", app updater prompts, package-manager upgrade prompts, or asks whether an update is safe before installing; prefer this over full third-party audits when the software is already installed and trusted.
---
```

- [ ] **Step 2: Add workflow and escalation rules**

Mirror `SPEC.md`: capture versions, identify updater without installing, fetch metadata/artifacts, diff changed surfaces, provenance checks, verdicts.

- [ ] **Step 3: Add references**

Add updater-specific checklists and exact report template.

- [ ] **Step 4: Add macOS provenance helper**

Shell script should inspect an existing `.app` path only; no network and no install. It runs `codesign`, `spctl`, `xattr`, `plutil`, and `/usr/libexec/PlistBuddy` when available.

### Task 3: Evals and final verification

**Files:**
- Create: `update-delta-audit-spike/evals/evals.json`

- [ ] **Step 1: Add three eval prompts**

Include OMP `15.10.4`, Orca/StablyAI macOS app `Xyz`, and package-manager lockfile delta.

- [ ] **Step 2: Static self-check**

Run: `python3 -m json.tool update-delta-audit-spike/evals/evals.json`

Expected: valid JSON echoed.

- [ ] **Step 3: Final test**

Run: `python3 -m unittest discover -s update-delta-audit-spike/tests -v`

Expected: PASS.
