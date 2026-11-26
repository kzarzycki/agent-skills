#!/usr/bin/env python3
"""The pin updater: moves a consumer repo's pack pin to the newest release tag, safely.

A consumer repo pins the pack in its ``apm.yml`` (``ref: <tag_prefix>X.Y.Z``) and deploys it with
``apm install``. This script finds the newest tag with the prefix, and when it is newer than the
pin, rewrites the pin, installs, then runs ``apm update`` so the sibling packages the lock holds (transitive ones
too, which ``apm install`` keeps at their locked refs) move to their newest release, and ``apm audit --ci
--no-policy`` so a committed local edit to an installed skill fails the run. A clean run is committed, the
message listing a compare link for each pin that moved, the direct one and every lock entry the update moved.

    pin_update.py [--repo <dir>] [--dry-run] [--file <values>] [--home <dir>]
                  [--remote <url>] [--apm <command>] [--omnigent <omnigent_agent.py>]

Reads ``pin.tag_prefix`` (required: with none set there is no pin updater) and ``cos_session``
through ``cos_values``. Each outcome that needs a person (updated, skipped, rolled back) prints an
``ACTION NEEDED:`` line, and relays it to ``cos_session`` through the installed ``omnigent-agents``
script; with no ``cos_session`` set it only prints. How often it runs is the scheduler's business.

* It skips, changing nothing, when the repo's ``apm.yml``, its lock or any file the lock lists as
  deployed has uncommitted changes, since those edits are the consumer's.
* It refuses a jump the new release says it cannot take (#2709): a release ships `bump-from.yml` in its
  package folder (`oldest:` the oldest pin it can be bumped from, `via:` the release to stop at), and a
  pin older than `oldest` is told to move to `via` first, since the base's own gate must be able to judge
  the bump PR and an old one cannot judge a new one's files.
* It rolls back a failed install, a failed update, a failed audit, and an install or update that removes a
  skill file the repo had committed: tracked files are restored and files they added removed.
* It works only in ``--repo`` (default: the directory it runs in) and refuses the pack's own
  checkout, so it never touches a developer checkout.

Exit codes: 0 up to date, updated or skipped; 1 the install failed and was rolled back; 2 a usage
or values error.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import cos_values

try:
    import yaml
except ImportError:
    sys.exit(f"{Path(sys.argv[0]).name} needs PyYAML: run it with `uv run {sys.argv[0]}`")


class PinError(Exception):
    """A usage problem: exit 2."""


def git(repo: Path, *args: str, check: bool = True) -> str:
    r = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
    )
    if check and r.returncode:
        raise PinError(f"git {' '.join(args)}: {r.stderr.strip() or r.stdout.strip()}")
    return r.stdout


def version_key(tag: str, prefix: str) -> tuple[int, ...] | None:
    m = re.fullmatch(r"(\d+(?:\.\d+)*)", tag[len(prefix) :]) if tag.startswith(prefix) else None
    return tuple(int(p) for p in m.group(1).split(".")) if m else None


def newest_tag(remote: str, prefix: str) -> str | None:
    r = subprocess.run(
        ["git", "ls-remote", "--tags", "--refs", remote],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
    )
    if r.returncode:
        raise PinError(f"cannot list tags of {remote}: {r.stderr.strip()}")
    tags = [ln.split("refs/tags/", 1)[1] for ln in r.stdout.splitlines() if "refs/tags/" in ln]
    keyed = [(k, t) for t in tags if (k := version_key(t, prefix))]
    return max(keyed)[1] if keyed else None


def bump_floor(remote: str, git_path: str, tag: str) -> tuple[tuple[int, ...], str] | None:
    """`(oldest, via)` from the release's `bump-from.yml`, or None when it ships none (no limit)."""
    sub = "/".join(git_path.split("/")[2:])
    name = f"{sub}/bump-from.yml" if sub else "bump-from.yml"
    with tempfile.TemporaryDirectory() as tmp:
        env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
        for cmd in (["init", "-q"], ["fetch", "-q", "--depth", "1", remote, f"refs/tags/{tag}"]):
            if subprocess.run(
                ["git", "-C", tmp, *cmd], capture_output=True, check=False, env=env
            ).returncode:
                return None
        shown = subprocess.run(
            ["git", "-C", tmp, "show", f"FETCH_HEAD:{name}"],
            capture_output=True,
            text=True,
            check=False,
        )
    if shown.returncode:
        return None
    data = yaml.safe_load(shown.stdout) or {}
    oldest = version_key("v" + str(data.get("oldest", "")), "v")
    via = str(data.get("via", ""))
    return (oldest, via) if oldest and via else None


