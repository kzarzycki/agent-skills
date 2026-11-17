"""claude.ai's cloud environments, on the Claude Code login this host already has.

The one client for `/v1/environment_providers`: `omnigent_agent.py` resolves and pins an environment with it and
makes one with `cloud-env`, and engineering-loop's `cloud_verifier.py seed` stores its login with it. Not a command;
it is loaded by path, so a project's copy and an installed one never mix.

The token is read from the macOS keychain (`Claude Code-credentials`), else `~/.claude/.credentials.json`, and goes
only into a request's `Authorization` header: never into an argument list, a log or a message. An error names the
HTTP status and the server's own message with every secret this module was told about (`secret`) masked, since a
server can echo back what it was sent. `CLAUDE_CLOUD_API_BASE` replaces the API's base URL (a test's fake).

Standard library only, plus `claude` for the login's organization.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from pathlib import Path

PAGE = 100  # environments asked for per page; the listing follows `has_more` and `last_id`
PAGES = 20
DEFAULT = "Default"  # the environment Claude Code makes for an account's first cloud session


class Refused(Exception):
    """The login, the API or a lookup said no; the message says what to do."""


Run = Callable[..., subprocess.CompletedProcess]


def _run(*cmd: str, check: bool = True, **kw: object) -> subprocess.CompletedProcess:
    done = subprocess.run(cmd, capture_output=True, text=True, errors="replace", check=False, **kw)
    if check and done.returncode:
        raise Refused(
            f"`{' '.join(cmd)}` exited {done.returncode}: {(done.stderr or done.stdout).strip()[-300:]}"
        )
    return done


def base() -> str:
    return os.environ.get("CLAUDE_CLOUD_API_BASE", "https://api.anthropic.com").rstrip("/")


def headers(run: Run = _run, secret: Callable[..., None] = lambda *_: None) -> dict:
    """Headers for the environment API on this host's Claude Code login. ``secret`` is handed each token as it is
    read, so a caller that redacts its output knows them; ``run`` runs ``security`` and ``claude``."""
    raw = ""
    if sys.platform == "darwin":
        user = os.environ.get("USER") or run("id", "-un").stdout.strip()
        raw = run(
            "security",
            "find-generic-password",
            "-a",
            user,
            "-s",
            "Claude Code-credentials",
            "-w",
            check=False,
        ).stdout
    if not raw and (path := Path.home() / ".claude" / ".credentials.json").exists():
        raw = path.read_text()
    if not raw:
        raise Refused("no Claude Code login on this host: run `claude auth login`")
    oauth = json.loads(raw)["claudeAiOauth"]
    secret(oauth.get("accessToken"), oauth.get("refreshToken"))
    if oauth.get("expiresAt", 0) / 1000 < time.time() + 60:
        raise Refused(
            "the Claude Code login's token has expired: run `claude` once to refresh it, then try again"
        )
    org = json.loads(run("claude", "auth", "status", "--json").stdout)["orgId"]
    return {
        "Authorization": f"Bearer {oauth['accessToken']}",
        "anthropic-version": "2023-06-01",
        "anthropic-beta": "ccr-byoc-2025-07-29",
        "x-organization-uuid": org,
    }


def call(path: str, body: dict | None, auth: dict, masked: tuple[str, ...] = ()) -> dict:
    """``GET`` ``path`` (``body`` None), else ``POST`` it as JSON. A refusal is a ``Refused`` naming the status and
    the server's message, with each of ``masked`` cut out of it."""
    req = urllib.request.Request(
        base() + path,
        data=None if body is None else json.dumps(body).encode(),
        headers={"Content-Type": "application/json", **auth},
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        said = e.read().decode(errors="replace")
        for value in (auth.get("Authorization", "").removeprefix("Bearer "), *masked):
            if value and len(value) >= 8:
                said = said.replace(value, "[secret]")
        said = said[-400:]  # cut after masking: a secret the cut splits would keep its tail
        path_only = path.split("?")[0]
        raise Refused(
            f"{'POST' if body is not None else 'GET'} {path_only}: HTTP {e.code}: {said.strip()}"
        ) from None
    except urllib.error.URLError as e:
        raise Refused(f"{path.split('?')[0]}: {e.reason}") from None


def environments(auth: dict) -> list[dict]:
    """Every environment the login's organization holds, each with ``environment_id``, ``name`` and ``kind``."""
    found: list[dict] = []
    after = ""
    for _ in range(PAGES):
        query = urllib.parse.urlencode({"limit": PAGE, **({"after_id": after} if after else {})})
        page = call(f"/v1/environment_providers?{query}", None, auth)
        found += page.get("environments") or []
        after = page.get("last_id") or ""
        if page.get("has_more") is not True or not page.get("environments") or not after:
            break
    return found


def named(envs: list[dict], name: str) -> dict | None:
    """The one environment called ``name``; two of them is a ``Refused``, since either could be meant."""
    hits = [e for e in envs if e.get("name") == name]
    if len(hits) > 1:
        ids = ", ".join(str(e.get("environment_id")) for e in hits)
        raise Refused(
            f"{len(hits)} cloud environments are named {name!r} ({ids}): rename all but one"
        )
    return hits[0] if hits else None


def pick(envs: list[dict], env: str, repo: str) -> dict:
    """The environment a cloud session of ``repo`` runs in: the one called ``env`` when it is given, else the one
    named after the repository, else the account's ``Default``. A name that isn't there is refused, naming
    ``cloud-env``, which makes it."""
    make = "create it with `omnigent_agent.py cloud-env <checkout>` (from the checkout's .claude/cloud-setup.sh)"
    if env:
        if hit := named(envs, env):
            return hit
        raise Refused(f"no cloud environment named {env!r} on this host's claude login: {make}")
    for name in (repo, DEFAULT):
        if name and (hit := named(envs, name)):
            return hit
    raise Refused(
        f"no cloud environment named {repo!r} or {DEFAULT!r} on this host's claude login: {make}"
    )


def create(auth: dict, name: str, script: str, description: str) -> dict:
    """A new cloud environment called ``name`` with ``script`` as its setup script and no variables, as Claude
    Code makes its ``Default`` one."""
    return call(
        "/v1/environment_providers/cloud/create",
        {
            "name": name,
            "kind": "anthropic_cloud",
            "description": description,
            "config": {
                "environment_type": "anthropic",
                "cwd": "/home/user",
                "init_script": script,
                "environment": {},
                "languages": [
                    {"name": "python", "version": "3.11"},
                    {"name": "node", "version": "20"},
                ],
                "network_config": {"allowed_hosts": [], "allow_default_hosts": True},
            },
        },
        auth,
    )


def read(auth: dict, env_id: str) -> dict:
    return call(f"/v1/environment_providers/{env_id}", None, auth)


def update(auth: dict, env_id: str, current: dict, config: dict) -> dict:
    """Replace ``env_id``'s config with ``config``, keeping its name and description; an update takes no
    ``kind``. The values of the variables ``current`` holds are masked in a refusal."""
    variables = (current.get("config") or {}).get("environment") or {}
    return call(
        f"/v1/environment_providers/{env_id}",
        {"name": current["name"], "description": current.get("description", ""), "config": config},
        auth,
        masked=tuple(str(v) for v in variables.values()),
    )
