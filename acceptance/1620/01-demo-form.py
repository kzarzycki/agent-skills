#!/usr/bin/env python3
"""#1620 Before merge line 2: demo_form takes a fixture PR whose `## Demo` comment links the repo's own sha blob
`?raw=true` (exit 0), and refuses one that links another repo's blob (exit 1). Synthetic data, no network."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "gatekeeper", ROOT / "engineering/skills/engineering-loop/scripts/gatekeeper.py"
)
gatekeeper = importlib.util.module_from_spec(SPEC)
sys.modules["gatekeeper"] = gatekeeper
SPEC.loader.exec_module(gatekeeper)

REPO, SHA = "example-owner/example-repo", "0123456789abcdef0123456789abcdef01234567"


def refused(repo: str) -> list[str]:
    body = f"## Demo\n\nthe card.\nhttps://github.com/{repo}/blob/{SHA}/card.png?raw=true\n"
    comment = {"body": body, "author": {"login": "worker"}, "isMinimized": False}
    pull = {
        "number": 1,
        "author": {"login": "worker"},
        "baseRepository": {"nameWithOwner": REPO},
        "comments": {"nodes": [comment]},
    }
    return gatekeeper.demo_form(pull)


own, other = refused(REPO), refused("example-owner/other-repo")
print("own repo:", own or "accepted")
print("other repo:", other or "accepted")
sys.exit(0 if not own and other else 1)
