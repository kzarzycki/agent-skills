from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest
import yaml

PACKAGE = Path(__file__).resolve().parents[1]
TEMPLATE = PACKAGE / "skills" / "github-tracker" / "github.md"
_SPEC = importlib.util.spec_from_file_location(
    "issue_batch", PACKAGE / "skills" / "github-tracker" / "scripts" / "issue_batch.py"
)
assert _SPEC and _SPEC.loader
issue_batch = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(issue_batch)
FAKE_GH = Path(__file__).parent / "fixtures" / "fake-gh"
PROTOCOL_PATTERN = re.compile(
    r"<!-- github-issue-batch-fixture-protocol\n(?P<protocol>.*?)\n-->",
    re.DOTALL,
)
TICKETS = [
    {
        "title": "Render account status",
        "body": "Show the account status in the dashboard.",
        "labels": ["frontend", "ready-for-agent"],
        "blockers": ["Expose account status"],
    },
    {
        "title": "Expose account status",
        "body": "Return the current account status from the API.",
        "labels": ["ready-for-agent", "api"],
        "blockers": [],
    },
    {
        "title": "Alert on account status",
        "body": "Notify operators when the account status changes.",
        "labels": ["ready-for-agent"],
        "blockers": ["Expose account status"],
    },
]


@dataclass
class PreparedBatch:
    batch_sha256: str
    issues: list[dict]
    relationships: list[dict]


@dataclass
class RunResult:
    events: list[tuple[str, str]]
    output: list[str]
    returncode: int
    batch: PreparedBatch
    state_path: Path


def _load_protocol() -> dict:
    match = PROTOCOL_PATTERN.search(TEMPLATE.read_text())
    assert match, "GitHub tracker template must declare its batch fixture protocol"
    protocol = yaml.safe_load(match.group("protocol"))
    assert protocol["version"] == 2
    assert protocol["ordering"] == {
        "algorithm": "stable_topological",
        "ticket_tiebreak": "title_utf8_bytes",
        "blocker_order": "final_ticket_order",
        "unique_titles": True,
    }
    assert protocol["state"]["atomic_write"] == ("sibling_temp_fsync_replace_directory_fsync")
    return protocol


def _prepare_batch(tickets: list[dict], protocol: dict) -> PreparedBatch:
    assert protocol["marker"] == issue_batch.MARKER
    return PreparedBatch(**issue_batch.prepare(tickets))


def _state_path(root: Path, batch: PreparedBatch, protocol: dict) -> Path:
    return (
        root
        / protocol["state"]["directory"]
        / protocol["state"]["filename"].format(
            batch_sha256=batch.batch_sha256,
        )
    )


