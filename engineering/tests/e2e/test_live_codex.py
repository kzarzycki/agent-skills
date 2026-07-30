from __future__ import annotations

import pytest

from engineering.tests.e2e.live_contract import exercise_live_agent

pytestmark = pytest.mark.live_agent


def test_codex_engineering_pack_conformance() -> None:
    exercise_live_agent("codex")
