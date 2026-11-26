#!/usr/bin/env python3
"""The chief-of-staff setup's values file and the one loader every pack script uses.

A setup (one chief of staff and its home folder) keeps its own settings in one YAML file,
``cos-values.yml``, in that home folder, never in a project repo: a project repo holds no
coordinator instructions (SKILL.md, "A tree of coordinators"). A setup with no file gets the pack
defaults below. The file holds only what differs from them; the owner edits it by hand.

Scripts import this module::

    import cos_values
    values = cos_values.load()                 # the home's file, else defaults
    values.get("delegation.on")                # the file's value, else the pack default
    values.require("cos_session")              # fail naming the key when nothing is set
    values.path("registry")                    # a path key, resolved to an absolute path

Interface (stable; a change is announced in the pack's changelog):

* ``load(path=None, *, home=None) -> Values``: reads the file (see ``find``), checks every key.
* ``Values.get(key)``: the set value, else the default (``None`` where the default is "the
  session's own" or "none set": the caller resolves it). An unknown key raises ``ValuesError``.
* ``Values.require(key)``: like ``get``, but raises ``ValuesError`` naming the key when it is ``None``.
* ``Values.is_set(key)``: whether the file sets it. ``Values.path(key)``: see above.
* ``ValuesError``: one error naming every missing, unknown or wrongly typed key (``.keys``).
* ``KEYS``: the key table (``Key``), the one place a key, its default and its kind are written.

The file's keys are nested as the dotted names read (``hosts.table`` is ``hosts:`` then
``table:``). A key the table does not list is an error naming it, with the nearest key, because a
typo would otherwise look like a default. Defaults hold no private name, host or secret: this
repo is public.

A YAML date (``until: 2030-01-31``) arrives as a ``datetime.date``, not a string; ``budget`` and
``parked`` hold free-form entries the loader does not check.

    cos_values.py [--file <path>] [--home <dir>] check | show | keys | get <key>
"""

from __future__ import annotations

import argparse
import copy
import difflib
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # run as `python3 cos_values.py` where PyYAML isn't installed
    sys.exit(
        f"{Path(sys.argv[0]).name} needs PyYAML: run it with `uv run {sys.argv[0]}`, which installs it"
    )

FILE_NAME = "cos-values.yml"
ENV_VAR = "COS_VALUES"


class ValuesError(ValueError):
    """A values file or key problem; ``keys`` names each key at fault."""

    def __init__(self, message: str, keys: tuple[str, ...] = ()):
        super().__init__(message)
        self.keys = keys


@dataclass(frozen=True)
class Key:
    name: str
    kind: str
    default: Any
    doc: str
    used_by: tuple[str, ...] = ()  # the setups the inventory says need a non-default value
    choices: tuple[str, ...] = ()
    extend: bool = False  # the file adds to the default list, never replaces it
    base: str = ""  # a path key resolves against "home" or "board" (the board's folder)


# What the owner never delegates (SKILL.md, "What stays on the card").
OWNER_ONLY = (
    "money",
    "credentials-and-2fa",
    "sudo",
    "send-outside-project",
    "irreversible-delete",
    "production-or-trading-path",
    "merge-long-lived-feature-branch",
    "risk-critical-paths",
    "owner-own-list",
)
JOBS = ("lead", "worker", "mechanical", "verifier", "scheduled")

F, S = "first", "second"


def _keys() -> dict[str, Key]:
    k = [
        Key("server", "str", None, "URL of the agent server; None: the session's own", (S, F)),
        Key(
            "cos_session",
            "str",
            None,
            "Session for supervisor posts and relays; None: the CoS's own",
            (S, F),
        ),
        Key(
            "registry",
            "str",
            "leads.registry",
            "Leads registry file, beside the board",
            (S, F),
            base="board",
        ),
        Key("board", "str", "tmp/loop/chief-of-staff.md", "Handover board path", (F,), base="home"),
        Key("reports_dir", "str", "tmp/loop", "Folder for leads' reports", (F, S), base="home"),
        Key(
            "hosts.table",
            "map",
            {},
            "Repo -> hosts it may run on; empty: any host that offers the harness",
            (F,),
        ),
        Key(
            "hosts.owner_requested_only",
            "strs",
            [],
            "Hosts that take only starts the owner asked for",
            (F,),
        ),
        Key(
            "managers",
            "managers",
            [],
            "Project managers: each has scope (repos), registry, board",
            (F,),
        ),
        Key("delegation.on", "bool", False, "Whether the owner delegates specs and merges", (S, F)),
        # ponytail: the owner's own entries add to the pack's list, never shorten it.
        Key(
            "owner_only",
            "strs",
            list(OWNER_ONLY),
            "What delegation never covers (the file adds to it)",
            (S, F),
            extend=True,
        ),
        Key(
            "models.tiers",
            "tiers",
            {},
            "Model per job (lead, worker, mechanical, verifier, scheduled), each with an optional `until` date",
            (S, F),
        ),
        Key(
            "budget",
            "map",
            {},
            "Weekly limits, pace formula, pauses, cap on leads per manager; each with an end date",
            (S, F),
        ),
        Key("parked", "list", [], "Parked list; each entry with an end date", (S, F)),
        Key(
            "decisions.file",
            "str",
            "decisions.md",
            "Decision log path, beside the board",
            (F, S),
            base="board",
        ),
        Key("hygiene.repos", "strs", [], "Repos the nightly scan covers", (F, S)),
        Key("pin.tag_prefix", "str", None, "Release-tag prefix; None: no pin updater", (S,)),
    ]
    return {x.name: x for x in k}


