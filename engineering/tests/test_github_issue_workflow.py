from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import yaml

PACKAGE = Path(__file__).resolve().parents[1]
TEMPLATE = (
    PACKAGE
    / "skills"
    / "setup-engineering-workflow-for-apm"
    / "templates"
    / "issue-tracker-github.md"
)
FAKE_GH = Path(__file__).parent / "fixtures" / "fake-gh"
PROTOCOL_PATTERN = re.compile(
    r"<!-- github-issue-batch-fixture-protocol\n(?P<protocol>.*?)\n-->",
    re.DOTALL,
)
TICKETS = [
    {
        "order": 1,
        "title": "Expose account status",
        "body": "Return the current account status from the API.",
        "labels": ["ready-for-agent", "api"],
        "blockers": [],
    },
    {
        "order": 2,
        "title": "Render account status",
        "body": "Show the account status in the dashboard.",
        "labels": ["frontend", "ready-for-agent"],
        "blockers": [1],
    },
    {
        "order": 3,
        "title": "Alert on account status",
        "body": "Notify operators when the account status changes.",
        "labels": ["ready-for-agent"],
        "blockers": [1],
    },
]


@dataclass
class RunResult:
    events: list[tuple[str, str]]
    output: list[str]
    returncode: int


def _load_protocol() -> dict:
    match = PROTOCOL_PATTERN.search(TEMPLATE.read_text())
    assert match, "GitHub tracker template must declare its batch fixture protocol"
    protocol = yaml.safe_load(match.group("protocol"))
    assert protocol["version"] == 1
    return protocol


