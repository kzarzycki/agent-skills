from __future__ import annotations

import json
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import ClassVar

SCRIPT = Path(__file__).resolve().parents[1] / "skills" / "chief-of-staff" / "scripts" / "memory.py"


def _memory(tmp_path: Path, *args: str, config: dict | None = None) -> subprocess.CompletedProcess:
    repo = tmp_path / "repo"
    if not repo.exists():
        repo.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        subprocess.run(
            ["git", "remote", "add", "origin", "git@github.com:me/my-project.git"],
            cwd=repo,
            check=True,
        )
    cfg = tmp_path / "coding-agent.json"
    cfg.write_text(json.dumps(config or {}))
    env = {"PATH": "/usr/bin:/bin", "HOME": str(tmp_path), "HINDSIGHT_CONFIG": str(cfg)}
    return subprocess.run(
        [sys.executable, "-B", str(SCRIPT), *args],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


class _Hindsight(BaseHTTPRequestHandler):
    calls: ClassVar[list[tuple[str, dict, str]]] = []

    def do_POST(self) -> None:
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.calls.append((self.path, body, self.headers.get("Authorization", "")))
        if "/banks/coding-agent-new/" in self.path:
            self.send_response(404)
            self.end_headers()
            return
        reply = (
            {"results": [{"text": "owner prefers\n small PRs"}]}
            if self.path.endswith("/recall")
            else {}
        )
        data = json.dumps(reply).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args: object) -> None:
        pass


def test_unconfigured_or_disabled_is_a_no_op(tmp_path: Path) -> None:
    for config in ({}, {"apiUrl": "http://127.0.0.1:9", "disabled": True}):
        for command in ("recall", "retain"):
            result = _memory(tmp_path, command, "x", config=config)
            assert (result.returncode, result.stdout) == (0, "memory: not configured\n")


def test_recall_and_retain_use_the_repo_bank(tmp_path: Path) -> None:
    server = HTTPServer(("127.0.0.1", 0), _Hindsight)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    config = {"apiUrl": f"http://127.0.0.1:{server.server_port}/", "apiToken": "t"}
    try:
        recalled = _memory(tmp_path, "recall", "pr", "size", config=config)
        retained = _memory(tmp_path, "retain", "Owner: small PRs", config=config)
        config["bankIdTemplate"] = "coding-agent-new"
        empty = _memory(tmp_path, "recall", "pr", config=config)
    finally:
        server.shutdown()
    assert (recalled.returncode, recalled.stdout) == (0, "owner prefers small PRs\n")
    assert (retained.returncode, retained.stdout) == (
        0,
        "memory: retained in coding-agent-my-project\n",
    )
    assert (empty.returncode, empty.stdout, empty.stderr) == (0, "", "")
    (recall_path, recall_body, auth), (retain_path, retain_body, _) = _Hindsight.calls[:2]
    assert recall_path == "/v1/default/banks/coding-agent-my-project/memories/recall"
    assert recall_body["query"] == "pr size" and auth == "Bearer t"
    assert retain_path == "/v1/default/banks/coding-agent-my-project/memories"
    assert retain_body["items"] == [{"content": "Owner: small PRs", "context": "chief of staff"}]


def test_unreachable_server_warns_on_recall_and_fails_a_retain(tmp_path: Path) -> None:
    config = {"apiUrl": "http://127.0.0.1:9"}
    recalled = _memory(tmp_path, "recall", "x", config=config)
    retained = _memory(tmp_path, "retain", "x", config=config)
    assert recalled.returncode == 0 and "memory: unavailable" in recalled.stderr
    assert retained.returncode == 1 and "memory: unavailable" in retained.stderr
