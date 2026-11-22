#!/usr/bin/env -S uv run -q --script
# /// script
# requires-python = ">=3.9"
# dependencies = ["PyYAML==6.0.3"]
# ///
"""The loop's own operations, which decide nothing, so they are not the gatekeeper's.

    uv run scripts/loop.py brief <pr> [--priorities <file>] [--proof <log>]... [--far <dir>] [--allow-conflict]  # a verifier pass's brief
    uv run scripts/loop.py brief <pr> --since <sha> [--priorities <file>]  # a reused verifier's delta brief
    uv run scripts/loop.py evidence <pr> --pass <n> --finding <title> --repro <file> --log <file>  # a finding's repro on the PR's evidence branch
    uv run scripts/loop.py release <issue>            # parked or dropped: remove the assignee the loop added

These read the PR or the issue through the `gatekeeper` skill's gatekeeper.py and its ports, found where the host
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


def installed(skill: str) -> Path:
    """The scripts folder of `skill`, which another package ships, found by the host's install layout: a sibling
    skill folder (APM's one skills directory), a sibling plugin's (this repo, or a marketplace Claude Code loads in
    place), else the newest version of a plugin in Claude Code's cache (`<marketplace>/<plugin>/<version>/`) that
    no update has orphaned. Exits naming the skill to install when none holds it."""
    # ponytail: three layouts, the ones APM and Claude Code use; a host with another adds its glob here.
    own = Path(__file__).resolve().parents[1]
    plugin = own.parent.parent
    cached = plugin.parent.parent.glob(f"[!.]*/[!.]*/skills/{skill}")
    for folder in [
        own.parent / skill,
        *sorted(plugin.parent.glob(f"[!.]*/skills/{skill}")),
        *sorted(cached, key=lambda path: path.stat().st_mtime, reverse=True),
    ]:
        if (folder / "SKILL.md").is_file() and not (folder.parents[1] / ".orphaned_at").exists():
            return folder / "scripts"
    sys.exit(f"{Path(__file__).name} needs the `{skill}` skill: install the package that ships it")


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


PASS_FINDING = re.compile(r"\**Verifier \([^)]*\), pass \d+ · ")


def previous_findings(pull: dict[str, Any], number: int) -> list[str]:
    """The findings pass `number` posted on the PR, each as its comment's text (`verdict` heads it `**Verifier (<family>),
    pass <n> · <id>** (<severity>): <title>`), the ones on a file outside the diff from the review's body, as their
    heading and the lines under it. Read from GitHub, so a verifier on any host gets them the way a host one does."""
    mine = re.compile(rf"\**Verifier \([^)]*\), pass {number} · ")
    found = [
        note["body"].strip()
        for thread in (pull.get("reviewThreads") or {}).get("nodes") or []
        if not thread.get("isResolved")  # a finding the lead resolved is no longer open
        for note in (thread.get("comments") or {}).get("nodes") or []
        if mine.match(note.get("body") or "")
    ]
    for review in (pull.get("reviews") or {}).get("nodes") or []:
        # a finding on a file outside the diff is a bullet in the review's body: its heading and the lines under it
        # (its evidence link among them) up to the next bullet or closing line
        current: list[str] | None = None
        text = review.get("body") or ""
        if "<!-- finding: " in text:
            for block in gatekeeper.FINDING_BLOCK.findall(text):
                head = block.strip()[2:] if block.startswith("- ") else block.strip()
                if mine.match(head):
                    found.append(head)
            continue
        # a body from before the markers: a bullet's lines up to the next bullet
        for line in text.splitlines():
            if line.startswith("- ") and mine.match(line[2:].strip()):
                current = [line.strip()[2:]]
                found.append("")
            elif current is not None and (
                line.startswith("- ") or gatekeeper.VERDICT_END.match(line)
            ):
                current = None
            elif current is not None:
                current.append(line)
            if current is not None:
                found[-1] = "\n".join(current).strip()
    return found


def brief(
    pr: int,
    priorities: Path | None,
    proofs: list[Path],
    far: Path | None = None,
    allow_conflict: bool = False,
) -> int:
    """Print a verifier pass's brief (lead.md step 7) with its facts read from the PR, so none is a previous pass's: the
    verifier role, the base (the merge-base with the default branch), the head, the spec, the pass (one after the
    newest verdict review's) and its report path, from pass 2 the previous pass's head, its findings and each one's rerun command, then the PR's labels, its title and body verbatim (fenced, so a verifier with no GitHub access reads them),
    then the priorities
    file as is and loop.md's `## Verifier brief`, read from loop.md where the policy is gatekeeper.md's. For each spec it
    prints `- Acceptance tests: <command> <issue>`, the command loop.md's `Acceptance tests:` line names, else the
    fallback `uv run <this folder>/acceptance.py`, so the verifier runs the one the worker ran. A proof log whose first line isn't the head is refused, since the
    verifier counts a stale proof as missing and spends the pass on it. With `far` (a verifier on another host, `far` an
    absolute path there holding a clone of the repo) its paths are that host's: it fetches the head and makes its own
    detached worktree under `far`'s `tmp/loop/` first, the role is read there, and the report and
    the proof logs are in `far`'s `tmp/loop/`, where the lead's `start --file` writes the logs."""
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
    reviewed = gatekeeper.passes(pull)
    if isinstance(reviewed, str):
        raise gatekeeper.Refused(f"PR #{pr} {reviewed}")
    number = max((n for _, n, _ in reviewed), default=0) + 1
    base = gatekeeper.merge_base(pull["baseRepository"]["defaultBranchRef"]["name"], head)
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
    lines.append(f"- Report: {loop_dir / f'pr{pr}-v{number}.md'}")
    if reviewed:
        newest = next(commit for commit, n, _ in reversed(reviewed) if n == number - 1)
        lines.append(
            f"- Previous pass: {number - 1}, on {newest}: review the diff since that head and rerun its repros"
        )
        # the findings and their repro commands, read from the PR: no report file is handed between passes, so a
        # verifier on any host, in a session or a fresh one, gets them the same way
        prior = previous_findings(pull, number - 1)
        if prior:
            lines.append(f"- Previous findings, pass {number - 1}:")
        for n, found in enumerate(prior, 1):
            lines.append(f"  {n}. " + found.replace("\n", "\n     "))
            if script := gatekeeper.rerun_command(pr, found):
                lines.append(f"     Rerun: {script}")
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
        *fenced(pull["body"] or ""),
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


# a top-level PR comment of the lead's that is triage, not another note: it opens with the word
TRIAGE = re.compile(r"\W*triage\b", re.IGNORECASE)


def triage_replies(pull: dict[str, Any], after: str | None) -> list[str]:
    """The lead's triage replies posted after `after`, the time of the verifier's last review: the lead's later comments
    on a verifier finding's thread, and the lead's top-level PR comments that open with `Triage`. The lead is the account
    running this, the one that posts the verdicts, since anyone can comment on a public PR and a stranger's comment is no
    triage. A comment with no time, or no author, is left out, and with no `after` there is none to show, since an
    unknown time can't be told from a reply the verifier already saw."""
    if not after:
        return []
    lead = gatekeeper.viewer()

    def mine(note: dict[str, Any]) -> bool:
        return (note.get("author") or {}).get("login") == lead and (
            note.get("createdAt") or ""
        ) > after

    found = []
    for thread in (pull.get("reviewThreads") or {}).get("nodes") or []:
        notes = (thread.get("comments") or {}).get("nodes") or []
        if notes and PASS_FINDING.match(notes[0].get("body") or ""):
            found += [note["body"].strip() for note in notes[1:] if mine(note)]
    found += [
        (note.get("body") or "").strip()
        for note in (pull.get("comments") or {}).get("nodes") or []
        if mine(note) and TRIAGE.match(note.get("body") or "")
    ]
    return [text for text in found if text]


def brief_since(pr: int, since: str, priorities: Path | None = None) -> int:
    """Print a reused verifier's brief: only the new head, the pass and its report path, `git diff <since>..<head>`, and
    the lead's triage replies since its last pass (triage_replies), shown as the lead's claims. No findings list and no
    rerun list: the conversation already holds them, and each fix is judged by rerunning its repro, not by a reply."""
    pull = gatekeeper.pull_request(pr)
    head = pull["headRefOid"]
    reviewed = gatekeeper.passes(pull)
    if isinstance(reviewed, str):
        raise gatekeeper.Refused(f"PR #{pr} {reviewed}")
    number = max((n for _, n, _ in reviewed), default=0) + 1
    try:
        diff = gatekeeper.git("diff", f"{since}..{head}")
    except subprocess.CalledProcessError:
        gatekeeper.git("fetch", "-q", "origin", f"pull/{pr}/head")
        try:
            diff = gatekeeper.git("diff", f"{since}..{head}")
        except subprocess.CalledProcessError as exc:
            raise gatekeeper.Refused(
                f"PR #{pr}: no diff {since}..{head}: {' '.join((exc.stderr or '').split())}"
            ) from exc
    last = [
        review.get("submittedAt") or ""
        for review in (pull.get("reviews") or {}).get("nodes") or []
        if (m := gatekeeper.PASS.match(review.get("body") or "")) and int(m[2]) == number - 1
    ]
    replies = triage_replies(pull, max(last) if last and max(last) else None)
    lines = [
        f"Review PR #{pr} as the verifier, pass {number}: this is your conversation's next pass, so review only what changed.",
        f"- Reviewed head: {head}",
        f"- Last verified head: {since}",
        f"- Report: tmp/loop/pr{pr}-v{number}.md",
        "",
        f"Diff since your last pass (`git diff {since}..{head}`):",
        diff.rstrip() or "(empty)",
    ]
    if replies:
        lines += [
            "",
            "The lead's triage replies since your last pass, which are the lead's claims, not facts: judge each fix by rerunning its repro.",
        ]
        lines += [f"- {text}".replace("\n", "\n  ") for text in replies]
    if priorities is not None:
        lines += ["", "Priorities:", priorities.read_text().rstrip()]
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
    # a reused verifier's brief: only what changed since the head it last verified
    briefing.add_argument("--since", metavar="SHA")
    briefing.add_argument("--proof", type=Path, action="append", default=[])
    evidencing = commands.add_parser("evidence")
    evidencing.add_argument("pr", type=int)
    evidencing.add_argument("--pass", dest="number", type=int, required=True)
    evidencing.add_argument("--finding", required=True, help="the finding's title")
    evidencing.add_argument("--repro", type=Path, required=True)
    evidencing.add_argument("--log", type=Path, required=True)
    releasing = commands.add_parser("release")
    releasing.add_argument("issue", type=int)
    args = parser.parse_args(argv)
    # the policy's adapters, read at the first port call, as gatekeeper.py's main does
    gatekeeper.running, gatekeeper.using = True, None
    try:
        gatekeeper.one_repo()
        if args.command == "evidence":
            return gatekeeper.evidence(args.pr, args.number, args.finding, args.repro, args.log)
        if args.command == "brief":
            if args.since:
                return brief_since(args.pr, args.since, args.priorities)
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
