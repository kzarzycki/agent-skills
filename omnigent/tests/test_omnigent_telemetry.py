"""scripts/omnigent_telemetry.py's analysis on synthetic rows, no Omnigent and no database."""

import importlib.util
import json
import sys
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "omnigent_telemetry",
    Path(__file__).resolve().parents[1]
    / "skills"
    / "omnigent-telemetry"
    / "scripts"
    / "omnigent_telemetry.py",
)
assert spec and spec.loader
telemetry = importlib.util.module_from_spec(spec)
sys.modules["omnigent_telemetry"] = telemetry
spec.loader.exec_module(telemetry)

NOW = 1_800_000_000.0
SINCE = telemetry.window_start(7, NOW)


def session(sid: str, root: str, title: str = "", **kw: object) -> dict:
    row = {
        "id": sid,
        "parent_id": None if sid == root else root,
        "root_id": root,
        "title": title or f"session {sid}",
        "created_at": SINCE + 60,
        "updated_at": SINCE + 120,
        "archived": False,
        "items": 10,
        "agent": "codex-native-ui",
        "host": "host-a",
        "workspace": "/work",
        "live_status": 1,
        "sub_agent_name": None,
        "usage": {"total_cost_usd": 1.0},
        "compactions": 0,
        "inherited": 0,
    }
    return {**row, **kw}


def tree(root: str, children: int, codex: int = 0, titles: tuple[str, ...] = ()) -> list[dict]:
    rows = [session(root, root)]
    rows += [
        session(f"{root}-c{i}", root, sub_agent_name="Codex" if i < codex else None)
        for i in range(children)
    ]
    rows += [session(f"{root}-v{i}", root, title=t) for i, t in enumerate(titles)]
    return rows


def db(**kw: object) -> dict:
    return {
        "daily": [],
        "sessions": [],
        "subscriptions": [],
        "tasks": [],
        "sidebar": {"unarchived": 0, "from_tasks": 0},
        **kw,
    }


def flags(rows: dict) -> list[str]:
    return telemetry.build(None, rows, None, 7, NOW)["flags"]


def kinds(rows: dict) -> list[str]:
    return [f.split()[0] for f in flags(rows)]


def edge(subscriber: str, target: str) -> dict:
    return {
        "subscriber_id": subscriber,
        "subscriber_title": f"lead {subscriber}",
        "target_id": target,
        "target_title": f"worker {target}",
    }


def task(failed: int) -> dict:
    return {
        "id": "task0001",
        "name": "nightly",
        "state": 1,
        "workspace": None,
        "runs": 10,
        "ok": 10 - failed,
        "failed": failed,
        "skipped": 0,
        "last_error": "host_offline" if failed else None,
    }


def test_a_tree_explodes_at_its_sub_agent_or_nested_codex_threshold() -> None:
    assert kinds(db(sessions=tree("r1", telemetry.SUBAGENTS))) == ["SUBAGENT_EXPLOSION"]
    assert kinds(db(sessions=tree("r1", telemetry.SUBAGENTS - 1))) == []
    nested = telemetry.NESTED_CODEX
    assert kinds(db(sessions=tree("r1", nested, codex=nested))) == ["SUBAGENT_EXPLOSION"]
    assert kinds(db(sessions=tree("r1", nested, codex=nested - 1))) == []


def test_verifier_churn_fires_on_a_pass_past_the_cap_in_either_title_form() -> None:
    for title in ("s12-verifier-p4", "verify #12 pass 5"):
        assert kinds(db(sessions=tree("r1", 0, titles=(title,)))) == ["VERIFIER_CHURN"]
    quiet = ("s12-verifier-p3", "verify #12 pass 3", "omp-plan")
    assert kinds(db(sessions=tree("r1", 0, titles=quiet))) == []


def test_fork_bloat_counts_inherited_items_of_a_session_started_in_the_window() -> None:
    at = telemetry.INHERITED_ITEMS
    assert kinds(db(sessions=[session("f1", "f1", inherited=at, items=at + 5)])) == ["FORK_BLOAT"]
    assert kinds(db(sessions=[session("f1", "f1", inherited=at - 1, items=at)])) == []
    old = session("f1", "f1", inherited=at, items=at, created_at=SINCE - 1)
    assert kinds(db(sessions=[old])) == []


