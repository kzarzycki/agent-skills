"""pytest's per-test limit from gatekeeper.md's `timeouts.test`, so pyproject.toml holds no limit of its own (#2232).

pytest-timeout reads `PYTEST_TIMEOUT` when it configures, so this plugin sets it first, and an explicit `--timeout`, the
variable or a test's own `@pytest.mark.timeout` still wins. A policy that can't be read leaves pytest-timeout's default
(none), never a made-up limit."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
GATEKEEPER = ROOT / "gatekeeper" / "skills" / "gatekeeper" / "scripts"


def test_limit() -> int | None:
    """`timeouts.test` in seconds from this checkout's gatekeeper.md, None when it can't be read."""
    try:
        sys.path.insert(0, str(GATEKEEPER))
        import approvals

        policy = approvals.Policy((ROOT / "docs" / "agents" / "gatekeeper.md").read_text())
        return approvals.timeouts(policy)["test"]
    except Exception:  # noqa: BLE001 -- an unreadable policy sets no limit; the policy's own tests fail on it
        return None
    finally:
        if str(GATEKEEPER) in sys.path:
            sys.path.remove(str(GATEKEEPER))


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config: pytest.Config) -> None:
    if os.environ.get("PYTEST_TIMEOUT") or config.getoption("timeout", None) is not None:
        return
    if (seconds := test_limit()) is not None:
        os.environ["PYTEST_TIMEOUT"] = str(seconds)
