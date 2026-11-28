"""omnigent_agent.py gate-host: a gate goes to the Placement host with a free slot and the lowest load (#1139)."""

import ast
import inspect

import pytest
import test_omnigent_agent as base

omnigent_agent = base.omnigent_agent


class Og:
    host_id = "h-here"

    def __init__(self, status: dict[str, str] | None = None) -> None:
        self.names = {"h-a": "node-a", "h-b": "node-b", "h-here": "node-here"}
        self.status = status or {}

    def call(self, method: str, path: str) -> dict:
        return {
            "hosts": [
                {"host_id": h, "name": n, "status": self.status.get(n, "online")}
                for h, n in self.names.items()
            ]
        }

    def host(self, name: str) -> str:
        for h, n in self.names.items():
            if name in (h, n):
                return h
        raise omnigent_agent.Fail(f"no host {name}")

    def hosts(self) -> dict[str, str]:
        return self.names


@pytest.fixture
def room(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Every host has room and load 0.5 unless a test says otherwise; the names host_capacity was asked about."""
    asked: list[str] = []

    def capacity(og: Og, host: str, name: str, cpu: bool = True) -> tuple[bool | None, str]:
        asked.append(name)
        return True, "room"

    monkeypatch.setattr(omnigent_agent, "host_capacity", capacity)
    monkeypatch.setattr(omnigent_agent, "host_load", lambda og, host: 0.5)
    return asked


def slots(monkeypatch: pytest.MonkeyPatch, table: dict[str, tuple[int, int] | None]) -> None:
    monkeypatch.setattr(omnigent_agent, "gate_slots", lambda og, host: table[Og().names[host]])


def test_a_gate_goes_to_the_host_whose_slots_are_not_all_held(
    monkeypatch: pytest.MonkeyPatch, room: list[str]
) -> None:
    slots(monkeypatch, {"node-a": (2, 2), "node-b": (1, 2)})
    picked, why = omnigent_agent.pick_gate_host(Og(), ["node-a", "node-b"])
    assert picked == "node-b"
    assert why == ["node-a: all 2 gate slots held"]


def test_the_host_with_the_lowest_load_wins_among_hosts_with_a_free_slot(
    monkeypatch: pytest.MonkeyPatch, room: list[str]
) -> None:
    slots(monkeypatch, {"node-a": (0, 2), "node-b": (0, 2)})
    monkeypatch.setattr(omnigent_agent, "host_load", lambda og, host: 3.0 if host == "h-a" else 1.0)
    assert omnigent_agent.pick_gate_host(Og(), ["node-a", "node-b"])[0] == "node-b"


def test_with_no_host_readable_none_is_chosen_and_each_reason_is_given(
    monkeypatch: pytest.MonkeyPatch, room: list[str]
) -> None:
    slots(monkeypatch, {"node-a": None, "node-b": (0, 2)})
    monkeypatch.setattr(
        omnigent_agent,
        "host_capacity",
        lambda og, host, name, cpu=True: (None, "load not readable"),
    )
    picked, why = omnigent_agent.pick_gate_host(Og(), ["node-a", "node-b"])
    assert picked is None
    assert why == ["node-a: gate slots not readable", "node-b: load not readable"]


def test_a_host_the_policy_excludes_is_never_chosen(
    monkeypatch: pytest.MonkeyPatch, room: list[str]
) -> None:
    slots(monkeypatch, {"node-a": (0, 4), "node-b": (3, 4)})
    monkeypatch.setattr(omnigent_agent, "host_load", lambda og, host: 0.0 if host == "h-a" else 9.0)
    picked, why = omnigent_agent.pick_gate_host(Og(), ["node-a", "node-b"], ["node-a"])
    assert picked == "node-b"
    assert "node-a" not in room  # not even asked about
    assert why == ["node-a: kept for other work by the policy"]


def test_a_host_without_room_or_offline_is_skipped(
    monkeypatch: pytest.MonkeyPatch, room: list[str]
) -> None:
    slots(monkeypatch, {"node-a": (0, 2), "node-b": (0, 2)})
    monkeypatch.setattr(
        omnigent_agent,
        "host_capacity",
        lambda og, host, name, cpu=True: (name != "node-a", "load 9"),
    )
    assert omnigent_agent.pick_gate_host(Og(), ["node-a", "node-b"])[0] == "node-b"
    assert omnigent_agent.pick_gate_host(Og({"node-b": "offline"}), ["node-b"])[0] is None


def test_the_chooser_is_the_one_start_uses_not_a_second_copy() -> None:
    """Both call host_capacity by name, through the module, so a patched or changed rule reaches both; none of the
    capacity rule (host_limits, the memory and load floors) is written again beside it."""

    def calls(fn: object) -> set[str]:
        return {
            n.func.id
            for n in ast.walk(ast.parse(inspect.getsource(fn)))
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
        }

    assert "host_capacity" in calls(omnigent_agent.pick_gate_host)
    assert "host_capacity" in calls(omnigent_agent.start)
    assert "placement_hosts" in inspect.getsource(omnigent_agent.command)
    source = inspect.getsource(omnigent_agent.pick_gate_host)
    assert not {"MIN_AVAILABLE_MB", "MAX_LOAD_PER_CORE", "host_row", "HOST_LIMITS"} & set(
        source.replace("(", " ").replace(")", " ").split()
    )
    assert omnigent_agent.host_capacity.__module__ == omnigent_agent.start.__module__
