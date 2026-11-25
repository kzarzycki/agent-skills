#!/usr/bin/env python3
"""The chief of staff's nightly hygiene scan (SKILL.md, "Hygiene scan").

Five checks and one list, printed as a report; the exit code is 0 only when there is nothing to
report and no host or repo went unreached.

    hygiene.py [--file <values>] [--home <dir>] [--today <date>] [--no-archive] [--json]
               [--pack <dir>] [--pack-repo <url>] [--installed-cmd <cmd>] [--checkouts <dir>]

* ``board``: the board (``board``) is over 4 KB. It only reports: the board is the owner's, so the
  scan never rewrites it.
* ``retention``: a report in ``reports_dir`` older than 14 days that no registry or state file
  names (its lead was reaped) moves to ``<reports_dir>/archive/``, unless ``--no-archive``. A
  report any registry (the root's and each manager's) or state file still names is a live lead's
  and is never touched; when a registry cannot be read, nothing is archived.
* ``decisions``: a ``budget``, ``parked`` or ``models.tiers`` entry past its end date, or a
  ``budget`` or ``parked`` entry with none. The values file is the owner's, so it names each entry
  to drop and edits nothing.
* ``pack lag``: for each host, each installed package whose version is behind the pack's latest
  release tag (``<package>-v<version>`` on ``--pack-repo``). ``--installed-cmd`` is run once per
  host with ``{host}`` replaced and prints ``{"<package>": "<version>"}``.
* ``restate``: a setup file (``CLAUDE.md``, ``AGENTS.md``, ``docs/agents/*.md``) of a repo in
  ``hygiene.repos``, found at ``--checkouts/<name>``, with a sentence copied from a skill of the
  pack at ``--pack``.
* ``not reached``: every host and repo the scan could not read, since a skipped one looks the same
  as a clean one.

Reads ``board``, ``registry``, ``managers``, ``reports_dir``, ``hosts.table``, ``budget``,
``parked``, ``models.tiers`` and ``hygiene.repos`` through ``cos_values``. The retention, the
board limit and the authors are fixed (the account the scan runs as): no key sets them.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import shlex
import socket
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cos_values

RETENTION_DAYS = 14
BOARD_MAX_KB = 4
DEFAULT_PACK_REPO = "https://github.com/kzarzycki/agent-skills"
MIN_WORDS = 10  # a sentence of fewer words is too short to be a copied rule
SETUP_FILES = ("CLAUDE.md", "AGENTS.md")


def _date(v) -> dt.date | None:
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, dt.date):
        return v
    try:
        return dt.date.fromisoformat(str(v))
    except ValueError:
        return None


def _version(v: str) -> tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", v))


def _words(text: str) -> str:
    return " ".join(re.sub(r"[`*_>#\-]", " ", text).lower().split())


# board -----------------------------------------------------------------------------------------


def check_board(board: Path) -> list[str]:
    if not board.is_file():
        return []
    kb = board.stat().st_size / 1024
    # ponytail: open question 7 proposed a fixed 4 KB that only reports; open question 13 (the
    # board's section names) is not settled, so the check reads no section.
    if kb <= BOARD_MAX_KB:
        return []
    return [
        f"{board} is {kb:.1f} KB, over {BOARD_MAX_KB} KB: move finished items to a dated archive"
    ]


# retention -------------------------------------------------------------------------------------


def _registries(values: cos_values.Values) -> list[Path]:
    root = values.path("registry")
    out = [root]
    for m in values.get("managers"):
        r = Path(m["registry"]).expanduser()
        out.append(r if r.is_absolute() else root.parent / r)
    return out


def _live_text(registries: list[Path]) -> str:
    """Every registry and state file's text. A registry that exists but cannot be read raises."""
    text = []
    for reg in registries:
        for f in (reg, reg.with_suffix(".state.json")):
            if f.exists():
                text.append(f.read_text())  # a directory or an unreadable file raises OSError
    return "\n".join(text)