def _canonical_batch(tickets: list[dict], protocol: dict) -> bytes:
    fields = protocol["canonical_fields"]
    canonical = [
        {field: sorted(ticket[field]) if field == "labels" else ticket[field] for field in fields}
        for ticket in tickets
    ]
    return json.dumps(
        canonical,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()


def _render_review(tickets: list[dict], markers: list[str]) -> list[str]:
    lines = ["Proposed GitHub Issue batch:"]
    for ticket, marker in zip(tickets, markers, strict=True):
        lines.extend(
            [
                f"{ticket['order']}. {ticket['title']}",
                f"   Body: {ticket['body']}",
                f"   Marker: {marker}",
                f"   Labels: {', '.join(ticket['labels'])}",
                "   Blocked by: " + (", ".join(map(str, ticket["blockers"])) or "None"),
            ]
        )
    return lines


def _run_batch(
    tmp_path: Path,
    *,
    approval: bool | None,
    fail_after: int = 0,
) -> RunResult:
    protocol = _load_protocol()
    batch_sha256 = hashlib.sha256(_canonical_batch(TICKETS, protocol)).hexdigest()
    markers = [
        protocol["marker"].format(
            batch_sha256=batch_sha256,
            ordinal=ticket["order"],
        )
        for ticket in TICKETS
    ]
    output = _render_review(TICKETS, markers)
    events = [("review", "\n".join(output))]
    prompt = protocol["approval_prompt"]
    output.append(prompt)
    events.append(("approval", "requested"))
    if approval is not True:
        events.append(("approval", "rejected" if approval is False else "pending"))
        return RunResult(events, output, 0)

    environment = os.environ.copy()
    environment.update(
        {
            "FAKE_GH_LOG": str(tmp_path / "gh.log"),
            "FAKE_GH_STATE": str(tmp_path / "gh-state.json"),
            "FAKE_GH_FAIL_AFTER": str(fail_after),
        }
    )
    urls: list[str | None] = []
    for marker in markers:
        command = [
            str(FAKE_GH),
            "issue",
            "list",
            "--state",
            "all",
            "--search",
            marker,
            "--json",
            "url,body",
        ]
        events.append(("gh", " ".join(command[1:])))
        search = subprocess.run(
            command,
            check=True,
            capture_output=True,
            env=environment,
            text=True,
        )
        matches = [item["url"] for item in json.loads(search.stdout) if marker in item["body"]]
        if len(matches) > 1:
            output.append(f"Multiple issues match {marker}; stopping.")
            return RunResult(events, output, 1)
        urls.append(matches[0] if matches else None)

    for index, (ticket, marker, existing_url) in enumerate(
        zip(TICKETS, markers, urls, strict=True)
    ):
        if existing_url:
            output.append(existing_url)
            events.append(("confirmed", existing_url))
            continue
        body = f"{ticket['body']}\n\n{marker}"
        command = [
            str(FAKE_GH),
            "issue",
            "create",
            "--title",
            ticket["title"],
            "--body",
            body,
            "--label",
            ",".join(sorted(ticket["labels"])),
        ]
        events.append(("gh", " ".join(command[1:])))
        created = subprocess.run(
            command,
            check=False,
            capture_output=True,
            env=environment,
            text=True,
        )
        if created.returncode:
            output.append(created.stderr.strip())
            return RunResult(events, output, created.returncode)
        urls[index] = created.stdout.strip()
        output.append(urls[index])
        events.append(("confirmed", urls[index]))

    for ticket in TICKETS:
        for blocker in ticket["blockers"]:
            command = [
                str(FAKE_GH),
                "issue",
                "edit",
                urls[ticket["order"] - 1],
                "--add-blocked-by",
                urls[blocker - 1],
            ]
            events.append(("gh", " ".join(command[1:])))
            subprocess.run(
                command,
                check=True,
                capture_output=True,
                env=environment,
                text=True,
            )
    return RunResult(events, output, 0)


def _gh_invocations(tmp_path: Path) -> list[list[str]]:
    log = tmp_path / "gh.log"
    return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []


def test_complete_batch_is_shown_before_approval_and_no_creation_precedes_it(
    tmp_path: Path,
) -> None:
    result = _run_batch(tmp_path, approval=None)

    review = "\n".join(result.output)
    for ticket in TICKETS:
        assert f"{ticket['order']}. {ticket['title']}" in review
        assert ticket["body"] in review
        assert ", ".join(ticket["labels"]) in review
        assert f":ticket:{ticket['order']} -->" in review
    assert "Blocked by: 1" in review
    assert result.output[-1] == "Create these GitHub Issues now?"
    assert _gh_invocations(tmp_path) == []


def test_rejection_creates_no_issues(tmp_path: Path) -> None:
    result = _run_batch(tmp_path, approval=False)

    assert result.returncode == 0
    assert _gh_invocations(tmp_path) == []


def test_approval_creates_in_dependency_order_and_reports_confirmed_urls(
    tmp_path: Path,
) -> None:
    result = _run_batch(tmp_path, approval=True)

    creates = [
        invocation
        for invocation in _gh_invocations(tmp_path)
        if invocation[:2] == ["issue", "create"]
    ]
    assert [_option(invocation, "--title") for invocation in creates] == [
        ticket["title"] for ticket in TICKETS
    ]
    assert [_option(invocation, "--label") for invocation in creates] == [
        ",".join(sorted(ticket["labels"])) for ticket in TICKETS
    ]
    assert [
        re.search(
            r"<!-- agent-skills-batch:[0-9a-f]{64}:ticket:(?P<ordinal>[1-3]) -->",
            _option(invocation, "--body"),
        ).group("ordinal")
        for invocation in creates
    ] == ["1", "2", "3"]
    assert result.output[-3:] == [
        "https://github.test/example/repo/issues/1",
        "https://github.test/example/repo/issues/2",
        "https://github.test/example/repo/issues/3",
    ]
    first_create = next(
        index
        for index, event in enumerate(result.events)
        if event[0] == "gh" and event[1].startswith("issue create")
    )
    assert result.events[first_create - 1][0] == "gh"
    assert all(event[0] != "gh" for event in result.events[:2])
    assert all(
        invocation[:2] != ["issue", "edit"]
        for invocation in _gh_invocations(tmp_path)[: len(TICKETS) * 2]
    )


def test_rerun_after_partial_failure_reuses_markers_and_creates_only_missing_issues(
    tmp_path: Path,
) -> None:
    failed = _run_batch(tmp_path, approval=True, fail_after=2)

    assert failed.returncode == 1
    assert failed.output[-3:-1] == [
        "https://github.test/example/repo/issues/1",
        "https://github.test/example/repo/issues/2",
    ]

    resumed = _run_batch(tmp_path, approval=True)

    creates = [
        invocation
        for invocation in _gh_invocations(tmp_path)
        if invocation[:2] == ["issue", "create"]
    ]
    assert [_option(invocation, "--title") for invocation in creates] == [
        TICKETS[0]["title"],
        TICKETS[1]["title"],
        TICKETS[2]["title"],
        TICKETS[2]["title"],
    ]
    assert resumed.output[-3:] == [
        "https://github.test/example/repo/issues/1",
        "https://github.test/example/repo/issues/2",
        "https://github.test/example/repo/issues/3",
    ]
    state = json.loads((tmp_path / "gh-state.json").read_text())
    assert len(state["issues"]) == 3
    bodies = [issue["body"] for issue in state["issues"]]
    marker_pattern = re.compile(
        r"<!-- agent-skills-batch:[0-9a-f]{64}:ticket:(?P<ordinal>[1-3]) -->"
    )
    assert [marker_pattern.search(body).group("ordinal") for body in bodies] == [
        "1",
        "2",
        "3",
    ]


def _option(arguments: list[str], name: str) -> str:
    return arguments[arguments.index(name) + 1]