def test_subscription_amplification_fires_when_one_target_wakes_several_subscribers() -> None:
    many = [edge(f"s{i}", "t1") for i in range(telemetry.SUBSCRIBERS)]
    assert kinds(db(subscriptions=many)) == ["SUBSCRIPTION_AMPLIFICATION"]
    one_each = [edge(f"s{i}", f"t{i}") for i in range(telemetry.SUBSCRIBERS)]
    assert kinds(db(subscriptions=one_each)) == []


def test_cron_fail_loop_fires_at_its_failed_run_count() -> None:
    assert kinds(db(tasks=[task(telemetry.CRON_FAILURES)])) == ["CRON_FAIL_LOOP"]
    assert kinds(db(tasks=[task(telemetry.CRON_FAILURES - 1)])) == []


def test_sidebar_noise_counts_unarchived_sessions_scheduled_runs_created() -> None:
    at = telemetry.SIDEBAR_SESSIONS
    assert kinds(db(sidebar={"unarchived": 50, "from_tasks": at})) == ["SIDEBAR_NOISE"]
    assert kinds(db(sidebar={"unarchived": 50, "from_tasks": at - 1})) == []


def test_without_the_database_the_api_sections_render_and_the_rest_are_named() -> None:
    usage = {
        "cost_today": 1.5,
        "cost_last_7d": 12.25,
        "cost_last_30d": 40.0,
        "sessions": [
            {
                "id": "r1",
                "title": "lead",
                "updated_at": SINCE + 1,
                "cost_usd": 3.0,
                "models": {"model-a": 3.0},
            },
            {
                "id": "r0",
                "title": "older",
                "updated_at": SINCE - 1,
                "cost_usd": 9.0,
                "models": {"model-a": 9.0},
            },
        ],
    }
    left = dict.fromkeys(telemetry.API_SECTIONS, "unreachable")
    r = telemetry.build(usage, None, None, 7, NOW, left)
    assert [t["id"] for t in r["trees"]] == ["r1"]
    assert r["models"] == [{"model": "model-a", "cost_usd": 3.0}]
    out = telemetry.text(r)
    assert "7 days $12.25" in out and "r1" in out
    assert all(f"{s}: unreachable" in out for s in telemetry.API_SECTIONS)
    assert "$12.25" in telemetry.page(r) and "<script" not in telemetry.page(r)


class Served:
    """A fake server: each path (without its query) answers with its canned document."""

    def __init__(self, docs: dict[str, object], calls: list | None = None) -> None:
        self.docs, self.calls = docs, calls if calls is not None else []

    def __call__(self, named: str = "") -> Served:
        self.calls.append(("server", named))
        return self

    def call(self, method: str, path: str, **kw: object) -> object:
        self.calls.append((method, path, kw.get("timeout")))
        doc = self.docs[path.split("?")[0]]
        if isinstance(doc, Exception):
            raise doc
        return doc


# The telemetry response as the report reads it: every section the report shows.
TELEMETRY = {
    "daily": [{"day": "2027-01-14", "cost_usd": 4.5}, {"day": "2027-01-15", "cost_usd": 6.0}],
    "models": [
        {
            "model": "model-a",
            "sessions": 2,
            "cost_usd": 9.0,
            "input_tokens": 2_000_000,
            "cache_read_tokens": 30_000_000,
            "output_tokens": 500_000,
        }
    ],
    "sessions": [
        {
            "id": "root0001",
            "root_id": "root0001",
            "title": "lead",
            "created_at": SINCE + 60,
            "updated_at": SINCE + 120,
            "agent": "claude-cloud",
            "host": "host-a",
            "live_status": 1,
            "labels": {"omni.role": "lead"},
            "turns": 7,
            "tool_calls": {"tool-x": 3},
            "usage": {"total_cost_usd": 9.0, "by_model": {"model-a": {"total_cost_usd": 9.0}}},
        },
        {
            "id": "kid00001",
            "root_id": "root0001",
            "parent_id": "root0001",
            "title": "verifier",
            "created_at": SINCE + 70,
            "updated_at": SINCE + 110,
            "usage": {"total_cost_usd": 1.0},
        },
    ],
    "scheduled_tasks": [
        {"id": "task0001", "name": "nightly", "runs": 4, "ok": 1, "failed": 3, "skipped": 0}
    ],
    "truncated": ["sessions: 120 more past max_sessions 500"],
}
USAGE = {
    "cost_today": 6.0,
    "cost_last_7d": 10.5,
    "cost_last_30d": 40.0,
    "sessions": [
        {
            "id": "root0001",
            "title": "lead",
            "updated_at": SINCE + 120,
            "cost_usd": 10.0,
            "models": {"model-a": 10.0},
            "child_usage": [
                {"harness": "codex", "model": "gpt-x", "total_tokens": 500, "cost_usd": 0.5}
            ],
        }
    ],
}


