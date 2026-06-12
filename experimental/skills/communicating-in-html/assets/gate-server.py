#!/usr/bin/env python3
"""Gate server: static serving + a live answer channel for decision pages.

Static files come from --dir (the dir holding the pages). Two dynamic routes:
  POST /gate/answer  -> body (JSON) written to --answers/<epoch-ms>.json, 200 {"ok":true}
  GET  /gate/state   -> --state file served with no-store (agent rewrites it as it works)

Pairs with render-decision-page.py output. The agent runs a background watcher
on the answers dir: the watcher exits when an answer lands, which re-invokes
the agent. Pure stdlib, no deps.

Usage:
  gate-server.py --dir <root> --port 8877 \
      --state _gate/state.json --answers _gate/answers
"""
import argparse
import json
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class Handler(SimpleHTTPRequestHandler):
    state_path: Path = None
    answers_dir: Path = None

    def log_message(self, *a):
        pass

    def _json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.split("?")[0] == "/gate/state":
            try:
                self._json(200, json.loads(self.state_path.read_text()))
            except Exception:
                self._json(200, {"state": "unknown", "version": 0})
            return
        super().do_GET()

    def do_POST(self):
        if self.path.split("?")[0] != "/gate/answer":
            self._json(404, {"ok": False})
            return
        try:
            n = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            self._json(400, {"ok": False, "error": "bad json"})
            return
        self.answers_dir.mkdir(parents=True, exist_ok=True)
        out = self.answers_dir / f"{int(time.time() * 1000)}.json"
        out.write_text(json.dumps(payload, indent=1))
        self._json(200, {"ok": True, "stored": out.name})


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dir", required=True)
    p.add_argument("--port", type=int, default=8877)
    p.add_argument("--state", required=True, help="state file, relative to --dir")
    p.add_argument("--answers", required=True, help="answers dir, relative to --dir")
    a = p.parse_args()
    root = Path(a.dir).resolve()
    Handler.state_path = root / a.state
    Handler.answers_dir = root / a.answers
    h = partial(Handler, directory=str(root))
    srv = ThreadingHTTPServer(("0.0.0.0", a.port), h)
    print(f"gate-server on :{a.port} root={root}")
    srv.serve_forever()


if __name__ == "__main__":
    main()