KEYS: dict[str, Key] = _keys()
_GROUPS = {".".join(n.split(".")[:i]) for n in KEYS for i in range(1, n.count(".") + 1)}
_MANAGER_FIELDS = {"scope": "strs", "registry": "str", "board": "str"}


class _Loader(yaml.SafeLoader):
    """YAML 1.2 booleans: only true/false, so a bare ``on:`` key (``delegation: on: true``) stays
    the string ``on``, not ``True``, and a value ``yes`` is a string the check then refuses."""


_Loader.yaml_implicit_resolvers = {
    ch: [(tag, rx) for tag, rx in rs if tag != "tag:yaml.org,2002:bool"]
    for ch, rs in yaml.SafeLoader.yaml_implicit_resolvers.items()
}
_Loader.add_implicit_resolver("tag:yaml.org,2002:bool", re.compile(r"^(?:true|false)$"), list("tf"))


def _is_str(v: Any) -> bool:
    return isinstance(v, str) and bool(v.strip())


def _is_num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0


def _check_kind(kind: str, v: Any) -> str | None:
    """The reason ``v`` is the wrong shape for ``kind``, or None."""
    if kind == "str":
        return None if _is_str(v) else "a non-empty string"
    if kind == "bool":
        return None if isinstance(v, bool) else "true or false"
    if kind == "int":
        return None if _is_num(v) and isinstance(v, int) else "a positive whole number"
    if kind == "num":
        return None if _is_num(v) else "a positive number"
    if kind == "strs":
        ok = isinstance(v, list) and all(_is_str(x) for x in v)
        return None if ok else "a list of non-empty strings"
    if kind == "list":
        return None if isinstance(v, list) else "a list"
    if kind == "map":
        return None if isinstance(v, dict) else "a mapping"
    if kind == "str|map":
        return None if _is_str(v) or isinstance(v, dict) else "a string or a mapping"
    if kind == "str|strs":
        return (
            None
            if _check_kind("str", v) is None or _check_kind("strs", v) is None
            else "a string or a list of strings"
        )
    return None


def _check_key(key: Key, v: Any, errors: list[tuple[str, str]]) -> None:
    def bad(name: str, why: str) -> None:
        errors.append((name, f"{name}: must be {why}"))

    if key.kind == "managers":
        if not isinstance(v, list):
            return bad(key.name, "a list of mappings with scope, registry and board")
        for i, m in enumerate(v):
            at = f"{key.name}[{i}]"
            if not isinstance(m, dict):
                bad(at, "a mapping with scope, registry and board")
                continue
            for f in m:
                if f not in _MANAGER_FIELDS:
                    errors.append(
                        (
                            f"{at}.{f}",
                            f"{at}.{f}: unknown key; a manager has {', '.join(_MANAGER_FIELDS)}",
                        )
                    )
            for f, kind in _MANAGER_FIELDS.items():
                if f not in m:
                    errors.append((f"{at}.{f}", f"{at}.{f}: missing"))
                elif (why := _check_kind(kind, m[f])) is not None:
                    bad(f"{at}.{f}", why)
        return
    if key.kind == "tiers":
        if not isinstance(v, dict):
            return bad(key.name, "a mapping job -> model")
        for job, spec in v.items():
            at = f"{key.name}.{job}"
            if job not in JOBS:
                errors.append((at, f"{at}: unknown job; the jobs are {', '.join(JOBS)}"))
            elif (
                _is_str(spec)
                or isinstance(spec, dict)
                and _is_str(spec.get("model"))
                and set(spec) <= {"model", "until"}
            ):
                continue
            else:
                bad(at, "a model name, or a mapping with model and an optional until")
        return
    if (why := _check_kind(key.kind, v)) is not None:
        return bad(key.name, why)
    if key.choices:
        for c in v.values() if isinstance(v, dict) else [v]:
            if c not in key.choices:
                bad(key.name, f"one of {', '.join(key.choices)} (got {c!r})")


def _near(name: str) -> str:
    if name in _GROUPS:
        subs = ", ".join(k for k in KEYS if k.startswith(f"{name}."))
        return f" (a group, not a key; its keys are {subs})"
    hit = difflib.get_close_matches(name, [*KEYS, *_GROUPS], n=1, cutoff=0.6)
    return f"; did you mean `{hit[0]}`?" if hit else ""