def _atomic_write_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("w") as handle:
        json.dump(state, handle, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    directory_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def _new_state(batch: PreparedBatch) -> dict:
    return {
        "version": 1,
        "batch_sha256": batch.batch_sha256,
        "approved": True,
        "issues": batch.issues,
        "relationships": batch.relationships,
    }


def _render_review(batch: PreparedBatch, remaining_writes: list[str]) -> list[str]:
    lines = ["Proposed GitHub Issue batch:"]
    for issue in batch.issues:
        lines.extend(
            [
                f"{issue['order']}. {issue['title']}",
                f"   Body: {issue['marked_body']}",
                f"   Labels: {', '.join(issue['labels'])}",
                "   Blocked by: " + (", ".join(issue["blockers"]) or "None"),
            ]
        )
    lines.append("Exact remaining write plan:")
    lines.extend(f"- {write}" for write in remaining_writes)
    return lines


def _gh_environment(
    tmp_path: Path,
    *,
    fail_after: int,
    lose_response_for: str | None,
) -> dict[str, str]:
    environment = os.environ.copy()
    environment.update(
        {
            "FAKE_GH_LOG": str(tmp_path / "gh.log"),
            "FAKE_GH_STATE": str(tmp_path / "gh-state.json"),
            "FAKE_GH_FAIL_AFTER": str(fail_after),
        }
    )
    if lose_response_for:
        environment["FAKE_GH_LOSE_CREATE_RESPONSE_FOR_TITLE"] = lose_response_for
    return environment


def _search_markers(
    batch: PreparedBatch,
    environment: dict[str, str],
    events: list[tuple[str, str]],
) -> tuple[list[str | None], str | None]:
    urls: list[str | None] = []
    for issue in batch.issues:
        command = [
            str(FAKE_GH),
            "issue",
            "list",
            "--state",
            "all",
            "--search",
            issue["marker"],
            "--json",
            "url,body",
        ]
        events.append(("gh-read", " ".join(command[1:])))
        search = subprocess.run(
            command,
            check=True,
            capture_output=True,
            env=environment,
            text=True,
        )
        matches = [
            item["url"] for item in json.loads(search.stdout) if issue["marker"] in item["body"]
        ]
        if len(matches) > 1:
            return urls, (f"Multiple issues match {issue['marker']}: " + ", ".join(sorted(matches)))
        urls.append(matches[0] if matches else None)
    return urls, None


def _remaining_writes(batch: PreparedBatch, state: dict) -> list[str]:
    writes = [
        f"create issue {issue['order']}: {issue['title']}"
        for issue in state["issues"]
        if issue["url"] is None
    ]
    writes.extend(
        (
            f"add blocker issue {relationship['blocker_order']} -> "
            f"issue {relationship['blocked_order']}"
        )
        for relationship in state["relationships"]
        if relationship["status"] != "confirmed"
    )
    return writes


def _run_batch(
    tmp_path: Path,
    *,
    tickets: list[dict] = TICKETS,
    approval: bool | None,
    fail_after: int = 0,
    lose_response_for: str | None = None,
) -> RunResult:
    protocol = _load_protocol()
    batch = _prepare_batch(tickets, protocol)
    state_path = _state_path(tmp_path, batch, protocol)
    environment = _gh_environment(
        tmp_path,
        fail_after=fail_after,
        lose_response_for=lose_response_for,
    )
    events: list[tuple[str, str]] = []
    output: list[str] = []

    state = json.loads(state_path.read_text()) if state_path.exists() else None
    if state is not None:
        assert state["batch_sha256"] == batch.batch_sha256
        assert state["approved"] is True
        assert [
            {key: issue[key] for key in ("title", "body", "labels", "blockers", "order")}
            for issue in state["issues"]
        ] == [
            {key: issue[key] for key in ("title", "body", "labels", "blockers", "order")}
            for issue in batch.issues
        ]

    urls, duplicate_error = _search_markers(batch, environment, events)
    if duplicate_error:
        output.append(duplicate_error)
        return RunResult(events, output, 1, batch, state_path)

    if state is None:
        proposed_state = _new_state(batch)
        for issue, url in zip(proposed_state["issues"], urls, strict=True):
            issue["url"] = url
        remaining = _remaining_writes(batch, proposed_state)
        output.extend(_render_review(batch, remaining))
        output.append(protocol["approval_prompt"])
        events.append(("approval", "requested"))
        if approval is not True:
            events.append(("approval", "rejected" if approval is False else "pending"))
            return RunResult(events, output, 0, batch, state_path)
        state = proposed_state
        _atomic_write_state(state_path, state)
        events.append(("state", "approved"))
    else:
        output.append(f"Resuming approved batch {batch.batch_sha256}.")
        for issue, url in zip(state["issues"], urls, strict=True):
            if url:
                issue["url"] = url
        _atomic_write_state(state_path, state)
        events.append(("state", "reconciled"))

    for issue in state["issues"]:
        if issue["url"]:
            output.append(issue["url"])
            events.append(("confirmed", issue["url"]))
            continue
        command = [
            str(FAKE_GH),
            "issue",
            "create",
            "--title",
            issue["title"],
            "--body",
            issue["marked_body"],
            "--label",
            ",".join(issue["labels"]),
        ]
        events.append(("gh-write", " ".join(command[1:])))
        created = subprocess.run(
            command,
            check=False,
            capture_output=True,
            env=environment,
            text=True,
        )
        if created.returncode:
            output.append(created.stderr.strip())
            return RunResult(events, output, created.returncode, batch, state_path)
        issue["url"] = created.stdout.strip()
        _atomic_write_state(state_path, state)
        events.append(("state", f"confirmed issue {issue['order']}"))
        output.append(issue["url"])
        events.append(("confirmed", issue["url"]))

    for relationship in state["relationships"]:
        if relationship["status"] == "confirmed":
            continue
        blocked = state["issues"][relationship["blocked_order"] - 1]["url"]
        blocker = state["issues"][relationship["blocker_order"] - 1]["url"]
        command = [
            str(FAKE_GH),
            "issue",
            "edit",
            blocked,
            "--add-blocked-by",
            blocker,
        ]
        events.append(("gh-write", " ".join(command[1:])))
        edited = subprocess.run(
            command,
            check=False,
            capture_output=True,
            env=environment,
            text=True,
        )
        if edited.returncode:
            output.append(edited.stderr.strip())
            return RunResult(events, output, edited.returncode, batch, state_path)
        relationship["status"] = "confirmed"
        _atomic_write_state(state_path, state)
        events.append(
            (
                "state",
                (
                    f"confirmed relationship {relationship['blocker_order']}"
                    f"->{relationship['blocked_order']}"
                ),
            )
        )
    return RunResult(events, output, 0, batch, state_path)


def _gh_invocations(tmp_path: Path) -> list[list[str]]:
    log = tmp_path / "gh.log"
    return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []


def _mutating_invocations(tmp_path: Path) -> list[list[str]]:
    return [
        invocation
        for invocation in _gh_invocations(tmp_path)
        if invocation[:2] in (["issue", "create"], ["issue", "edit"])
    ]


def _remote_state(tmp_path: Path) -> dict:
    return json.loads((tmp_path / "gh-state.json").read_text())


def _option(arguments: list[str], name: str) -> str:
    return arguments[arguments.index(name) + 1]


def test_first_run_reconciles_before_exact_preview_and_approval_boundary(
    tmp_path: Path,
) -> None:
    pending = _run_batch(tmp_path, approval=None)

    assert all(event[0] == "gh-read" for event in pending.events[: len(TICKETS)])
    review = "\n".join(pending.output)
    for issue in pending.batch.issues:
        assert f"{issue['order']}. {issue['title']}" in review
        assert issue["marked_body"] in review
        assert ", ".join(issue["labels"]) in review
    assert "Exact remaining write plan:" in review
    assert pending.output[-1] == "Create these GitHub Issues now?"
    assert _mutating_invocations(tmp_path) == []
    assert not pending.state_path.exists()

    approved = _run_batch(tmp_path, approval=True)

    first_write = next(
        index for index, event in enumerate(approved.events) if event[0] == "gh-write"
    )
    assert approved.events[first_write - 2 :][0:2] == [
        ("approval", "requested"),
        ("state", "approved"),
    ]
    assert all(
        event[0] != "gh-read"
        for event in approved.events[
            approved.events.index(("approval", "requested")) + 1 : first_write
        ]
    )


def test_rejection_creates_zero_issues_and_persists_no_approval(tmp_path: Path) -> None:
    result = _run_batch(tmp_path, approval=False)

    assert result.returncode == 0
    assert _mutating_invocations(tmp_path) == []
    assert not result.state_path.exists()


def test_approval_uses_stable_order_and_persists_urls_and_graph(
    tmp_path: Path,
) -> None:
    result = _run_batch(tmp_path, approval=True)

    assert result.returncode == 0
    assert [issue["title"] for issue in result.batch.issues] == [
        "Expose account status",
        "Alert on account status",
        "Render account status",
    ]
    state = json.loads(result.state_path.read_text())
    assert [issue["url"] for issue in state["issues"]] == [
        "https://github.test/example/repo/issues/1",
        "https://github.test/example/repo/issues/2",
        "https://github.test/example/repo/issues/3",
    ]
    assert state["relationships"] == [
        {"blocked_order": 2, "blocker_order": 1, "status": "confirmed"},
        {"blocked_order": 3, "blocker_order": 1, "status": "confirmed"},
    ]
    assert _remote_state(tmp_path)["relationships"] == [
        {
            "blocked": "https://github.test/example/repo/issues/2",
            "blocker": "https://github.test/example/repo/issues/1",
        },
        {
            "blocked": "https://github.test/example/repo/issues/3",
            "blocker": "https://github.test/example/repo/issues/1",
        },
    ]
    assert list(result.state_path.parent.glob(".*.tmp")) == []


def test_fresh_process_recovers_create_success_with_lost_response(
    tmp_path: Path,
) -> None:
    interrupted = _run_batch(
        tmp_path,
        approval=True,
        lose_response_for="Alert on account status",
    )

    assert interrupted.returncode == 1
    durable_after_interrupt = json.loads(interrupted.state_path.read_text())
    assert [issue["url"] for issue in durable_after_interrupt["issues"]] == [
        "https://github.test/example/repo/issues/1",
        None,
        None,
    ]
    assert len(_remote_state(tmp_path)["issues"]) == 2

    resumed = _run_batch(tmp_path, approval=None)

    assert resumed.returncode == 0
    assert ("approval", "requested") not in resumed.events
    creates = [
        invocation
        for invocation in _gh_invocations(tmp_path)
        if invocation[:2] == ["issue", "create"]
    ]
    assert [_option(invocation, "--title") for invocation in creates] == [
        "Expose account status",
        "Alert on account status",
        "Render account status",
    ]
    assert len(_remote_state(tmp_path)["issues"]) == 3
    final_state = json.loads(resumed.state_path.read_text())
    assert all(issue["url"] for issue in final_state["issues"])
    assert all(
        relationship["status"] == "confirmed" for relationship in final_state["relationships"]
    )


def test_equivalent_input_permutations_have_one_order_hash_and_marker_set() -> None:
    protocol = _load_protocol()
    tickets = [
        *TICKETS,
        {
            "title": "Summarize account status",
            "body": "Summarize account status signals for operators.",
            "labels": ["reporting", "ready-for-agent"],
            "blockers": ["Render account status", "Alert on account status"],
        },
    ]
    blocker_permutations = [
        {
            **ticket,
            "labels": list(reversed(ticket["labels"])),
            "blockers": list(reversed(ticket["blockers"])),
        }
        for ticket in reversed(tickets)
    ]

    first = _prepare_batch(tickets, protocol)
    second = _prepare_batch(blocker_permutations, protocol)

    assert second.batch_sha256 == first.batch_sha256
    assert [issue["title"] for issue in second.issues] == [issue["title"] for issue in first.issues]
    assert [issue["marker"] for issue in second.issues] == [
        issue["marker"] for issue in first.issues
    ]


def _changed_batch(case: str) -> list[dict]:
    tickets = [
        {
            **ticket,
            "labels": list(ticket["labels"]),
            "blockers": list(ticket["blockers"]),
        }
        for ticket in TICKETS
    ]
    if case == "title":
        tickets[0]["title"] = "Render current account status"
    elif case == "body":
        tickets[2]["body"] = "Notify operators immediately."
    elif case == "labels":
        tickets[1]["labels"].append("backend")
    elif case == "blockers":
        tickets[2]["blockers"] = []
    elif case == "derived_order":
        tickets.append(
            {
                "title": "Audit account status",
                "body": "Record every account status transition.",
                "labels": ["ready-for-agent"],
                "blockers": ["Expose account status"],
            }
        )
    else:
        raise AssertionError(case)
    return tickets


@pytest.mark.parametrize(
    "case",
    ["title", "body", "labels", "blockers", "derived_order"],
)
def test_changed_batch_invalidates_durable_approval(
    tmp_path: Path,
    case: str,
) -> None:
    approved = _run_batch(tmp_path, approval=True)
    writes_before = len(_mutating_invocations(tmp_path))

    changed = _run_batch(
        tmp_path,
        tickets=_changed_batch(case),
        approval=None,
    )

    assert changed.batch.batch_sha256 != approved.batch.batch_sha256
    assert changed.output[-1] == "Create these GitHub Issues now?"
    assert ("approval", "requested") in changed.events
    assert len(_mutating_invocations(tmp_path)) == writes_before
    assert not changed.state_path.exists()


def test_duplicate_marker_stops_before_approval_create_or_relationship_edit(
    tmp_path: Path,
) -> None:
    protocol = _load_protocol()
    batch = _prepare_batch(TICKETS, protocol)
    marker = batch.issues[0]["marker"]
    duplicate_state = {
        "issues": [
            {
                "url": "https://github.test/example/repo/issues/41",
                "title": "First duplicate",
                "body": marker,
                "labels": [],
            },
            {
                "url": "https://github.test/example/repo/issues/42",
                "title": "Second duplicate",
                "body": marker,
                "labels": [],
            },
        ],
        "relationships": [],
        "lost_create_responses": [],
    }
    (tmp_path / "gh-state.json").write_text(json.dumps(duplicate_state) + "\n")

    result = _run_batch(tmp_path, approval=True)

    assert result.returncode == 1
    assert result.output == [
        (
            f"Multiple issues match {marker}: "
            "https://github.test/example/repo/issues/41, "
            "https://github.test/example/repo/issues/42"
        )
    ]
    assert ("approval", "requested") not in result.events
    assert _mutating_invocations(tmp_path) == []


LAYERS = PACKAGE.parent / "docs" / "layers.md"
MANIFEST_FENCE = re.compile(r"## Split manifest.*?```json\n(?P<manifest>.*?)\n```", re.DOTALL)


def _documented_manifest(tmp_path: Path) -> Path:
    match = MANIFEST_FENCE.search(LAYERS.read_text())
    assert match, "docs/layers.md must show a split manifest"
    path = tmp_path / "split-manifest.json"
    path.write_text(match.group("manifest"))
    return path


def test_documented_manifest_round_trips_through_the_apply_step(tmp_path: Path) -> None:
    manifest = _documented_manifest(tmp_path)
    items = json.loads(manifest.read_text())["items"]
    tickets = issue_batch.tickets_from_manifest(manifest, ["area:engineering"])

    result = _run_batch(tmp_path, tickets=tickets, approval=True)

    assert result.returncode == 0
    remote = _remote_state(tmp_path)
    assert [(issue["title"], issue["labels"]) for issue in remote["issues"]] == [
        (item["title"], ["area:engineering"]) for item in items
    ]
    for issue, item in zip(remote["issues"], items, strict=True):
        assert issue["body"].startswith(f"{item['spec']}\n\n<!-- agent-skills-batch:")
    assert remote["relationships"] == [
        {
            "blocked": "https://github.test/example/repo/issues/2",
            "blocker": "https://github.test/example/repo/issues/1",
        }
    ]
    writes = len(_mutating_invocations(tmp_path))

    again = _run_batch(tmp_path, tickets=tickets, approval=None)

    assert again.returncode == 0
    assert len(_mutating_invocations(tmp_path)) == writes


@pytest.mark.parametrize(
    "mutate",
    [
        lambda m: m["items"].append(dict(m["items"][0])),
        lambda m: m["items"][0].update(blocked_by=["No such item"]),
        lambda m: m["items"][0].update(blocked_by=[m["items"][1]["title"]]),
        lambda m: m.update(version=2),
    ],
    ids=["duplicate-title", "unknown-blocker", "cycle", "version"],
)
def test_apply_step_refuses_a_bad_manifest_before_any_gh_call(tmp_path: Path, mutate) -> None:
    manifest = _documented_manifest(tmp_path)
    document = json.loads(manifest.read_text())
    mutate(document)
    manifest.write_text(json.dumps(document))

    with pytest.raises(issue_batch.BatchError):
        issue_batch.tickets_from_manifest(manifest, [])

    assert _gh_invocations(tmp_path) == []


def test_apply_step_labels_every_issue_ready_for_agent_unless_the_caller_names_labels(
    tmp_path: Path,
) -> None:
    manifest = _documented_manifest(tmp_path)

    default = issue_batch.prepare(
        issue_batch.tickets_from_manifest(manifest, [issue_batch.DEFAULT_LABEL])
    )
    assert {tuple(issue["labels"]) for issue in default["issues"]} == {("ready-for-agent",)}

    printed = subprocess.run(
        [
            "python3",
            str(PACKAGE / "skills/github-tracker/scripts/issue_batch.py"),
            "github",
            str(manifest),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert json.loads(printed.stdout) == default

    named = subprocess.run(
        [
            "python3",
            str(PACKAGE / "skills/github-tracker/scripts/issue_batch.py"),
            "github",
            str(manifest),
            "--label",
            "b",
            "--label",
            "a",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert {tuple(issue["labels"]) for issue in json.loads(named.stdout)["issues"]} == {("a", "b")}


def test_cli_refuses_a_bad_manifest_with_exit_1_and_writes_nothing(tmp_path: Path) -> None:
    manifest = _documented_manifest(tmp_path)
    document = json.loads(manifest.read_text())
    document["items"][0]["blocked_by"] = ["No such item"]
    manifest.write_text(json.dumps(document))
    script = str(PACKAGE / "skills/github-tracker/scripts/issue_batch.py")

    for target in ("github", "local"):
        refused = subprocess.run(
            ["python3", script, target, str(manifest)], check=False, capture_output=True, text=True
        )
        assert refused.returncode == 1
        assert "unknown" in refused.stderr
    assert not (tmp_path / "issues").exists()


def test_local_files_apply_writes_numbered_tickets_in_the_local_template(tmp_path: Path) -> None:
    manifest = tmp_path / "split-manifest.json"
    spec = (
        "## What to build\n\nShow the status.\n\n## Acceptance criteria\n\n- [ ] One\n- [ ] Two\n\n"
        "## Blocked by\n\n- Expose account status\n"
    )
    manifest.write_text(
        json.dumps(
            {
                "version": 1,
                "items": [
                    {
                        "title": "Render account status",
                        "spec": spec,
                        "blocked_by": ["Expose account status"],
                    },
                    {"title": "Expose account status", "spec": "Return it.", "blocked_by": []},
                ],
            }
        )
    )

    script = str(PACKAGE / "skills/github-tracker/scripts/issue_batch.py")
    subprocess.run(["python3", script, "local", str(manifest)], check=True, capture_output=True)

    issues = tmp_path / "issues"
    assert sorted(path.name for path in issues.iterdir()) == [
        "01-expose-account-status.md",
        "02-render-account-status.md",
    ]
    assert (issues / "01-expose-account-status.md").read_text() == (
        "# 01: Expose account status\n\n**What to build:** Return it.\n\n"
        "**Blocked by:** None (can start immediately)\n\n**Status:** ready-for-agent\n"
    )
    assert (issues / "02-render-account-status.md").read_text() == (
        "# 02: Render account status\n\n**What to build:** Show the status.\n\n"
        "**Blocked by:** 01 Expose account status\n\n**Status:** ready-for-agent\n\n"
        "- [ ] One\n- [ ] Two\n"
    )
