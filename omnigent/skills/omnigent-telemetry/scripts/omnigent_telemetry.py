#!/usr/bin/env python3
"""Omnigent spend, tokens and anomaly flags over the last N days, from the server's API.

    python3 scripts/omnigent_telemetry.py [--days N] [--max-sessions N] [--json] [--html PATH]

- ``GET /v1/usage/telemetry?since=&until=&max_sessions=``: daily cost, models, sessions (labels, turns,
  tool calls, usage by model, sub-agent and fork counts) and scheduled tasks, as the server counted
  them. A section it cut at ``max_sessions`` comes back in ``truncated`` and is shown as a gap, never
  as zeros.
- ``GET /v1/usage?days=N``: spend today, over 7 and 30 days, each top-level tree's cost by model, and
  each session's ``child_usage[]`` (what a verifier's ``codex`` or ``agy`` posted). The server adds
  child usage into neither cost nor models, and the report shows it beside its parent session only.
- Local Codex rollout files: the newest rate-limit snapshot.

Login and token refresh are ``omnigent-agents``' ``omnigent_agent.py``, a sibling skill in this
package. There is no SQL and no database credential. The window is the last N UTC days, today
included. Exit 0 whenever a report is printed. Stdlib only.
"""

from __future__ import annotations

import argparse
import glob
import html
import json
import os
import re
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.dont_write_bytecode = True  # no __pycache__ left in the sibling skill's folder
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "omnigent-agents" / "scripts"))
from omnigent_agent import Fail, Omnigent

# /v1/usage and /v1/usage/telemetry build their window on request: slower than the 30 s of any other call
USAGE_SECONDS = 180.0
MAX_DAYS = 90  # the longest window GET /v1/usage/telemetry serves
MAX_SESSIONS = 500  # sessions the telemetry call returns before it reports the rest as truncated
ROLLOUTS = "~/.omnigent/codex-native/*/codex-home/sessions/*/*/*/rollout-*.jsonl"
ROLLOUT_FILES = 15  # newest rollouts scanned for a populated rate-limit snapshot
TOP_TREES = 15  # trees in the text and HTML tables; --json has all


# Flag thresholds: a flag fires at its threshold and stays quiet below it.
SUBAGENTS = 25  # sub-agents in one root tree
NESTED_CODEX = 6  # Codex's own sub-agents (sub_agent_name 'Codex') in one tree
VERIFIER_PASS = 4  # a pass past the loop's default cap of 3
INHERITED_ITEMS = 500  # items a session created in the window inherited from a fork
SUBSCRIBERS = 2  # sessions one target wakes when it ends a turn
CRON_FAILURES = 3  # failed runs of one scheduled task in the window
SIDEBAR_SESSIONS = 10  # unarchived top-level sessions scheduled runs created
CLOUD_AGENT = "claude-cloud"  # agent name of a session that runs in a cloud VM
GEMINI_AGENT = "antigravity-native"
ROLES = ("lead", "worker", "verifier")  # `omni.role` label values, else a word of the title
PASS = re.compile(r"(?:-p|\bpass\s*)(\d+)\b", re.IGNORECASE)

API_SECTIONS = (
    "daily cost",
    "tokens by model",
    "session trees' sub-agents, nested Codex sub-agents, compactions and forked items",
    "scheduled tasks",
    "anomaly flags",
)


# --- sources ---------------------------------------------------------------------------------


def fetch_telemetry(client: Omnigent, since: int, until: int, max_sessions: int) -> dict:
    """``GET /v1/usage/telemetry`` for the window, as the report's rows. No row is computed here."""
    got = client.call(
        "GET",
        f"/v1/usage/telemetry?since={since}&until={until}&max_sessions={max_sessions}",
        timeout=USAGE_SECONDS,
    )
    if not isinstance(got, dict):
        raise Fail("the telemetry response is not a JSON object")
    sessions = got.get("sessions") or []
    for s in sessions:
        s["usage"] = s.get("usage") or {}
        s["labels"] = s["labels"] if isinstance(s.get("labels"), dict) else {}
        s["tool_calls"] = s["tool_calls"] if isinstance(s.get("tool_calls"), dict) else {}
    models = [
        {**m, "cache_read_tokens": m.get("cache_read_input_tokens") or 0}
        for m in got.get("models") or []
    ]
    return {
        "sessions": sessions,
        "daily": got.get("daily_cost") or [],
        "models": models,
        "tasks": got.get("scheduled_tasks") or [],
        "subscriptions": sum(len(s.get("subscribes_to") or []) for s in sessions),
        "sidebar": got.get("sidebar"),
        "truncated": got.get("truncated") or [],
    }


