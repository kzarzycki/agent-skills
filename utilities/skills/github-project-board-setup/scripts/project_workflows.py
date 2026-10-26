#!/usr/bin/env python3
"""Switch on and configure a GitHub Projects board's built-in workflows, which no public API writes.

    uv run --with playwright python scripts/project_workflows.py <spec.json> [--dry-run]

GraphQL and REST read workflows and delete them, but cannot switch one on or set what it does. The
web UI does that with POST (a new workflow) and PUT (an existing one, by its number) to
https://github.com/memexes/<project REST id>/workflows on the signed-in session, so this script sends
those same requests with fetch() from a background tab of a browser that is signed in to GitHub,
attached over CDP at CDP_URL (default http://127.0.0.1:9222). It needs no token and fills no form;
`gh` (with the `project` scope) only looks up ids. The project's REST `id` is the memex id.

The spec names everything by name, since option ids change whenever a field is edited:

    {"owner": "example-org", "number": 12,
     "workflows": [
       {"name": "Auto-add to project", "query": "is:pr is:open", "repository": "example-org/example-repo"},
       {"name": "Item added to project", "contentTypes": ["PullRequest"], "set": {"Status": "Open"}},
       {"name": "Pull request merged", "set": {"Status": "Merged"}},
       {"name": "Auto-close issue", "enabled": false}]}

`name` is the workflow's name as the board's Workflows page lists it. Each request starts from the
page's own default for that workflow, or its current one, with the spec's `set` (one field and
option), `query`, `repository` and `contentTypes` filled in, so a workflow kind the script has never
seen needs no code. A workflow the spec leaves out is left as it is. `--dry-run` prints the requests
and sends none. Exit 1 on the first refused request, with GitHub's reply: the endpoint is internal,
so a refusal after a GitHub change means capturing the web UI's request again (the browser's network
panel, saving one workflow) and updating `request()`.
"""

from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
from collections.abc import Callable
from typing import Any

CDP_URL = os.environ.get("CDP_URL", "http://127.0.0.1:9222")
FETCH = """async ([url, method, payload]) => {
  const r = await fetch(url, {method, credentials: "same-origin", body: JSON.stringify(payload),
    headers: {"content-type": "application/json", accept: "application/json",
              "x-requested-with": "XMLHttpRequest", "github-verified-fetch": "true"}});
  return [r.status, await r.text()];
}"""


def request(
    want: dict[str, Any],
    current: list[dict[str, Any]],
    defaults: list[dict[str, Any]],
    fields: dict[str, dict[str, Any]],
    repository_id: Callable[[str], int],
) -> tuple[str, dict[str, Any]]:
    """The method and body that make the board's workflow `want["name"]` what the spec entry says.

    `current` and `defaults` are the workflows page's `memex-workflows-data` and
    `memex-workflow-configurations-data`; `fields` is the project's REST field list by name."""
    have = next((w for w in current if w["name"] == want["name"]), None)
    base = have or next(
        (c["defaultWorkflow"] for c in defaults if c["defaultWorkflow"]["name"] == want["name"]),
        None,
    )
    if base is None:
        raise ValueError(f"no workflow named {want['name']!r} on this board")
    actions = copy.deepcopy(base["actions"])
    for action in actions:
        args = action["arguments"]
        if action["actionType"] == "set_field" and "set" in want:
            ((name, value),) = want["set"].items()
            if name not in fields:
                raise ValueError(f"the board has no field {name!r}")
            option = next(
                (o for o in fields[name].get("options", []) if o["name"]["raw"] == value), None
            )
            if option is None:
                raise ValueError(f"{name} has no option {value!r}")
            args.update(fieldId=fields[name]["id"], fieldOptionId=option["id"])
        if "query" in args and "query" in want:
            args["query"] = want["query"]
        if "repositoryId" in args and "repository" in want:
            args["repositoryId"] = repository_id(want["repository"])
    body = {
        "name": want["name"],
        "contentTypes": want.get("contentTypes", base["contentTypes"]),
        "enabled": want.get("enabled", True),
        "actions": actions,
    }
    if have:
        return "PUT", {"workflowNumber": have["number"], **body}
    # a new workflow's actions get their ids from GitHub
    for action in actions:
        action.pop("id", None)
    return "POST", {"workflow": {**body, "triggerType": base["triggerType"]}}


def gh(*args: str) -> Any:
    return json.loads(
        subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout
    )


def main(argv: list[str]) -> int:
    if not argv or argv[0].startswith("-"):
        print(__doc__, file=sys.stderr)
        return 2
    with open(argv[0]) as f:
        spec = json.load(f)
    dry = "--dry-run" in argv[1:]
    owner, number = spec["owner"], int(spec["number"])
    kind = "orgs" if gh("api", f"users/{owner}")["type"] == "Organization" else "users"
    base = f"{kind}/{owner}/projectsV2/{number}"
    memex = gh("api", base)["id"]
    fields = {f["name"]: f for f in gh("api", f"{base}/fields", "--paginate")}

    from playwright.sync_api import TimeoutError as PlaywrightTimeout
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(CDP_URL)
        # a background tab: a foreground one would raise the browser over the user's windows
        with browser.contexts[0].expect_page() as opened:
            browser.new_browser_cdp_session().send(
                "Target.createTarget", {"url": "about:blank", "background": True}
            )
        page = opened.value
        try:
            page.goto(
                f"https://github.com/{kind}/{owner}/projects/{number}/workflows", wait_until="load"
            )
            island = page.locator("#memex-workflows-data")
            try:
                island.wait_for(state="attached", timeout=30000)
            except PlaywrightTimeout:
                print(
                    f"no workflows page at {page.url} ({page.title()}): sign in, or finish SSO, in that browser",
                    file=sys.stderr,
                )
                return 1
            current = json.loads(island.text_content() or "[]")
            defaults = json.loads(
                page.locator("#memex-workflow-configurations-data").text_content() or "[]"
            )
            for want in spec["workflows"]:
                try:
                    method, payload = request(
                        want, current, defaults, fields, lambda r: gh("api", f"repos/{r}")["id"]
                    )
                except ValueError as exc:
                    print(exc, file=sys.stderr)
                    return 1
                print(method, json.dumps(payload))
                if dry:
                    continue
                status, reply = page.evaluate(
                    FETCH, [f"/memexes/{memex}/workflows", method, payload]
                )
                if not 200 <= status < 300:
                    print(f"refused ({status}): {reply[:500]}", file=sys.stderr)
                    return 1
        finally:
            page.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