def served_report(monkeypatch, capsys, argv: list[str], docs: dict) -> tuple[list, dict]:
    calls: list = []
    monkeypatch.setattr(telemetry, "Omnigent", Served(docs, calls))
    monkeypatch.setattr(telemetry, "codex_rate_limits", lambda: None)
    assert telemetry.main([*argv, "--json"]) == 0
    return calls, json.loads(capsys.readouterr().out)


def test_a_telemetry_response_renders_every_section_with_no_database(monkeypatch, capsys) -> None:
    docs = {"/v1/usage/telemetry": TELEMETRY, "/v1/usage": USAGE}
    calls, r = served_report(monkeypatch, capsys, ["--days", "3", "--max-sessions", "50"], docs)
    since = telemetry.window_start(3, calls and r["window"]["generated"])
    path = next(c[1] for c in calls if c[0] == "GET" and "telemetry" in c[1])
    assert path.startswith(f"/v1/usage/telemetry?since={since}&until=")
    assert path.endswith("&max_sessions=50")
    assert [c[1] for c in calls if c[0] == "GET"][1] == "/v1/usage?days=3"
    assert r["left_out"] == {
        "Codex rate limits": "no Codex rollout with a rate-limit snapshot here"
    }
    out = telemetry.text(r)
    for part in (
        "Daily cost",
        "$10.50",  # the window's daily total
        "model-a",
        "Session trees",
        "root0001"[:8],
        "Cloud sessions: 1",
        "codex gpt-x $0.50",
        "Scheduled tasks",
        "nightly",
        "CRON_FAIL_LOOP",
        "7 days $10.50",
    ):
        assert part in out, part
    page = telemetry.page(r)
    assert "nightly" in page and "<script" not in page and "root0001"[:8] in page


def test_child_usage_stays_beside_its_parent_and_is_added_to_no_cost(monkeypatch, capsys) -> None:
    docs = {"/v1/usage/telemetry": TELEMETRY, "/v1/usage": USAGE}
    _, r = served_report(monkeypatch, capsys, [], docs)
    row = r["cloud"]["rows"][0]
    assert row["children"] == [
        {"harness": "codex", "model": "gpt-x", "cost_usd": 0.5, "tokens": 500}
    ]
    assert (r["cloud"]["cost_usd"], r["cloud"]["child_cost_usd"]) == (9.0, 0.5)
    assert r["models"][0]["cost_usd"] == 9.0  # the server's models, child usage not in them
    assert r["trees"][0]["cost_usd"] == 10.0  # the API's tree cost, as the server counted it


def test_a_truncated_entry_is_a_named_gap_not_a_zero(monkeypatch, capsys) -> None:
    docs = {"/v1/usage/telemetry": TELEMETRY, "/v1/usage": USAGE}
    _, r = served_report(monkeypatch, capsys, [], docs)
    assert r["truncated"] == ["sessions: 120 more past max_sessions 500"]
    out = telemetry.text(r)
    assert "not zeros" in out and "120 more past max_sessions 500" in out
    assert "120 more past max_sessions 500" in telemetry.page(r)
    only_dict = {**TELEMETRY, "truncated": [{"section": "tool_calls", "reason": "cut"}]}
    assert telemetry.build(None, telemetry_rows(only_dict), None, 7, NOW)["truncated"] == [
        "section tool_calls, reason cut"
    ]


def telemetry_rows(doc: dict) -> dict:
    return telemetry.fetch_telemetry(Served({"/v1/usage/telemetry": doc}), SINCE, int(NOW), 500)


def test_a_failed_telemetry_call_names_its_sections_and_the_usage_sections_still_render(
    monkeypatch, capsys
) -> None:
    docs = {"/v1/usage/telemetry": telemetry.Fail("HTTP 404"), "/v1/usage": USAGE}
    _, r = served_report(monkeypatch, capsys, [], docs)
    assert all("HTTP 404" in r["left_out"][s] for s in telemetry.API_SECTIONS)
    assert r["spend"]["cost_last_7d"] == 10.5 and r["daily"] is None