def check_retention(
    values: cos_values.Values, today: dt.date, *, archive: bool
) -> tuple[list[str], list[str]]:
    """(findings, archived paths). A file a registry or state names is never a candidate."""
    reports = values.path("reports_dir")
    if not reports.is_dir():
        return [], []
    try:
        live = _live_text(_registries(values))
    except OSError as e:
        return [f"retention skipped, a registry cannot be read ({e}): nothing archived"], []
    skip = {values.path("board"), values.path("registry"), values.path("decisions.file")}
    if values.file:
        skip.add(values.file.resolve())
    found, moved = [], []
    for f in sorted(reports.iterdir()):
        if not f.is_file() or f in skip or f.name.startswith("."):
            continue
        if f.suffix in (".registry",) or f.name.endswith((".state.json", ".events.jsonl")):
            continue
        age = (today - dt.datetime.fromtimestamp(f.stat().st_mtime, dt.timezone.utc).date()).days
        # ponytail: a name found anywhere in a registry or state file counts as live (a few
        # reports stay that should go, none that are live is moved).
        if age <= RETENTION_DAYS or f.name in live or str(f) in live:
            continue
        if archive:
            dest = reports / "archive" / f.name
            dest.parent.mkdir(exist_ok=True)
            if dest.exists():
                dest = dest.with_name(f"{dest.stem}.{int(f.stat().st_mtime)}{dest.suffix}")
            f.rename(dest)
            moved.append(str(dest))
            found.append(f"archived {f.name} ({age} days old, no live lead names it)")
        else:
            found.append(f"{f.name} is {age} days old and no live lead names it (would archive)")
    return found, moved


# decisions -------------------------------------------------------------------------------------


def check_decisions(values: cos_values.Values, today: dt.date) -> list[str]:
    out: list[str] = []

    def judge(label: str, until) -> None:
        d = _date(until)
        if d is None:
            out.append(f"{label}: no end date (add `until`)")
        elif d < today:
            out.append(f"{label}: ended {d}, drop it from the values file")

    budget = values.get("budget")
    if budget:
        judge("budget", budget.get("until"))
    for i, item in enumerate(values.get("parked")):
        label = f"parked[{i}]" + (f" {item.get('item')}" if isinstance(item, dict) else "")
        judge(label, item.get("until") if isinstance(item, dict) else None)
    for job, spec in values.get("models.tiers").items():
        if isinstance(spec, dict) and "until" in spec:  # a tier with no `until` is a standing one
            judge(f"models.tiers.{job}", spec["until"])
    return out


# pack lag --------------------------------------------------------------------------------------


