"""The shareable Renovate presets for the pack pin in apm.yml (#2766).

Renovate reads each regex with RE2 and fills `{{{group}}}` templates from the match groups; the
test applies both to fixture `apm.yml` text and fixture tags the way a lookup does, and orders
the surviving tags as Renovate's semver versioning does (a prerelease sorts below its release
and above the release before it).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1] / "renovate"
TAGS = [
    "engineering-v0.35.12",
    "engineering-v0.35.13-next",
    "engineering-v0.35.14-next",
    "engineering-v0.35.14",
    "engineering-v0.36.0-next",
    "omnigent-v0.1.21-next",
    "engineering-v0.35.12-rc1",
    "gatekeeper-v0.1.15",
    "gatekeeper-v0.1.16",
    "loop-v0.1.9-next",
    "loop-v0.1.10",
    "engineering-hooks-v0.1.0-next",
]
APM = """dependencies:
  apm:
  - git: kzarzycki/agent-skills/{package}
    ref: {ref}
  mcp: []
"""


def manager(line: str) -> dict:
    return json.loads((ROOT / f"{line}.json").read_text())["customManagers"][0]


def py(regex: str) -> str:
    """RE2 names a group `(?<n>`; Python names it `(?P<n>`."""
    return re.sub(r"\(\?<(\w+)>", r"(?P<\1>", regex)


def extract(line: str, ref: str, package: str = "engineering") -> dict | None:
    for pattern in manager(line)["matchStrings"]:
        hit = re.search(py(pattern), APM.format(ref=ref, package=package), re.MULTILINE)
        if hit:
            return hit.groupdict()
    return None


def version(v: str) -> tuple:
    core, _, pre = v.partition("-")
    return (*map(int, core.split(".")), pre == "")  # a prerelease sorts below its release


def newest(line: str, package: str) -> str:
    pattern = py(manager(line)["extractVersionTemplate"].replace("{{{package}}}", package))
    found = [m.group("version") for t in TAGS if (m := re.match(pattern, t))]
    return max(found, key=version) if found else None


@pytest.mark.parametrize("line", ["stable", "next"])
def test_preset_extracts_the_pin(line):
    m = extract(line, "engineering-v0.35.5")
    assert m
    assert (m["owner"], m["repo"], m["package"], m["currentValue"]) == (
        "kzarzycki",
        "agent-skills",
        "engineering",
        "0.35.5",
    )


PINS = [
    ("engineering", "0.35.10"),
    ("gatekeeper", "0.1.16"),
    ("loop", "0.1.10"),
    ("engineering-hooks", "0.1.0"),
]


@pytest.mark.parametrize("line", ["stable", "next"])
@pytest.mark.parametrize(("package", "current"), PINS)
def test_any_package_pin_is_extracted(line, package, current):
    m = extract(line, f"{package}-v{current}", package)
    assert m
    assert (m["owner"], m["repo"], m["package"], m["currentValue"]) == (
        "kzarzycki",
        "agent-skills",
        package,
        current,
    )


def test_next_pin_of_a_package_with_only_next_tags():
    assert extract("stable", "engineering-hooks-v0.1.0-next", "engineering-hooks") is None
    m = extract("next", "engineering-hooks-v0.1.0-next", "engineering-hooks")
    assert m["package"] == "engineering-hooks"
    assert m["currentValue"] == "0.1.0-next"


def test_package_newest_tags_per_line():
    assert newest("stable", "gatekeeper") == newest("next", "gatekeeper") == "0.1.16"
    assert newest("stable", "loop") == "0.1.10"
    assert newest("next", "loop") == "0.1.10"  # the stable release sorts above its own -next
    assert newest("stable", "engineering-hooks") is None  # only a -next tag exists
    assert newest("next", "engineering-hooks") == "0.1.0-next"
    assert (
        newest("next", "engineering") == "0.36.0-next"
    )  # engineering-hooks tags are not engineering's


def test_stable_ignores_a_next_pin():
    assert extract("stable", "engineering-v0.35.5-next") is None


def test_next_extracts_a_next_pin():
    assert extract("next", "engineering-v0.35.5-next")["currentValue"] == "0.35.5-next"


def test_stable_tags_only():
    assert newest("stable", "engineering") == "0.35.14"
    pattern = py(
        manager("stable")["extractVersionTemplate"].replace("{{{package}}}", "engineering")
    )
    assert not any(re.match(pattern, t) for t in TAGS if t.endswith("-next"))


def test_next_picks_a_next_tag_over_an_older_stable_one():
    assert newest("next", "engineering") == "0.36.0-next"
    older = [t for t in TAGS if t != "engineering-v0.36.0-next"]
    assert (
        max(
            (t.split("-v")[1] for t in older if t.startswith("engineering-v") and "rc" not in t),
            key=version,
        )
        == "0.35.14"
    )


def test_a_package_ignores_other_packages_tags():
    assert newest("next", "loop") == "0.1.10"
    assert newest("next", "omnigent") == "0.1.21-next"


def test_next_lifts_the_unstable_filter():
    rules = json.loads((ROOT / "next.json").read_text())["packageRules"]
    assert any(r.get("ignoreUnstable") is False for r in rules)
    assert "packageRules" not in json.loads((ROOT / "stable.json").read_text())