def test_the_report_has_no_sql_and_no_database_credentials() -> None:
    src = Path(telemetry.__file__).read_text()
    for gone in ("psql", "docker", "SELECT ", "zstd", "db-container", "DB_CONTAINER", "PASSWORD"):
        assert gone not in src, gone
    for gone in ("psql", "docker", "Postgres"):
        assert gone not in (Path(telemetry.__file__).parent.parent / "SKILL.md").read_text()


def called(sid: str, tool: str | None, n: int = 0, **kw: object) -> dict:
    return session(sid, sid, tool_calls={tool: n, "other": 4} if tool else {"other": 4}, **kw)


def test_a_tool_split_gives_each_side_its_metrics_and_the_tools_share_of_calls() -> None:
    rows = [
        called(
            "a",
            "tool-x",
            6,
            usage={"total_cost_usd": 2.0, "total_tokens": 100},
            turns=3,
            title="lead a",
        ),
        called(
            "b",
            "tool-x",
            4,
            usage={"total_cost_usd": 1.0, "total_tokens": 50},
            turns=1,
            title="verifier b",
        ),
        called(
            "c", None, usage={"total_cost_usd": 5.0, "total_tokens": 10}, turns=2, title="lead c"
        ),
    ]
    r = telemetry.build(None, db(sessions=rows), None, 7, NOW, None, "tool-x", None)
    sides = r["split"]["sides"]
    yes, no = sides["called tool-x"], sides["never called tool-x"]
    assert (yes["sessions"], yes["cost_usd"], yes["tokens"], yes["turns"]) == (2, 3.0, 150, 4)
    assert (yes["tool_calls"], yes["split_tool_calls"], yes["split_tool_share"]) == (
        18,
        10,
        10 / 18,
    )
    assert (no["sessions"], no["cost_usd"], no["split_tool_share"]) == (1, 5.0, 0.0)
    assert set(yes["roles"]) == {"lead", "verifier"}
    out = telemetry.text(r)
    assert "called tool-x" in out and "not comparable across sides" in out
    assert "not comparable" in telemetry.page(r)


def test_a_label_split_groups_sessions_by_a_launch_label() -> None:
    rows = [
        session("a", "a", labels={"arm": "one"}),
        session("b", "b", labels={"arm": "two"}),
        session("c", "c", labels={}),
    ]
    sides = telemetry.build(None, db(sessions=rows), None, 7, NOW, None, None, "arm")["split"][
        "sides"
    ]
    assert sides["has label arm"]["sessions"] == 2 and sides["no label arm"]["sessions"] == 1
    assert sides["arm=one"]["sessions"] == sides["arm=two"]["sessions"] == 1


def test_no_split_without_an_argument_and_the_pack_names_no_tool() -> None:
    assert telemetry.build(None, db(sessions=[session("a", "a")]), None, 7, NOW)["split"] is None
    src = (
        Path(telemetry.__file__).read_text()
        + (Path(telemetry.__file__).parent.parent / "SKILL.md").read_text()
    )
    assert "code-mode" not in src and "code_mode" not in src and "codemode" not in src.lower()


def test_a_cloud_session_that_failed_still_counts_with_its_cost_and_its_childrens_usage() -> None:
    kid = {"harness": "codex", "model": "gpt-x", "total_tokens": 500, "cost_usd": 0.5}
    rows = [
        session(
            "cloud1",
            "cloud1",
            agent="claude-cloud",
            live_status=4,
            usage={"total_cost_usd": 2.0, "by_model": {"claude-sonnet-5-5": {}}},
        ),
        session("other", "other"),
    ]
    api = {"sessions": [{"id": "cloud1", "child_usage": [kid]}]}
    c = telemetry.build(api, db(sessions=rows), None, 7, NOW)["cloud"]
    assert (c["sessions"], c["cost_usd"], c["child_cost_usd"]) == (1, 2.0, 0.5)
    row = c["rows"][0]
    assert row["status"] == "failed" and row["models"] == ["claude-sonnet-5-5"]
    assert row["children"] == [
        {"harness": "codex", "model": "gpt-x", "cost_usd": 0.5, "tokens": 500}
    ]


def test_a_gemini_session_shows_its_tokens_not_a_bare_zero() -> None:
    rows = [
        session(
            "g", "g", agent="antigravity-native", usage={"total_cost_usd": 0, "total_tokens": 7000}
        )
    ]
    r = telemetry.build(None, db(sessions=rows), None, 7, NOW)
    assert r["unpriced"][0]["note"] == "7,000 tokens, no price"
    assert "7,000 tokens, no price" in telemetry.text(r)
