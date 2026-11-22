"""A ``Waits:`` set is read wherever it sits in a STILL WORKING turn (#1613)."""

from test_omnigent_agent import omnigent_agent as oa

A, B = "a" * 32, "b" * 32
SET = [("session", A), ("session", B)]


def test_waits_before_still_working_reads_both():
    t = f"x\n\nWaits: session {A} and session {B}\nSTILL WORKING: waiting on {A} (x) and {B} (y). Report: /r.md"
    assert oa.trailer_items(t) == SET
    assert oa.wait_of(t) == f"{A}, {B}"


def test_waits_after_still_working_unchanged():
    t = f"STILL WORKING: waiting on {A} (x) and {B} (y). Report: /r.md\nWaits: session {A} and session {B}"
    assert oa.trailer_items(t) == SET
    assert oa.wait_of(t) == f"{A}, {B}"


def test_prose_only_multi_id_returns_the_set():
    t = f"STILL WORKING: waiting on {A} (x) and {B} (y). Report: /r.md"
    assert oa.trailer_items(t) == []
    assert oa.wait_of(t) == f"{A}, {B}"


def test_single_id_unchanged():
    assert oa.wait_of(f"STILL WORKING: waiting on {A} (x). Report: /r.md") == A
    t = f"Waits: session {A}\nSTILL WORKING: waiting on {A}. Report: /r.md"
    assert oa.wait_of(t) == A


def test_no_still_working_reads_no_waits():
    assert oa.trailer_items(f"Waits: session {A}") == []


def test_preamble_places_waits_after_the_ending_line():
    assert "followed by a last line `Waits:" in oa.LEAD_PREAMBLE