def _walk(node: Any, prefix: str, out: dict[str, Any], errors: list[tuple[str, str]]) -> None:
    if not isinstance(node, dict):
        errors.append((prefix.rstrip("."), f"{prefix.rstrip('.')}: must be a mapping of its keys"))
        return
    for k, v in node.items():
        name = f"{prefix}{k}"
        if name in KEYS:
            n = len(errors)
            _check_key(KEYS[name], v, errors)
            if len(errors) == n:
                out[name] = v
        elif name in _GROUPS:
            _walk(v, f"{name}.", out, errors)
        else:
            errors.append((name, f"{name}: unknown key{_near(name)}"))


def find(
    path: str | os.PathLike | None = None, *, home: str | os.PathLike | None = None
) -> Path | None:
    """The values file: ``path``, else ``$COS_VALUES``, else ``cos-values.yml`` in ``home`` (the
    current folder by default). A named file that is missing is an error; the home's own absent
    file is not (the setup then runs on the pack defaults)."""
    named = path or os.environ.get(ENV_VAR)
    if named:
        p = Path(named).expanduser()
        if not p.is_file():
            raise ValuesError(f"values file not found: {p}")
        return p
    p = Path(home or Path.cwd()).expanduser() / FILE_NAME
    return p if p.is_file() else None


class Values:
    def __init__(self, set_values: dict[str, Any], file: Path | None, home: Path):
        self._set = set_values
        self.file = file
        self.home = home

    def _key(self, key: str) -> Key:
        if key not in KEYS:
            raise ValuesError(f"{key}: unknown key{_near(key)}", (key,))
        return KEYS[key]

    def is_set(self, key: str) -> bool:
        self._key(key)
        return key in self._set

    def get(self, key: str) -> Any:
        k = self._key(key)
        if key not in self._set:
            return copy.deepcopy(k.default)
        v = copy.deepcopy(self._set[key])
        if k.extend:
            return [*k.default, *(x for x in v if x not in k.default)]
        return v

    def require(self, key: str) -> Any:
        v = self.get(key)
        if v is None:
            where = f" in {self.file}" if self.file else f" (no {FILE_NAME} found)"
            raise ValuesError(
                f"{key}: missing, and the pack has no default for it; set it{where}", (key,)
            )
        return v

    def path(self, key: str) -> Path:
        """A path key as an absolute path: ``~`` expanded, a relative one resolved against the
        home folder, or the board's folder for a file that sits beside the board."""
        k = self._key(key)
        if not k.base:
            raise ValuesError(f"{key}: not a path key", (key,))
        raw = self.require(key)
        p = Path(raw).expanduser()
        if p.is_absolute():
            return p
        root = self.home
        if k.base == "board":
            root = self.path("board").parent
        return root / p

    def as_dict(self) -> dict[str, Any]:
        """Every key with its effective value."""
        return {name: self.get(name) for name in KEYS}


def load(path: str | os.PathLike | None = None, *, home: str | os.PathLike | None = None) -> Values:
    """Load the setup's values; raises ``ValuesError`` naming each bad key."""
    file = find(path, home=home)
    base = Path(home).expanduser() if home else (file.parent if file else Path.cwd())
    base = base.resolve()
    if file is None:
        return Values({}, None, base)
    try:
        data = yaml.load(file.read_text(), Loader=_Loader)
    except yaml.YAMLError as e:
        raise ValuesError(f"{file}: not valid YAML: {e}") from e
    if data is None:
        data = {}
    out: dict[str, Any] = {}
    errors: list[tuple[str, str]] = []
    if not isinstance(data, dict):
        raise ValuesError(f"{file}: must be a mapping of keys")
    _walk(data, "", out, errors)
    if errors:
        msg = f"{file}: " + "; ".join(m for _, m in errors)
        raise ValuesError(msg, tuple(n for n, _ in errors))
    return Values(out, file, base)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Check, show or read the chief of staff's values file."
    )
    ap.add_argument("--file", help=f"the values file (else ${ENV_VAR}, else {FILE_NAME} in --home)")
    ap.add_argument("--home", help="the setup's home folder (default: the current folder)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check", help="validate the file; exit 1 naming each bad key")
    sub.add_parser("show", help="print every key's effective value as JSON")
    sub.add_parser("keys", help="print each key with its default and meaning")
    g = sub.add_parser("get", help="print one key's effective value as JSON")
    g.add_argument("key")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "keys":
            for k in KEYS.values():
                print(f"{k.name}\t{json.dumps(k.default)}\t{k.doc}")
            return 0
        v = load(a.file, home=a.home)
        if a.cmd == "check":
            print(f"ok: {v.file or 'no file, pack defaults'}")
        elif a.cmd == "show":
            print(json.dumps(v.as_dict(), indent=2, default=str))
        else:
            print(json.dumps(v.require(a.key), default=str))
    except ValuesError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
