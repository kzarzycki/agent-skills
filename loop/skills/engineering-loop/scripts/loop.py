#!/usr/bin/env -S uv run -q --script
# /// script
# requires-python = ">=3.9"
# dependencies = ["PyYAML==6.0.3"]
# ///
"""The loop's own operations, which decide nothing, so they are not the gatekeeper's.

    uv run scripts/loop.py brief <pr> [--priorities <file>] [--proof <log>]...  # a verifier pass's brief
    uv run scripts/loop.py release <issue>            # parked or dropped: remove the assignee the loop added

Both read the PR or the issue through the `gatekeeper` skill's gatekeeper.py and its ports, found where the host
installed that skill (`installed` below), and exit as it does: 0 done, 1 refused with the reason.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType


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


def brief(pr: int, priorities: Path | None, proofs: list[Path]) -> int:
    """Print a verifier pass's brief (lead.md step 7) with its facts read from the PR, so none is a previous pass's: the
    verifier role, the base (the merge-base with the default branch), the head, the spec, the pass (one after the
    newest verdict review's) and its report path, from pass 2 the previous report and its head, then the priorities
    file as is and loop.md's `## Verifier brief`, read from loop.md where the policy is gatekeeper.md's. A proof log
    whose first line isn't the head is refused, since the verifier counts a stale proof as missing and spends the
    pass on it."""
    _, loop = gatekeeper.project()
    if isinstance(loop, gatekeeper.Policy):
        where = gatekeeper.toplevel() / gatekeeper.LOOP
        loop = gatekeeper.read(where) if where.exists() else None
    pull = gatekeeper.pull_request(pr)
    head = pull["headRefOid"]
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
    role = os.path.relpath(Path(__file__).resolve().parents[1] / "verifier.md")
    lines = [
        f"Review PR #{pr} as the verifier, pass {number}, following {role}.",
        f"- Base: {base}",
        f"- Reviewed head: {head}",
        f"- Spec: {', '.join(f'#{n}' for n in issues) or 'none linked'}",
        f"- Report: tmp/loop/pr{pr}-v{number}.md",
    ]
    if reviewed:
        newest = next(commit for commit, n, _ in reversed(reviewed) if n == number - 1)
        lines.append(
            f"- Previous report: tmp/loop/pr{pr}-v{number - 1}.md, on {newest}: review the diff since that head and"
            " rerun its repros"
        )
    lines += [f"- Proof log: {log} (its first line is the head)" for log in proofs]
    if priorities is not None:
        lines += ["", "Priorities:", priorities.read_text().rstrip()]
    # as written, but for the blank lines around it: indentation may be a snippet's
    if (own := gatekeeper.section(loop or "", "Verifier brief").strip("\n")).strip():
        lines += ["", own]
    print("\n".join(lines))
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    commands = parser.add_subparsers(dest="command", required=True)
    briefing = commands.add_parser("brief")
    briefing.add_argument("pr", type=int)
    briefing.add_argument("--priorities", type=Path)
    briefing.add_argument("--proof", type=Path, action="append", default=[])
    releasing = commands.add_parser("release")
    releasing.add_argument("issue", type=int)
    args = parser.parse_args(argv)
    gatekeeper.using = (
        None  # the policy's adapters, read at the first port call, as gatekeeper.py's main does
    )
    try:
        gatekeeper.one_repo()
        if args.command == "brief":
            return brief(args.pr, args.priorities, args.proof)
        return release(args.issue)
    except gatekeeper.Refused as exc:
        print(exc)
        return 1
    except subprocess.CalledProcessError as exc:
        print(exc.stderr.strip() or exc)  # gh's reason
        return 1
    finally:
        gatekeeper.using = gatekeeper.GITHUB


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
