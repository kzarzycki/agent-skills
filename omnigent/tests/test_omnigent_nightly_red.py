import json

from test_omnigent_queue_rejects import GitHub, acts, fleet, omnigent_agent, run


class Issues(GitHub):
    """``GitHub`` that also lists repo o/r's open issues."""

    def __init__(self, monkeypatch) -> None:
        super().__init__(monkeypatch)
        self.issues: list[dict] = []

    def gh(self, *args: str, timeout: float = 0) -> str:
        path = next((a for a in args if a.startswith("repos/")), "")
        if path.startswith("repos/o/r/issues?state=open"):
            self.calls.append(args)
            out = json.dumps(self.issues if "page=1" in path else [])
            return f'HTTP/2.0 200 OK\nEtag: "{hash(out)}"\n\n{out}'
        return super().gh(*args, timeout=timeout)


def test_an_open_red_nightly_issue_is_an_act_event_once(tmp_path, monkeypatch) -> None:
    """#1386: the manager hears of a red scheduled run the poll after its issue opens, once, with no hygiene pass."""
    registry, og = fleet(tmp_path)
    gh = Issues(monkeypatch)
    gh.issues = [
        {"number": 30, "title": "Nightly red since 1a2b3c4"},
        {"number": 31, "title": "Nightly red since pr", "pull_request": {}},
        {"number": 32, "title": "An unrelated issue"},
    ]
    run(og, registry, monkeypatch, 3)
    told = acts(og, "nightly is red")
    assert len(told) == 1 and "#30" in told[0]


def test_the_nightly_red_event_routes_act_by_rule() -> None:
    def ask():
        raise AssertionError("no model call")

    event = {"kind": "nightly-red", "session": "", "last": "", "line": "x"}
    assert omnigent_agent.route(event, ask)[:2] == ("rule", "act")
