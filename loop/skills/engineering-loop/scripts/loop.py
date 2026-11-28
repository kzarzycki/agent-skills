#!/usr/bin/env -S uv run -q --script
# /// script
# requires-python = ">=3.9"
# dependencies = ["PyYAML==6.0.3"]
# ///
"""The loop's own operations, which decide nothing, so they are not the gatekeeper's.

    uv run scripts/loop.py brief <pr> [--priorities <file>] [--proof <log>]... [--far <dir>] [--allow-conflict]  # a verifier pass's brief
    uv run scripts/loop.py release <issue>            # parked or dropped: remove the assignee the loop added

Both read the PR or the issue through the `gatekeeper` skill's gatekeeper.py and its ports, found where the host
installed that skill (`installed` below), and exit as it does: 0 done, 1 refused with the reason.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import re
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _installed import installed


def load(skill: str, name: str) -> ModuleType:
    """`<name>.py` from `skill`'s scripts, loaded by path; Python writes no bytecode into the installed skill."""
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location(name, installed(skill) / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gatekeeper = load("gatekeeper", "gatekeeper")


def release(number: int) -> int:
    """Parked or dropped: remove each assignee the loop added (assigned_by_loop), and keep a claim a person made."""
    issue = gatekeeper.issue_node(number)
    for login in sorted(gatekeeper.assignees(issue)):
        if gatekeeper.assigned_by_loop(issue, login):
            gatekeeper.assign(number, login, add=False)
            print(f"#{number}: removed @{login}, whom the loop assigned")
        else:
            print(f"#{number}: kept @{login}, whose claim it is")
    return 0


def fenced(text: str) -> list[str]:
    """`text` verbatim in a code fence one backtick longer than the longest run inside it (three at least), so
    a fence in the text never closes this one."""
    ticks = "`" * max(3, max((len(run) for run in re.findall(r"`+", text)), default=0) + 1)
    return [ticks, text.rstrip("\n"), ticks]


# a verifier pass's tool-call budget: past it the pass stops and reports what it checked (#2870). Passes seen ran 11-62
# calls, most under 30; 40 leaves a full pass room and stops a pass that explores the tree on a resent ~100k context.
TOOL_CALL_BUDGET = 40
FILE_LIST_CAP = 120
# lines of a PR body a verifier gains nothing from, since no criterion is about them
NOISE = re.compile(r"^(?:Token estimate|Tokens spent):.*\n?", re.MULTILINE)


def diff_summary(base: str, head: str) -> list[str]:
    """The brief's diff lines: `git diff --stat` between the merge-base and the head and the changed files with their
    status, so the verifier reads them from the brief instead of exploring the tree for them. The head is fetched
    first when this clone lacks it; where git can't answer, one line says so."""

    def git(*args: str) -> str:
        return subprocess.run(
            ["git", *args], capture_output=True, text=True, check=True
        ).stdout.rstrip("\n")

    try:
        try:
            git("cat-file", "-e", f"{head}^{{commit}}")
        except subprocess.CalledProcessError:
            git("fetch", "-q", "origin", head)
        stat = git("diff", "--stat=100", base, head)
        names = git("diff", "--name-status", base, head).splitlines()
    except (subprocess.CalledProcessError, OSError):
        return ["- Diff: not available here; run `git diff --stat <base> <head>`"]
    shown = names[:FILE_LIST_CAP]
    more = [f"  ...and {len(names) - FILE_LIST_CAP} more: run `git diff --name-status`"] * (
        len(names) > FILE_LIST_CAP
    )
    return [
        f"- Changed files ({len(names)}, status then path):",
        *(f"  {line}" for line in shown),
        *more,
        "- Diff stat (base to head):",
        *(f"  {line}" for line in stat.splitlines()[-FILE_LIST_CAP - 1 :]),
    ]


def previous_findings(pull: dict[str, Any], number: int) -> list[str]:
    """The findings pass `number` posted on the PR, each as its comment's text (`verdict` heads it `**Verifier (<family>),
    pass <n> · <id>** (<severity>): <title>`), the ones on a file outside the diff from the review's body, as their
    first line. Read from GitHub, so a verifier on any host gets them the way a host one does."""
    mine = re.compile(rf"\**Verifier \([^)]*\), pass {number} · ")
    found = [
        note["body"].strip()
        for thread in (pull.get("reviewThreads") or {}).get("nodes") or []
        for note in (thread.get("comments") or {}).get("nodes") or []
        if mine.match(note.get("body") or "")
    ]
    for review in (pull.get("reviews") or {}).get("nodes") or []:
        found += [
            line.strip()[2:]
            for line in (review.get("body") or "").splitlines()
            if line.startswith("- ") and mine.match(line[2:].strip())
        ]
    return found


def deviations_gap(body: str) -> str | None:
    """Why the PR body's `Spec deviations:` line (lead.md step 7) can't start a verifier, else None: the line is absent,
    or a deviation it lists (inline, or as the `- ` bullets under it) carries no link to the owner's decision (a URL or
    `#n`). `none` alone is fine."""
    lines = NOISE.sub("", body).splitlines()
    for at, line in enumerate(lines):
        if found := re.match(r"\s*Spec deviations:[ \t]*(.*?)[ \t]*$", line):
            break
    else:
        return "the body has no `Spec deviations:` line: write `none`, or each deviation with a link to the owner's decision"
    items = [found[1]] if found[1] else []
    for line in lines[at + 1 :]:
        if not line.lstrip().startswith(("- ", "* ")):
            break
        items.append(line.strip()[2:])
    if items and [item.strip("`*_ .").lower() for item in items] == ["none"]:
        return None
    if not items:
        return "the `Spec deviations:` line lists nothing: write `none`, or each deviation with a link to the owner's decision"
    if bare := [item for item in items if not re.search(r"https?://|(?<![\w&])#\d+", item)]:
        return f"the `Spec deviations:` line lists a deviation with no link to the owner's decision: {bare[0]}"
    return None


def gates_line(head: str) -> str:
    """The brief's `- Gates:` line: whether the gate has a recorded pass on the head's tree (the gatekeeper's `reusable`),
    so the verifier reruns the full gate only when it has none (verifier.md, Gates and repros)."""
    try:
        record = gatekeeper.reusable(head)
    except (gatekeeper.Refused, subprocess.CalledProcessError, OSError, ValueError):
        record = None
    if record is not None:
        return f"- Gates: passed on the head's tree at {record.get('time', 'a recorded time')}, recorded: don't rerun the gate"
    return "- Gates: no recorded pass on the head: run `approvals.py gate-record <head>` and run the gate only if it names a missing record"


def brief(
    pr: int,
    priorities: Path | None,
    proofs: list[Path],
    far: Path | None = None,
    allow_conflict: bool = False,
) -> int:
    """Print a verifier pass's brief (lead.md step 7) with its facts read from the PR, so none is a previous pass's: the
    verifier role, the base (the merge-base with the default branch), the head, the spec, the pass (one after the
    newest verdict review's) and its report path, from pass 2 the previous report and its head, then the PR's labels, its title and body verbatim (fenced, so a verifier with no GitHub access reads them),
    then the priorities
    file as is and loop.md's `## Verifier brief`, read from loop.md where the policy is gatekeeper.md's. For each spec it
    prints `- Acceptance tests: <command> <issue>`, the command loop.md's `Acceptance tests:` line names, else the
    fallback `uv run <this folder>/acceptance.py`, so the verifier runs the one the worker ran. A proof log whose first line isn't the head is refused, since the
    verifier counts a stale proof as missing and spends the pass on it. With `far` (a verifier on another host, `far` an
    absolute path there holding a clone of the repo) its paths are that host's: it fetches the head and makes its own
    detached worktree under `far`'s `tmp/loop/` first, the role is read there, and the report, the previous report and
    the proof logs are in `far`'s `tmp/loop/`, where the lead's `start --file` writes the last two, as are the previous
    pass's repros, each named by its path there from the copy of that report `wait` brought to `tmp/loop/` here."""
    pull = gatekeeper.pull_request(pr)
    with gatekeeper.policy_from(pull["baseRefName"]):
        _, loop = gatekeeper.project()
    if isinstance(loop, gatekeeper.Policy):
        where = gatekeeper.toplevel() / gatekeeper.LOOP
        loop = gatekeeper.read(where) if where.exists() else None
    head = pull["headRefOid"]
    # first, before anything is written: a pass on a head that conflicts with its base is spent on a head that can't land
    if not allow_conflict and (files := gatekeeper.conflicted(pr, pull["baseRefName"], head)):
        raise gatekeeper.Refused(
            f"PR #{pr}: head {head} does not merge cleanly into origin/{pull['baseRefName']}, conflicted: "
            f"{', '.join(files)}; merge the base in first, or pass --allow-conflict to review this head"
        )
    if missing := [str(log) for log in proofs if not log.is_file()]:
        raise gatekeeper.Refused(f"PR #{pr}: no proof log at {', '.join(missing)}")
    # byte for byte, as lead.md's `head -1 <log> | grep -qx <head>` compares: a trailing space or CR is another line
    if stale := [
        str(log) for log in proofs if log.read_bytes().split(b"\n", 1)[0] != head.encode()
    ]:
        raise gatekeeper.Refused(
            f"PR #{pr}: stale proof, its first line isn't the head {head}: {', '.join(stale)}; rerun it"
        )
    if problem := deviations_gap(pull["body"] or ""):
        raise gatekeeper.Refused(f"PR #{pr}: {problem}")
    reviewed = gatekeeper.passes(pull)
    if isinstance(reviewed, str):
        raise gatekeeper.Refused(f"PR #{pr} {reviewed}")
    number = max((n for _, n, _ in reviewed), default=0) + 1
    # the PR's own base, so a stacked PR gets its real base and not the default branch's
    base = gatekeeper.merge_base(pull["baseRefName"], head)
    issues = sorted(
        {issue["number"] for issue in pull["closingIssuesReferences"]["nodes"]}
        | set(gatekeeper.named(pull["body"] or ""))
    )
    role = Path(__file__).resolve().parents[1] / "verifier.md"
    runner = Path(gatekeeper.__file__).resolve().with_name("acceptance.py")
    loop_dir = far / "tmp" / "loop" if far else Path("tmp/loop")  # the verifier's tmp/loop/
    tree = loop_dir / f"pr{pr}-v{number}-tree"
    if far:
        if not far.is_absolute():
            raise gatekeeper.Refused(f"--far {far}: an absolute path on the verifier's host")
        role = tree / role.relative_to(gatekeeper.toplevel())  # the worktree's own copy
        runner = tree / runner.relative_to(gatekeeper.toplevel())
    lines = [
        f"Review PR #{pr} as the verifier, pass {number}, following {os.path.relpath(role) if not far else role}.",
        f"- Base: {base}",
        f"- Reviewed head: {head}",
        f"- Spec: {', '.join(f'#{n}' for n in issues) or 'none linked'}",
        gates_line(head),
    ]
    # the command the worker ran for each spec's checks, so the verifier runs the same one (SKILL.md, Acceptance checks)
    own = re.search(r"^Acceptance tests:[ \t]*(\S.*?)[ \t]*$", loop or "", re.MULTILINE)
    command = (
        own[1].strip("`").strip()
        if own and own[1].strip("`").strip()
        else f"uv run {runner if far else os.path.relpath(runner)}"
    )
    lines += [f"- Acceptance tests: {command} {n}" for n in issues]
    if far:
        lines.append(
            f"- Worktree: first, in {far}, run `git fetch origin pull/{pr}/head` and"
            f" `git worktree add --detach {tree} {head}`, then run every command of this brief in {tree}"
        )
    lines += diff_summary(base, head)
    lines.append(
        f"- Budget: {TOOL_CALL_BUDGET} tool calls. Read the changed files above, not the tree; at the budget stop,"
        " write the report with what you checked and what you did not, and say so on a `Budget:` line"
    )
    lines.append(f"- Report: {loop_dir / f'pr{pr}-v{number}.md'}")
    if reviewed:
        newest = next(commit for commit, n, _ in reversed(reviewed) if n == number - 1)
        lines.append(
            f"- Previous report: {loop_dir / f'pr{pr}-v{number - 1}.md'}, on {newest}: review the diff since that head"
            " and rerun its repros"
        )
        # the findings themselves, since the previous report stays on the lead's host and a cloud verifier can't read it
        if prior := previous_findings(pull, number - 1):
            lines += [
                f"- Previous findings, pass {number - 1}:",
                *(f"  {n}. " + f.replace("\n", "\n     ") for n, f in enumerate(prior, 1)),
            ]
        # a far verifier works in its worktree, but the last one saved its repros beside its report, in the clone's
        # tmp/loop/: each by its path there, from the copy wait brought home
        if far and (home := Path("tmp/loop") / f"pr{pr}-v{number - 1}.md").is_file():
            saved = re.findall(r"tmp/loop/([\w.-]+)(?![\w./-])", home.read_text())
            lines += [
                f"- Repro: {loop_dir / name}"
                for name in dict.fromkeys(saved)
                if name not in (home.name, f"pr{pr}-v{number}.md")
            ]
    lines += [
        f"- Proof log: {loop_dir / log.name if far else log} (its first line is the head)"
        for log in proofs
    ]
    if line := gatekeeper.unforced(pull):
        lines.append(f"- Note: {line}")
    if labels := [label["name"] for label in pull["labels"]["nodes"]]:
        lines.append(f"- Labels: {', '.join(labels)}")
    # the PR's own text, verbatim, so a verifier with no GitHub access can check a criterion about it
    lines += [
        "",
        "PR title:",
        *fenced(pull["title"] or ""),
        "",
        "PR body:",
        *fenced(NOISE.sub("", pull["body"] or "")),
    ]
    if priorities is not None:
        lines += ["", "Priorities:", priorities.read_text().rstrip()]
    # as written, but for the blank lines around it: indentation may be a snippet's
    if (own := gatekeeper.section(loop or "", "Verifier brief").strip("\n")).strip():
        lines += ["", own]
    # a warning for the lead, on stderr: the brief on stdout is the verifier's and stays as it is
    try:
        if shared := gatekeeper.overlaps(pr):
            print(f"warning: PR #{pr} overlaps other open PRs:", *shared, sep="\n", file=sys.stderr)
    except (gatekeeper.Refused, subprocess.CalledProcessError, OSError, ValueError) as exc:
        why = (getattr(exc, "stderr", None) or str(exc)).strip().splitlines()
        print(f"warning: overlap lookup failed: {why[0] if why else exc!r}", file=sys.stderr)
    print("\n".join(lines))
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    commands = parser.add_subparsers(dest="command", required=True)
    briefing = commands.add_parser("brief")
    briefing.add_argument("pr", type=int)
    # a verifier on another host: the absolute path there holding a clone of the repo
    briefing.add_argument("--far", type=Path)
    briefing.add_argument("--priorities", type=Path)
    briefing.add_argument("--allow-conflict", action="store_true")
    briefing.add_argument("--proof", type=Path, action="append", default=[])
    releasing = commands.add_parser("release")
    releasing.add_argument("issue", type=int)
    args = parser.parse_args(argv)
    # the policy's adapters, read at the first port call, as gatekeeper.py's main does
    gatekeeper.running, gatekeeper.using = True, None
    try:
        gatekeeper.one_repo()
        if args.command == "brief":
            return brief(args.pr, args.priorities, args.proof, args.far, args.allow_conflict)
        return release(args.issue)
    except gatekeeper.Refused as exc:
        print(exc)
        return 1
    except subprocess.CalledProcessError as exc:
        print(exc.stderr.strip() or exc)  # gh's reason
        return 1
    finally:
        gatekeeper.running, gatekeeper.using = False, None


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