def latest_releases(pack_repo: str) -> dict[str, str]:
    r = subprocess.run(
        ["git", "ls-remote", "--tags", "--refs", pack_repo, "*-v*"],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if r.returncode:
        raise RuntimeError(f"git ls-remote {pack_repo}: {r.stderr.strip()}")
    best: dict[str, str] = {}
    for line in r.stdout.splitlines():
        m = re.search(r"refs/tags/(.+)-v(\d+(?:\.\d+)*)$", line)
        if m and (m[1] not in best or _version(m[2]) > _version(best[m[1]])):
            best[m[1]] = m[2]
    return best


def hosts_in_scope(values: cos_values.Values) -> list[str]:
    table = values.get("hosts.table")
    scoped = set(values.get("hygiene.repos")) or set(table)
    hosts = sorted({h for repo, hs in table.items() if repo in scoped or not scoped for h in hs})
    return hosts or [socket.gethostname()]


def check_pack_lag(
    hosts: list[str], installed_cmd: str | None, pack_repo: str
) -> tuple[list[str], list[str]]:
    """(findings, hosts not reached)."""
    if not installed_cmd:
        return [], list(hosts)
    try:
        latest = latest_releases(pack_repo)
    except (RuntimeError, OSError, subprocess.TimeoutExpired) as e:
        return [], [f"{h} (latest releases unreadable: {e})" for h in hosts]
    found, missed = [], []
    for host in hosts:
        try:
            r = subprocess.run(
                shlex.split(installed_cmd.replace("{host}", shlex.quote(host))),
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
            installed = json.loads(r.stdout) if r.returncode == 0 else None
            if not isinstance(installed, dict):
                raise TypeError(r.stderr.strip() or "no JSON object")
        except (ValueError, TypeError, OSError, subprocess.TimeoutExpired) as e:
            missed.append(f"{host} ({e})")
            continue
        for pkg, have in sorted(installed.items()):
            want = latest.get(pkg)
            if want and _version(str(have)) < _version(want):
                found.append(f"{host}: {pkg} {have} is behind the release {want}")
    return found, missed


# restate ---------------------------------------------------------------------------------------


def pack_sentences(pack: Path) -> dict[str, str]:
    """Normalized sentence -> the skill it is from, for every long enough sentence in the pack."""
    out: dict[str, str] = {}
    for f in sorted(pack.glob("*/skills/*/SKILL.md")):
        text = re.sub(r"\n\s*\n", "\n", f.read_text().split("---", 2)[-1])
        for s in re.split(r"(?<=[.!?])\s+|\n", text):
            n = _words(s)
            if len(n.split()) >= MIN_WORDS:
                out.setdefault(n, f.parent.name)
    return out


def check_restate(
    repos: list[str], checkouts: Path | None, pack: Path | None
) -> tuple[list[str], list[str]]:
    """(findings, repos not reached)."""
    if not repos:
        return [], []
    if checkouts is None or pack is None or not pack.is_dir():
        return [], [f"{r} (no --checkouts and --pack to read it with)" for r in repos]
    rules = pack_sentences(pack)
    found, missed = [], []
    for repo in repos:
        root = checkouts / repo.rsplit("/", 1)[-1]
        if not root.is_dir():
            missed.append(f"{repo} (no checkout at {root})")
            continue
        files = [root / n for n in SETUP_FILES] + sorted((root / "docs" / "agents").glob("*.md"))
        for f in files:
            if not f.is_file():
                continue
            body = _words(f.read_text())
            for rule, skill in rules.items():
                if rule in body:
                    found.append(
                        f"{repo}: {f.relative_to(root)} restates the {skill} skill: “{rule[:70]}…”"
                    )
    return found, missed


# main ------------------------------------------------------------------------------------------


def scan(values: cos_values.Values, args: argparse.Namespace) -> dict:
    today = _date(args.today) if args.today else dt.datetime.now(dt.timezone.utc).date()
    retention, archived = check_retention(values, today, archive=not args.no_archive)
    lag, host_miss = check_pack_lag(
        hosts_in_scope(values), args.installed_cmd, args.pack_repo or DEFAULT_PACK_REPO
    )
    restate, repo_miss = check_restate(
        values.get("hygiene.repos"),
        Path(args.checkouts).expanduser() if args.checkouts else None,
        Path(args.pack).expanduser() if args.pack else None,
    )
    return {
        "board": check_board(values.path("board")),
        "retention": retention,
        "archived": archived,
        "decisions": check_decisions(values, today),
        "pack lag": lag,
        "restate": restate,
        "not reached": host_miss + repo_miss,
    }


def render(report: dict) -> str:
    out = []
    for name, items in report.items():
        if name == "archived":
            continue
        out.append(f"## {name}")
        out += [f"- {i}" for i in items] or ["- none"]
        out.append("")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="The chief of staff's nightly hygiene scan.")
    ap.add_argument("--file", help="the values file")
    ap.add_argument("--home", help="the setup's home folder")
    ap.add_argument("--today", help=argparse.SUPPRESS)
    ap.add_argument("--no-archive", action="store_true", help="report old reports, move none")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--pack", help="a clone of the pack (its skills' sentences are the rules)")
    ap.add_argument("--pack-repo", help=f"where releases are tagged (default {DEFAULT_PACK_REPO})")
    ap.add_argument("--installed-cmd", help="prints a host's installed versions as JSON; {host}")
    ap.add_argument("--checkouts", help="folder holding each hygiene.repos repo's checkout")
    a = ap.parse_args(argv)
    try:
        report = scan(cos_values.load(a.file, home=a.home), a)
    except cos_values.ValuesError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2) if a.json else render(report))
    return int(any(v for k, v in report.items() if k != "archived"))


if __name__ == "__main__":
    sys.exit(main())
