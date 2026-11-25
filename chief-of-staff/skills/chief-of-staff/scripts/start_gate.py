#!/usr/bin/env python3
"""The start gate: whether a lead for a repo may start on a host (SKILL.md, "Start gate").

    start_gate.py check --repo <repo> --host <host> [--owner-requested] [--registry <name>]

Exit 0 allows the start; exit 1 refuses it and prints each reason; exit 2 is a bad values file.
It reads ``hosts.table``, ``hosts.owner_requested_only`` and ``managers`` through ``cos_values``,
and refuses three things:

* a host in ``hosts.owner_requested_only`` when the start is not ``--owner-requested``: such a
  host takes only starts the owner asked for;
* a host the table does not list for the repo, once the table has any row. A repo the table does
  not list at all is refused too (ponytail: the epic leaves "absent repo" open; a table that
  names some repos is read as the whole list). A setup with no table is not restricted here;
* a repo in a manager's ``scope`` without that manager's registry: the lead must be recorded in
  the registry the manager's supervisor follows, so ``--registry`` must name it.

The gate does not measure the host: the capacity check (``omnigent_agent.py capacity``) stays the
one place that judges memory and CPU, and a setup with no table gets what it allows today.
Common options: ``--file`` (the values file), ``--home`` (the setup's home folder).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cos_values


def _hosts(v) -> list[str]:
    return [v] if isinstance(v, str) else list(v or [])


def refusals(
    values: cos_values.Values,
    repo: str,
    host: str,
    owner_requested: bool = False,
    registry: str | None = None,
) -> list[str]:
    """Every reason the start is refused; empty when it is allowed."""
    out: list[str] = []
    if host in values.get("hosts.owner_requested_only") and not owner_requested:
        out.append(f"host {host} takes only starts the owner asked for (pass --owner-requested)")
    table = values.get("hosts.table")
    if table:
        allowed = _hosts(table.get(repo))
        if repo not in table:
            out.append(f"repo {repo} is not in hosts.table")
        elif host not in allowed:
            out.append(f"host {host} is not allowed for {repo} (hosts.table: {', '.join(allowed)})")
    for m in values.get("managers"):
        if repo in m["scope"] and registry != m["registry"]:
            out.append(
                f"repo {repo} is managed: start it in its manager's registry {m['registry']}"
                + (f", not {registry}" if registry else " (pass --registry)")
            )
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Refuse a lead start the hosts table does not allow.")
    ap.add_argument("--file", help="the values file")
    ap.add_argument("--home", help="the setup's home folder")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="exit 0 to allow the start, 1 to refuse it")
    c.add_argument("--repo", required=True)
    c.add_argument("--host", required=True)
    c.add_argument("--owner-requested", action="store_true")
    c.add_argument("--registry", help="the registry the lead will be recorded in")
    a = ap.parse_args(argv)
    try:
        values = cos_values.load(a.file, home=a.home)
    except cos_values.ValuesError as e:
        print(f"start_gate: {e}", file=sys.stderr)
        return 2
    why = refusals(values, a.repo, a.host, a.owner_requested, a.registry)
    for r in why:
        print(f"REFUSED: {r}")
    if not why:
        print(f"ALLOWED: {a.repo} on {a.host}")
    return 1 if why else 0


if __name__ == "__main__":
    sys.exit(main())