def pins(repo: Path, prefix: str) -> list[tuple[str, str]]:
    """(``owner/repo[/path]``, ref) of each apm dependency pinned to a tag with the prefix."""
    data = yaml.safe_load((repo / "apm.yml").read_text()) or {}
    out = []
    for dep in (data.get("dependencies") or {}).get("apm") or []:
        if isinstance(dep, dict) and str(dep.get("ref", "")).startswith(prefix) and dep.get("git"):
            out.append((str(dep["git"]), str(dep["ref"])))
    return out


def dirty(repo: Path) -> list[str]:
    """Uncommitted paths among apm.yml, the lock and every file the lock lists as deployed."""
    watched = ["apm.yml", "apm.lock.yaml"]
    lock = repo / "apm.lock.yaml"
    if lock.is_file():
        for dep in (yaml.safe_load(lock.read_text()) or {}).get("dependencies") or []:
            watched += [str(f) for f in dep.get("deployed_files") or []]
    out = git(repo, "status", "--porcelain", "--", *watched)
    return [ln[3:] for ln in out.splitlines()]


def modified(repo: Path) -> set[str]:
    """Tracked files that differ from HEAD (staged or not)."""
    return set(git(repo, "diff", "HEAD", "--name-only").splitlines())


def untracked(repo: Path) -> set[str]:
    return set(git(repo, "ls-files", "--others", "--exclude-standard").splitlines())


def refuse_pack_checkout(repo: Path) -> None:
    if (repo / ".claude-plugin" / "marketplace.json").is_file():
        raise PinError(f"{repo} is a checkout of the pack itself: the updater never touches one")


def notify(values: cos_values.Values, line: str, omnigent: str | None) -> None:
    print(line)
    session = values.get("cos_session")
    if not session:
        return
    script = Path(omnigent) if omnigent else installed_omnigent()
    r = subprocess.run(
        [sys.executable, "-B", str(script), "relay", session, line],
        capture_output=True,
        text=True,
        check=False,
    )
    if r.returncode:
        print(
            f"relay to cos_session failed (exit {r.returncode}): {r.stderr.strip()}",
            file=sys.stderr,
        )


