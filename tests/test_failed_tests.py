"""tools/failed_tests.py: the `failed-tests` artifact `qualify` publishes for the gatekeeper's break-glass proof."""

from __future__ import annotations

import json
from pathlib import Path

from tools import failed_tests

JUNIT = """<testsuites><testsuite name="pytest">
<testcase classname="tests.test_a" name="test_ok"/>
<testcase classname="tests.test_a" name="test_bad"><failure message="x">boom</failure></testcase>
<testcase classname="tests.test_b" name="test_err"><error message="y"/></testcase>
<testcase classname="tests.test_b" name="test_skip"><skipped/></testcase>
</testsuite></testsuites>"""


def test_failures_and_errors_are_failed_and_every_case_is_selected(tmp_path: Path) -> None:
    junit = tmp_path / "junit.xml"
    junit.write_text(JUNIT)
    out = tmp_path / "out" / "failed-tests.json"
    assert failed_tests.main([str(junit), str(out)]) == 0
    assert json.loads(out.read_text()) == {
        "failed": ["tests.test_a::test_bad", "tests.test_b::test_err"],
        "selected": [
            "tests.test_a::test_ok",
            "tests.test_a::test_bad",
            "tests.test_b::test_err",
            "tests.test_b::test_skip",
        ],
    }


def test_a_run_whose_tests_never_started_publishes_two_empty_lists(tmp_path: Path) -> None:
    out = tmp_path / "failed-tests.json"
    assert failed_tests.main([str(tmp_path / "missing.xml"), str(out)]) == 0
    assert json.loads(out.read_text()) == {"failed": [], "selected": []}


def test_it_wants_an_input_and_an_output() -> None:
    assert failed_tests.main(["only-one"]) == 2