def child_usage_of(usage: dict | None) -> dict[str, list[dict]]:
    """Each session's posted child usage from ``/v1/usage`` ``sessions[].child_usage[]``."""
    return {
        s["id"]: s["child_usage"]
        for s in (usage or {}).get("sessions") or []
        if isinstance(s.get("child_usage"), list) and s["child_usage"]
    }


def codex_rate_limits(pattern: str = ROLLOUTS) -> dict | None:
    """The newest populated ``payload.rate_limits`` in this host's Codex rollouts."""
    files = sorted(glob.glob(os.path.expanduser(pattern)), key=os.path.getmtime, reverse=True)
    for path in files[:ROLLOUT_FILES]:
        try:
            lines = Path(path).read_bytes().splitlines()
        except OSError:
            continue
        for line in reversed(lines):
            if b'"rate_limits"' not in line:
                continue
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            limits = (obj.get("payload") or {}).get("rate_limits") or {}
            windows = [limits[k] for k in ("primary", "secondary") if limits.get(k)]
            if windows:
                return {"timestamp": obj.get("timestamp"), "file": path, "windows": windows}
    return None


# --- analysis: pure functions over plain rows ------------------------------------------------


def day(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat()


def window_start(days: int, now: float) -> int:
    """UTC midnight of the first of the last ``days`` days, today included."""
    today = datetime.fromtimestamp(now, tz=timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return int((today - timedelta(days=days - 1)).timestamp())


def cost(usage: dict) -> float:
    return float(usage.get("cost_usd") or 0.0)


def role_of(s: dict) -> str:
    """lead, worker or verifier from the `omni.role` label, else a word of the title; else ''."""
    named = (s.get("labels") or {}).get("omni.role")
    if named in ROLES:
        return named
    words = re.findall(r"[a-z]+", (s.get("title") or "").lower())
    return next((r for r in ROLES if r in words), "")


def has_tokens(usage: dict) -> bool:
    return usage.get("input_tokens") is not None or usage.get("output_tokens") is not None


def tokens_of(usage: dict) -> int:
    return int((usage.get("input_tokens") or 0) + (usage.get("output_tokens") or 0))


def side_metrics(members: list[dict], tool: str | None) -> dict:
    """One side's numbers. `tool_calls` is {name: count} per session; `tool` the split's tool, if any."""
    calls = sum(sum((s.get("tool_calls") or {}).values()) for s in members)
    own = sum((s.get("tool_calls") or {}).get(tool, 0) for s in members) if tool else 0
    priced = [s for s in members if has_tokens(s["usage"])]
    return {
        "sessions": len(members),
        "cost_usd": sum(cost(s["usage"]) for s in members),
        "tokens": sum(tokens_of(s["usage"]) for s in priced) if priced else None,
        "turns": sum(s.get("turns") or 0 for s in members),
        "wall_seconds": sum(
            max(0, (s["updated_at"] or 0) - (s["created_at"] or 0)) for s in members
        ),
        "tool_calls": calls,
        "split_tool_calls": own,
        "split_tool_share": (own / calls) if tool and calls else None,
    }


def split_of(sessions: list[dict], tool: str | None, label: str | None) -> dict | None:
    """Sessions in two sides, by a named tool called at least once or by a launch label key.

    Both sides get the same metrics, overall and by role. The names come from the caller's
    arguments only; nothing here knows which tool or label a setup compares.
    """
    if not (tool or label):
        return None
    if tool:
        kind, key = "tool", tool
        sides = {
            f"called {tool}": [s for s in sessions if (s.get("tool_calls") or {}).get(tool)],
            f"never called {tool}": [
                s for s in sessions if not (s.get("tool_calls") or {}).get(tool)
            ],
        }
    else:
        kind, key = "label", str(label)
        sides = {
            f"has label {label}": [s for s in sessions if (s.get("labels") or {}).get(label)],
            f"no label {label}": [s for s in sessions if not (s.get("labels") or {}).get(label)],
        }
        values = sorted(
            {str(s["labels"][label]) for s in sessions if (s.get("labels") or {}).get(label)}
        )
        sides = (
            {
                **sides,
                **{
                    f"{label}={v}": [
                        s for s in sessions if str((s.get("labels") or {}).get(label)) == v
                    ]
                    for v in values
                },
            }
            if len(values) > 1
            else sides
        )
    out = {}
    for name, members in sides.items():
        out[name] = {
            **side_metrics(members, tool),
            "roles": {
                r: side_metrics([s for s in members if role_of(s) == r], tool)
                for r in ROLES
                if any(role_of(s) == r for s in members)
            },
        }
    return {"kind": kind, "key": key, "sides": out}


def cloud_of(sessions: list[dict], kids: dict[str, list[dict]]) -> dict:
    """Cloud sessions as their own group: cost, models and the usage their child CLIs posted.

    `kids` is `/v1/usage`'s child usage by parent id. It is shown beside the parent and never added to
    its cost, as the server adds it to nothing.
    """
    group = [s for s in sessions if s.get("agent") == CLOUD_AGENT]
    rows = []
    for s in group:
        by = s["usage"].get("by_model") or {}
        children = kids.get(s["id"], [])
        rows.append(
            {
                "id": s["id"],
                "title": s["title"] or "",
                "cost_usd": cost(s["usage"]),
                "models": sorted(by),
                "status": s.get("live_status") or "",
                "children": [
                    {
                        "harness": c.get("harness") or "?",
                        "model": c.get("model") or "?",
                        "cost_usd": c.get("cost_usd"),
                        "tokens": c.get("total_tokens"),
                    }
                    for c in children
                ],
                "child_cost_usd": sum(float(c.get("cost_usd") or 0) for c in children),
            }
        )
    return {
        "sessions": len(rows),
        "cost_usd": sum(r["cost_usd"] for r in rows),
        "child_cost_usd": sum(r["child_cost_usd"] for r in rows),
        "rows": sorted(rows, key=lambda r: -r["cost_usd"]),
    }


def priced_note(s: dict) -> str | None:
    """ "no price" for a Gemini session that has tokens and no cost, so $0 is never shown for it."""
    u = s["usage"]
    if s.get("agent") == GEMINI_AGENT and tokens_of(u) and not cost(u):
        return f"{tokens_of(u):,} tokens, no price"
    return None


def verifier_pass(title: str) -> int:
    return max((int(n) for n in PASS.findall(title or "")), default=0)


def models_of(sessions: list[dict]) -> list[dict]:
    rows: dict[str, dict] = defaultdict(
        lambda: dict.fromkeys(
            ("sessions", "cost_usd", "input_tokens", "cache_read_tokens", "output_tokens"), 0
        )
    )
    for s in sessions:
        for name, u in (s["usage"].get("by_model") or {}).items():
            row = rows[name]
            row["sessions"] += 1
            row["cost_usd"] += cost(u)
            row["input_tokens"] += u.get("input_tokens") or 0
            row["cache_read_tokens"] += u.get("cache_read_input_tokens") or 0
            row["output_tokens"] += u.get("output_tokens") or 0
    return sorted(
        ({"model": m, **r} for m, r in rows.items()),
        key=lambda r: (-r["cost_usd"], -r["cache_read_tokens"]),
    )


def trees_of(api_sessions: list[dict], sessions: list[dict] | None, since: int) -> list[dict]:
    """One row per root tree: cost from the API (summed over its subtree), counts from the telemetry call."""
    by_root: dict[str, list[dict]] = defaultdict(list)
    for s in sessions or []:
        by_root[s["root_id"] or s["id"]].append(s)
    api = {s["id"]: s for s in api_sessions if (s.get("updated_at") or 0) >= since}
    rows = []
    for rid in set(api) | set(by_root):
        members = by_root.get(rid, [])
        root = next((s for s in members if s["id"] == rid), {})
        a = api.get(rid, {})
        children = [s for s in members if s["id"] != rid]
        row = {
            "id": rid,
            "title": a.get("title") or root.get("title") or "",
            "updated_at": max(
                [a.get("updated_at") or 0] + [s.get("updated_at") or 0 for s in members]
            ),
            "cost_usd": a["cost_usd"] if a else sum(cost(s["usage"]) for s in members),
            "models": a.get("models") or {},
        }
        if sessions is not None:
            row.update(
                host=root.get("host") or "",
                agent=root.get("agent") or "",
                workspace=root.get("workspace") or "",
                status=root.get("live_status") or "",
                root_cost_usd=cost(root.get("usage") or {}),
                subagents=len(children),
                nested_codex=sum(1 for s in children if s.get("sub_agent_name") == "Codex"),
                items=sum(s.get("items") or 0 for s in members),
                inherited=root.get("inherited_items") or 0,
                compactions=sum(s.get("compactions") or 0 for s in members),
                tokens=sum(tokens_of(s["usage"]) for s in members),
                late_verifiers=sorted(
                    s["title"] for s in children if verifier_pass(s["title"]) >= VERIFIER_PASS
                ),
            )
        rows.append(row)
    return sorted(rows, key=lambda r: -r["cost_usd"])


def flags_of(db: dict, trees: list[dict], since: int) -> list[str]:
    flags = []
    for t in trees:
        name = f"{t['id'][:8]} '{t['title'][:40]}'"
        if t["subagents"] >= SUBAGENTS or t["nested_codex"] >= NESTED_CODEX:
            flags.append(
                f"SUBAGENT_EXPLOSION {name}: {t['subagents']} sub-agents, {t['nested_codex']}"
                f" nested Codex, ${t['cost_usd']:.2f}"
            )
        if t["late_verifiers"]:
            flags.append(
                f"VERIFIER_CHURN {name}: {len(t['late_verifiers'])} verifier sessions at pass"
                f" >= {VERIFIER_PASS} ({', '.join(t['late_verifiers'][:3])})"
            )
    for s in db["sessions"]:
        if (s.get("created_at") or 0) >= since and (
            s.get("inherited_items") or 0
        ) >= INHERITED_ITEMS:
            flags.append(
                f"FORK_BLOAT {s['id'][:8]} '{(s['title'] or '')[:40]}': started with"
                f" {s['inherited_items']} inherited items, {(s.get('items') or 0) - s['inherited_items']} its own"
            )
    titles = {s["id"]: s.get("title") or "" for s in db["sessions"]}
    by_target: dict[str, list[dict]] = defaultdict(list)
    for s in db[
        "sessions"
    ]:  # `subscribes_to`: the sessions this one wakes on, when they end a turn
        for target in s.get("subscribes_to") or []:
            by_target[target].append(s)
    for target, edges in by_target.items():
        if len(edges) >= SUBSCRIBERS:
            subs = ", ".join(f"{e['id'][:8]} '{(e.get('title') or '')[:24]}'" for e in edges)
            flags.append(
                f"SUBSCRIPTION_AMPLIFICATION {target[:8]} '{titles.get(target, '')[:40]}'"
                f" wakes {len(edges)} subscribers: {subs}"
            )
    for t in db["tasks"]:
        if t.get("failed", 0) >= CRON_FAILURES:
            flags.append(
                f"CRON_FAIL_LOOP {t['id'][:8]} '{t['name']}': {t['failed']}/{t.get('runs', 0)} runs failed"
                f" (last error {t.get('last_error') or 'none recorded'})"
            )
    side = db["sidebar"] or {"from_scheduled_tasks": 0, "unarchived": 0}
    if side["from_scheduled_tasks"] >= SIDEBAR_SESSIONS:
        flags.append(
            f"SIDEBAR_NOISE {side['from_scheduled_tasks']} of {side['unarchived']} unarchived top-level"
            " sessions were created by scheduled-task runs"
        )
    return flags


def build(
    usage: dict | None,
    db: dict | None,
    rate_limits: dict | None,
    days: int,
    now: float,
    left_out: dict[str, str] | None = None,
    split_tool: str | None = None,
    split_label: str | None = None,
) -> dict:
    """The report from whatever sources answered; ``left_out`` maps each missing section to why."""
    since = window_start(days, now)
    left_out = dict(left_out or {})
    api_sessions = (usage or {}).get("sessions") or []
    trees = trees_of(api_sessions, db["sessions"] if db else None, since)
    if db:
        models = db.get("models") or models_of(db["sessions"])
    else:  # cost only: the API carries no tokens
        totals: dict[str, float] = defaultdict(float)
        for t in trees:
            for m, c in t["models"].items():
                totals[m] += c
        models = [
            {"model": m, "cost_usd": c} for m, c in sorted(totals.items(), key=lambda x: -x[1])
        ]
    if rate_limits is None:
        left_out.setdefault("Codex rate limits", "no Codex rollout with a rate-limit snapshot here")
    return {
        "window": {"days": days, "from": day(since), "to": day(now), "generated": now},
        "spend": None
        if usage is None
        else {k: usage.get(k) for k in ("cost_today", "cost_last_7d", "cost_last_30d")},
        "daily": db["daily"] if db else None,
        "rate_limits": rate_limits,
        "models": models,
        "trees": trees,
        "tasks": sorted(db["tasks"], key=lambda t: (-t.get("failed", 0), -t.get("runs", 0)))
        if db
        else None,
        "subscriptions": db["subscriptions"] if db else None,
        "sidebar": db.get("sidebar") if db else None,
        "flags": flags_of(db, trees, since) if db else None,
        "split": split_of(db["sessions"], split_tool, split_label) if db else None,
        "cloud": cloud_of(db["sessions"], child_usage_of(usage)) if db else None,
        "truncated": [str(t) for t in (db or {}).get("truncated") or []],
        "unpriced": [
            {"id": s["id"], "title": s["title"], "note": n}
            for s in (db["sessions"] if db else [])
            if (n := priced_note(s))
        ],
        "left_out": left_out,
    }


# --- rendering -------------------------------------------------------------------------------


def usd(x: float | None) -> str:
    return "-" if x is None else f"${x:,.2f}"


def mtok(n: float) -> str:
    return f"{n / 1e6:,.1f}M"


def window_name(w: dict) -> str:
    return {300: "5h", 10080: "weekly"}.get(w.get("window_minutes"), f"{w.get('window_minutes')}m")


def resets(w: dict) -> str:
    at = w.get("resets_at")
    return datetime.fromtimestamp(at, tz=timezone.utc).strftime("%m-%d %H:%M UTC") if at else "?"


def model_cells(m: dict) -> list[str]:
    if "sessions" not in m:
        return [m["model"], "", usd(m["cost_usd"]), "", "", ""]
    return [
        m["model"],
        str(m["sessions"]),
        usd(m["cost_usd"]),
        mtok(m["input_tokens"]),
        mtok(m["cache_read_tokens"]),
        mtok(m["output_tokens"]),
    ]


MODEL_HEAD = ["model", "sessions", "cost", "uncached in", "cache read", "output"]
TREE_HEAD = ["root", "updated", "host", "harness", "sub-agents (nested Codex)", "items (forked)"]
TREE_HEAD += ["compactions", "cost (root)", "title"]
TASK_HEAD = ["task", "name", "runs", "succeeded", "failed", "skipped", "last error", "workspace"]


def tree_cells(t: dict) -> list[str]:
    updated = datetime.fromtimestamp(t["updated_at"], tz=timezone.utc).strftime("%m-%d %H:%M")
    if "subagents" not in t:
        return [t["id"][:8], updated, "", "", "", "", "", usd(t["cost_usd"]), t["title"]]
    return [
        t["id"][:8],
        updated,
        t["host"],
        t["agent"],
        f"{t['subagents']} ({t['nested_codex']})",
        f"{t['items']} ({t['inherited']})",
        str(t["compactions"]),
        f"{usd(t['cost_usd'])} ({usd(t['root_cost_usd'])})",
        t["title"],
    ]


def task_cells(t: dict) -> list[str]:
    cells = [
        t["id"][:8],
        t["name"],
        *(t.get(k, 0) for k in ("runs", "succeeded", "failed", "skipped")),
    ]
    return [str(c) for c in cells] + [t.get("last_error") or "", t.get("workspace") or ""]


def split_rows(r: dict) -> list[list[str]]:
    rows = []
    for name, side in r["split"]["sides"].items():
        for role, m in [("all", side), *side["roles"].items()]:
            share = "-" if m["split_tool_share"] is None else f"{100 * m['split_tool_share']:.0f}%"
            tok = "no tokens recorded" if m["tokens"] is None else mtok(m["tokens"])
            rows.append(
                [
                    name,
                    role,
                    str(m["sessions"]),
                    usd(m["cost_usd"]),
                    tok,
                    str(m["turns"]),
                    f"{m['wall_seconds'] / 3600:.1f}h",
                    str(m["tool_calls"]),
                    share,
                ]
            )
    return rows


SPLIT_HEAD = [
    "side",
    "role",
    "sessions",
    "cost",
    "tokens",
    "turns",
    "wall",
    "tool calls",
    "split tool share",
]
SPLIT_NOTE = (
    "One call of a tool that runs code can do the work of several direct calls,"
    " so raw call counts are not comparable across sides."
)
CLOUD_HEAD = ["session", "cost", "models", "status", "child CLIs (harness model cost)", "title"]


def cloud_rows(r: dict) -> list[list[str]]:
    return [
        [
            c["id"][:8],
            usd(c["cost_usd"]),
            ", ".join(c["models"]),
            c["status"],
            "; ".join(f"{k['harness']} {k['model']} {usd(k['cost_usd'])}" for k in c["children"]),
            c["title"],
        ]
        for c in r["cloud"]["rows"]
    ]


def daily_total(r: dict) -> float:
    return sum(d["cost_usd"] for d in r["daily"])


def text(r: dict) -> str:
    w = r["window"]
    out = [f"Omnigent telemetry, last {w['days']} days ({w['from']} to {w['to']} UTC)", ""]
    if r["spend"]:
        s = r["spend"]
        out.append(
            f"Spend (API): today {usd(s['cost_today'])}, 7 days {usd(s['cost_last_7d'])},"
            f" 30 days {usd(s['cost_last_30d'])}"
        )
    if r["daily"] is not None:
        out.append(f"Daily cost (telemetry), window total {usd(daily_total(r))}:")
        out += [f"  {d['day']}  {usd(d['cost_usd']):>10}" for d in r["daily"]]
    if r["rate_limits"]:
        rl = r["rate_limits"]
        windows = ", ".join(
            f"{window_name(x)} {x.get('used_percent')}% used, resets {resets(x)}"
            for x in rl["windows"]
        )
        out.append(f"Codex rate limits ({rl['timestamp']}): {windows}")

    def table(title: str, head: list[str], rows: list[list[str]]) -> None:
        out.extend(["", title, "  " + " | ".join(head)])
        out.extend("  " + " | ".join(row) for row in rows)

    table("Models", MODEL_HEAD, [model_cells(m) for m in r["models"]])
    table(
        f"Session trees, top {TOP_TREES} of {len(r['trees'])} by cost",
        TREE_HEAD,
        [tree_cells(t) for t in r["trees"][:TOP_TREES]],
    )
    if r.get("split"):
        sp = r["split"]
        table(f"Split by {sp['kind']} {sp['key']}", SPLIT_HEAD, split_rows(r))
        out.append(f"  Note: {SPLIT_NOTE}")
    if r.get("cloud") and r["cloud"]["sessions"]:
        c = r["cloud"]
        table(
            f"Cloud sessions: {c['sessions']}, {usd(c['cost_usd'])} (child CLIs {usd(c['child_cost_usd'])})",
            CLOUD_HEAD,
            cloud_rows(r),
        )
    if r.get("unpriced"):
        out += ["", "Tokens with no price (not $0):"]
        out += [f"  {u['id'][:8]} {u['title'][:40]}: {u['note']}" for u in r["unpriced"]]
    if r["tasks"] is not None:
        table("Scheduled tasks", TASK_HEAD, [task_cells(t) for t in r["tasks"] if t.get("runs")])
        if r["subscriptions"] is not None and r["sidebar"]:
            out.append(
                f"\nLive subscriptions: {r['subscriptions']}. Unarchived top-level sessions:"
                f" {r['sidebar']['unarchived']}, {r['sidebar']['from_scheduled_tasks']} from scheduled runs."
            )
    if r["flags"] is not None:
        out.append(f"\nFlags ({len(r['flags'])}):")
        out += [f"  {f}" for f in r["flags"]] or ["  none"]
    if r.get("truncated"):
        out.append("\nTruncated by the server (a gap in the numbers above, not zeros):")
        out += [f"  {t}" for t in r["truncated"]]
    if r["left_out"]:
        out.append("\nLeft out:")
        out += [f"  {k}: {why}" for k, why in r["left_out"].items()]
    return "\n".join(out) + "\n"


CSS = """
:root{--bg:#fbfbfa;--fg:#1d1d1b;--muted:#6b6b66;--line:#e2e1dc;--bar:#3a6ea5;--flag:#a5481d}
@media (prefers-color-scheme:dark){:root{--bg:#161615;--fg:#ecebe6;--muted:#9a9993;
--line:#2f2f2c;--bar:#6c9fd6;--flag:#e08a5a}}
body{background:var(--bg);color:var(--fg);font:14px/1.45 system-ui,sans-serif;margin:0;
padding:24px 16px;max-width:1200px;margin-inline:auto}
h1{font-size:20px;margin:0 0 4px}h2{font-size:15px;margin:28px 0 8px}
.muted{color:var(--muted)}.cards{display:flex;flex-wrap:wrap;gap:12px;margin-top:16px}
.card{border:1px solid var(--line);border-radius:8px;padding:10px 14px;min-width:130px}
.card b{display:block;font-size:20px;font-variant-numeric:tabular-nums}
.scroll{overflow-x:auto}table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}
th,td{text-align:left;padding:4px 8px;border-bottom:1px solid var(--line);white-space:nowrap}
th{color:var(--muted);font-weight:600}td:last-child{white-space:normal}
.bars{display:grid;grid-template-columns:auto 1fr auto;gap:4px 10px;align-items:center}
.bar{height:14px;background:var(--bar);border-radius:3px;min-width:1px}
ul.flags li{color:var(--flag);margin:4px 0}
"""


def page(r: dict) -> str:
    """One self-contained page: inline CSS, no script, nothing fetched."""
    e = html.escape
    w = r["window"]
    cards = []
    if r["spend"]:
        s = r["spend"]
        cards += [("Today", s["cost_today"]), ("7 days", s["cost_last_7d"])]
        cards.append(("30 days", s["cost_last_30d"]))
    if r["daily"] is not None:
        cards.append((f"{w['days']}-day window", daily_total(r)))
    body = [
        f"<h1>Omnigent telemetry, last {w['days']} days</h1>",
        f"<div class=muted>{e(w['from'])} to {e(w['to'])} UTC</div>",
        "<div class=cards>"
        + "".join(
            f"<div class=card><span class=muted>{e(k)}</span><b>{usd(v)}</b></div>"
            for k, v in cards
        )
        + "</div>",
    ]
    if r["rate_limits"]:
        rl = r["rate_limits"]
        windows = ", ".join(
            f"{window_name(x)} {x.get('used_percent')}% used, resets {resets(x)}"
            for x in rl["windows"]
        )
        body.append(f"<p>Codex rate limits ({e(str(rl['timestamp']))}): {e(windows)}</p>")
    if r["daily"]:
        top = max(d["cost_usd"] for d in r["daily"]) or 1
        body.append("<h2>Daily spend</h2><div class=bars>")
        for d in r["daily"]:
            body.append(
                f"<span>{e(d['day'])}</span><div class=bar style='width:{100 * d['cost_usd'] / top:.1f}%'>"
                f"</div><span>{usd(d['cost_usd'])}</span>"
            )
        body.append("</div>")

    def table(title: str, head: list[str], rows: list[list[str]]) -> None:
        body.append(f"<h2>{e(title)}</h2><div class=scroll><table><tr>")
        body.append("".join(f"<th>{e(h)}</th>" for h in head) + "</tr>")
        body.extend("<tr>" + "".join(f"<td>{e(c)}</td>" for c in row) + "</tr>" for row in rows)
        body.append("</table></div>")

    if r["flags"] is not None:
        body.append(f"<h2>Flags ({len(r['flags'])})</h2><ul class=flags>")
        body += [f"<li>{e(f)}</li>" for f in r["flags"]] or ["<li>none</li>"]
        body.append("</ul>")
    table("Models", MODEL_HEAD, [model_cells(m) for m in r["models"]])
    table(
        f"Session trees, top {TOP_TREES} of {len(r['trees'])} by cost",
        TREE_HEAD,
        [tree_cells(t) for t in r["trees"][:TOP_TREES]],
    )
    if r.get("split"):
        table(f"Split by {r['split']['kind']} {r['split']['key']}", SPLIT_HEAD, split_rows(r))
        body.append(f"<p class=muted>{e(SPLIT_NOTE)}</p>")
    if r.get("cloud") and r["cloud"]["sessions"]:
        table(
            f"Cloud sessions: {r['cloud']['sessions']}, {usd(r['cloud']['cost_usd'])}"
            f" (child CLIs {usd(r['cloud']['child_cost_usd'])})",
            CLOUD_HEAD,
            cloud_rows(r),
        )
    if r.get("unpriced"):
        body.append("<h2>Tokens with no price</h2><ul>")
        body += [
            f"<li>{e(u['id'][:8])} {e(u['title'][:40])}: {e(u['note'])}</li>" for u in r["unpriced"]
        ]
        body.append("</ul>")
    if r["tasks"] is not None:
        table("Scheduled tasks", TASK_HEAD, [task_cells(t) for t in r["tasks"] if t["runs"]])
    if r.get("truncated"):
        body.append("<h2>Truncated by the server (a gap, not zeros)</h2><ul>")
        body += [f"<li>{e(t)}</li>" for t in r["truncated"]]
        body.append("</ul>")
    if r["left_out"]:
        body.append("<h2>Left out</h2><ul>")
        body += [f"<li>{e(k)}: {e(why)}</li>" for k, why in r["left_out"].items()]
        body.append("</ul>")
    return (
        "<!doctype html><html lang=en><head><meta charset=utf-8>"
        "<meta name=viewport content='width=device-width,initial-scale=1'>"
        f"<title>Omnigent telemetry</title><style>{CSS}</style></head><body>"
        + "\n".join(body)
        + "</body></html>\n"
    )


# --- entry -----------------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--days", type=int, default=7, help="last N UTC days, today included (7)")
    p.add_argument(
        "--server",
        default="",
        help="Omnigent server URL; default: this session's, else the one login",
    )
    p.add_argument("--json", action="store_true", help="print the report as JSON")
    p.add_argument("--html", metavar="PATH", help="also write a self-contained HTML page")
    p.add_argument(
        "--max-sessions",
        type=int,
        default=MAX_SESSIONS,
        help=f"sessions the server returns before it truncates ({MAX_SESSIONS})",
    )
    p.add_argument(
        "--split-tool", help="compare sessions that called this tool with those that did not"
    )
    p.add_argument("--split-label", help="compare sessions by this launch label key")
    p.add_argument(
        "--values",
        metavar="FILE",
        help="JSON file with split_tool / split_label, as the setup passes them",
    )
    args = p.parse_args(argv)
    if args.values:
        vals = json.loads(Path(args.values).read_text())
        args.split_tool = args.split_tool or vals.get("split_tool")
        args.split_label = args.split_label or vals.get("split_label")
    if args.split_tool and args.split_label:
        p.error("--split-tool and --split-label are one split each: pick one")
    if not 1 <= args.days <= MAX_DAYS:
        p.error(f"--days must be 1 to {MAX_DAYS}: the server serves at most {MAX_DAYS} days")
    now = time.time()
    left_out: dict[str, str] = {}
    usage = db = None
    client = Omnigent(args.server)
    try:  # first: its daily cost and /v1/usage's are read under a second apart
        db = fetch_telemetry(client, window_start(args.days, now), int(now), args.max_sessions)
    except (Fail, OSError, ValueError) as e:
        why = f"GET /v1/usage/telemetry failed: {str(e)[:200]}"
        left_out.update(dict.fromkeys(API_SECTIONS, why))
    try:
        usage = client.call("GET", f"/v1/usage?days={args.days}", timeout=USAGE_SECONDS)
    except (Fail, OSError, ValueError) as e:
        left_out["spend and session-tree cost (API)"] = str(e)
    r = build(
        usage, db, codex_rate_limits(), args.days, now, left_out, args.split_tool, args.split_label
    )
    if args.html:
        Path(args.html).write_text(page(r))
    print(json.dumps(r, indent=2) if args.json else text(r), end="" if not args.json else "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