def installed_omnigent() -> Path:
    """The installed ``omnigent-agents`` script, never a developer checkout of the pack."""
    # ponytail: the same layouts cos_page.installed knows; that module runs code on import, so this
    # keeps a short copy. A checkout counts only where AGENT_SKILLS_CHECKOUT is set.
    own = Path(__file__).resolve().parents[1]
    root = own.parent.parent.parent
    checkout = (root / ".git").exists() and (root / ".claude-plugin" / "marketplace.json").is_file()
    laid = not checkout or bool(os.environ.get("AGENT_SKILLS_CHECKOUT"))
    cache = Path.home() / ".claude" / "plugins" / "cache"
    cached = sorted(
        cache.glob("[!.]*/[!.]*/[!.]*/skills/omnigent-agents"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for folder in [
        *([own.parent / "omnigent-agents"] if laid else []),
        *(sorted(root.glob("[!.]*/skills/omnigent-agents")) if laid else []),
        *cached,
    ]:
        if (folder / "scripts" / "omnigent_agent.py").is_file():
            return folder / "scripts" / "omnigent_agent.py"
    raise PinError("needs the `omnigent-agents` skill: install the package that ships it")


def lock_refs(repo: Path) -> dict[str, tuple[str, str]]:
    """``owner/repo[/path]`` -> (resolved ref, deployed files joined) of every package in the lock."""
    lock = repo / "apm.lock.yaml"
    out: dict[str, tuple[str, str]] = {}
    if lock.is_file():
        for dep in (yaml.safe_load(lock.read_text()) or {}).get("dependencies") or []:
            key = "/".join(x for x in (dep.get("repo_url"), dep.get("virtual_path")) if x)
            out[key or str(dep.get("name"))] = (str(dep.get("resolved_ref") or ""), "")
    return out


def deployed(repo: Path) -> set[str]:
    lock = repo / "apm.lock.yaml"
    files: set[str] = set()
    if lock.is_file():
        for dep in (yaml.safe_load(lock.read_text()) or {}).get("dependencies") or []:
            files |= {str(f) for f in dep.get("deployed_files") or []}
    return files


def compare_link(git_path: str, old: str, new: str) -> str:
    owner, repo = git_path.split("/")[:2]
    return f"https://github.com/{owner}/{repo}/compare/{old}...{new}"


def run(args: argparse.Namespace) -> int:
    values = cos_values.load(args.file, home=args.home)
    prefix = values.require("pin.tag_prefix")
    repo = Path(args.repo).resolve()
    refuse_pack_checkout(repo)
    if not (repo / "apm.yml").is_file():
        raise PinError(f"{repo}: no apm.yml")
    found = pins(repo, prefix)
    if not found:
        print(f"no dependency in {repo}/apm.yml is pinned to a `{prefix}` tag: nothing to do")
        return 0
    say = lambda line: notify(values, line, args.omnigent)
    for git_path, old in found:
        remote = args.remote or "https://github.com/" + "/".join(git_path.split("/")[:2])
        new = newest_tag(remote, prefix)
        if new is None or version_key(new, prefix) <= (version_key(old, prefix) or ()):
            print(f"{git_path}: {old} is the newest `{prefix}` tag")
            continue
        link = compare_link(git_path, old, new)
        floor = bump_floor(remote, git_path, new)
        if floor and (version_key(old, prefix) or ()) < floor[0]:
            say(
                f"ACTION NEEDED: pin update {old} -> {new} refused in {repo.name}: {new} can be "
                f"bumped only from {'.'.join(map(str, floor[0]))} or newer, since the base's own "
                f"gate cannot judge a jump that large. Bump to {prefix}{floor[1]} first, land "
                f"it, then run the updater again. Changes: {link}"
            )
            continue
        if args.dry_run:
            print(f"{git_path}: would move {old} to {new} ({link})")
            continue
        edited = dirty(repo)
        if edited:
            say(
                f"ACTION NEEDED: pin update {old} -> {new} skipped in {repo.name}: uncommitted "
                f"changes in {', '.join(edited[:5])}{' …' if len(edited) > 5 else ''}. "
                f"Commit or revert them; changes: {link}"
            )
            continue
        text = (repo / "apm.yml").read_text()
        if text.count(f"ref: {old}") != 1:
            say(
                f"ACTION NEEDED: pin update {old} -> {new} skipped in {repo.name}: "
                f"`ref: {old}` is not on exactly one line of apm.yml. Changes: {link}"
            )
            continue
        before, was_modified = untracked(repo), modified(repo)
        refs_before, files_before = lock_refs(repo), deployed(repo)
        (repo / "apm.yml").write_text(text.replace(f"ref: {old}", f"ref: {new}"))
        failure = ""
        for step in (["install"], ["update"], ["audit", "--ci", "--no-policy"]):
            done = subprocess.run(
                [*args.apm.split(), *step], cwd=repo, capture_output=True, text=True, check=False
            )
            if done.returncode:
                tail = (done.stderr.strip() or done.stdout.strip()).splitlines()[-1:]
                failure = f"`apm {step[0]}`: {tail[0] if tail else f'exit {done.returncode}'}"
                break
            if step[0] != "audit":
                # An install or update that deletes a skill file the repo committed is a loss.
                gone = sorted(f for f in files_before if not (repo / f).exists())
                if gone:
                    failure = f"`apm {step[0]}` removed {', '.join(gone[:5])}"
                    break
        if failure:
            # Restore every tracked file the run changed (the pre-run state of the watched set was
            # clean), then remove what it added.
            if changed := sorted(modified(repo) - was_modified):
                git(repo, "checkout", "HEAD", "--", *changed)
            for extra in untracked(repo) - before:
                path = repo / extra
                if path.is_file() or path.is_symlink():
                    path.unlink()
            say(
                f"ACTION NEEDED: pin update {old} -> {new} failed in {repo.name} and was rolled "
                f"back ({failure}). Changes: {link}"
            )
            return 1
        links = [link]
        for pkg, (ref, _) in lock_refs(repo).items():
            was = refs_before.get(pkg, ("", ""))[0]
            if was and ref and was != ref and pkg != git_path:
                links.append(compare_link(pkg, was, ref))
        watched = sorted({"apm.yml", "apm.lock.yaml"} | files_before | deployed(repo))
        git(repo, "add", "-A", "--", *watched)
        git(
            repo,
            "commit",
            "-q",
            "-m",
            f"chore: move the {prefix.rstrip('-v')} pin {old} -> {new}\n\n"
            + "\n".join(f"Changes: {u}" for u in links),
        )
        say(
            f"ACTION NEEDED: {repo.name} pin moved {old} -> {new}, installed, audited and "
            f"committed: review. Changes: {' '.join(links)}"
        )
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--repo", default=".", help="the consumer repo (default: the current directory)")
    p.add_argument("--dry-run", action="store_true", help="print what would move; change nothing")
    p.add_argument("--file", help="the values file")
    p.add_argument("--home", help="the setup's home folder")
    p.add_argument("--remote", help="tag source (default: the dependency's GitHub repo)")
    p.add_argument("--apm", default="apm", help="the install command's program (default: apm)")
    p.add_argument(
        "--omnigent", help="omnigent_agent.py to relay with (default: the installed one)"
    )
    args = p.parse_args()
    try:
        return run(args)
    except (PinError, cos_values.ValuesError) as e:
        print(f"pin_update.py: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
