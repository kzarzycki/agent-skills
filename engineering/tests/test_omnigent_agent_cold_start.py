"""omnigent_agent.py start/wait print the seconds to a session's first turn, from the timestamps
the Omnigent HTTP API returns (a stand-in for the HTTP calls only, #1037)."""

import re
from pathlib import Path

import pytest
import test_omnigent_agent as base
from test_omnigent_agent import no_model, no_sleep  # noqa: F401  (the fixtures apply here by name)

omnigent_agent = base.omnigent_agent


class Server(omnigent_agent.Omnigent):
    """The real client with ``call`` answering from a dict: every method above it runs."""

    def __init__(self, made: int | None, first: int | None) -> None:
        self.base, self.host_id, self._token, self.loops = "http://x", "h", "t", {}
        self.made, self.first = made, first  # the session record's and first turn's created_at
        self.items_: list[dict] = []

    def call(self, method: str, path: str, body: object = None, **_: object) -> dict:
        if path.startswith("/v1/agents"):
            name = omnigent_agent.AGENTS["claude"]
            return {"data": [{"id": "a1", "name": name, "harness": "claude-native"}]}
        if path == "/v1/projects":
            return {"data": []}
        if (method, path) == ("GET", "/v1/hosts"):
            return {"hosts": [{"host_id": "h", "name": "host", "status": "online"}]}
        if (method, path) == ("POST", "/v1/sessions"):
            return {"id": "s1"}
        if path.endswith("/events"):  # the brief lands in the history
            text = body["data"]["content"][0]["text"]  # type: ignore[index]
            self.items_.append(
                {
                    "id": "i1",
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": text}],
                    "created_at": 5,
                }
            )
            if self.first is not None:
                self.items_.append(
                    {
                        "id": "i2",
                        "type": "message",
                        "role": "assistant",
                        "content": [],
                        "created_at": self.first,
                    }
                )
            return {}
        if "/items" in path:
            return {"data": list(reversed(self.items_))}
        if path.startswith("/v1/sessions/s1"):
            info = {
                "status": "idle",
                "pending_elicitations": [],
                "pending_inputs": [],
                "workspace": "/w",
            }
            return info | ({"created_at": self.made} if self.made is not None else {})
        raise AssertionError(f"unfaked {method} {path}")


def started(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, made: int | None, first: int | None
) -> str:
    og = Server(made, first)
    monkeypatch.setattr(omnigent_agent, "Omnigent", lambda: og)
    monkeypatch.setattr(omnigent_agent, "COLD_START_SECONDS", 0)
    monkeypatch.setattr(omnigent_agent, "pack_behind", lambda _: None)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "brief.md").write_text("do X")
    return og


def test_start_prints_seconds_from_create_to_the_first_assistant_item(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    started(monkeypatch, tmp_path, 1000, 1042)
    code = omnigent_agent.main(
        ["start", "claude", "t", "brief.md", "r.md", "--confirm-seconds", "0"]
    )
    assert code == 0, capsys.readouterr().err
    assert "cold start: 42 s to first turn" in capsys.readouterr().err


@pytest.mark.parametrize(("made", "first"), [(1000, None), (None, 1042)])
def test_a_time_the_api_does_not_give_is_unknown_never_0(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    made: int | None,
    first: int | None,
) -> None:
    started(monkeypatch, tmp_path, made, first)
    code = omnigent_agent.main(
        ["start", "claude", "t", "brief.md", "r.md", "--confirm-seconds", "0"]
    )
    assert code == 0, capsys.readouterr().err
    err = capsys.readouterr().err
    assert re.search(r"cold start: unknown s to first turn", err), err
