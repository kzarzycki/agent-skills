#!/usr/bin/env python3
"""drawio-live bridge: drawio embed-mode iframe <-> a .drawio file on disk.

Serves a host page that embeds a drawio editor (embed=1&proto=json). Every
editor autosave is POSTed here and written atomically to FILE; the page polls
/version and reloads the editor when the file changes on disk (agent edits).

Usage: server.py FILE [--port 8765] [--host AUTO] [--editor-url URL]
  --host defaults to the machine's Tailscale IP (100.64/10) if present,
  else 127.0.0.1. --editor-url defaults to http://<host>:8090/.
"""
import argparse, hashlib, json, os, socket, sys, tempfile
from http.server import HTTPServer, BaseHTTPRequestHandler

ROOT = os.path.dirname(os.path.abspath(__file__))


def tailscale_ip():
    import subprocess
    ips = subprocess.run(["hostname", "-I"], capture_output=True, text=True).stdout.split()
    try:
        ips += socket.gethostbyname_ex(socket.gethostname())[2]
    except OSError:
        pass
    for ip in ips:
        if ip.count(".") == 3:
            a, b = (int(x) for x in ip.split(".")[:2])
            if a == 100 and 64 <= b <= 127:   # Tailscale CGNAT range 100.64/10
                return ip
    return "127.0.0.1"


ap = argparse.ArgumentParser()
ap.add_argument("file")
ap.add_argument("--port", type=int, default=8765)
ap.add_argument("--host", default=None)
ap.add_argument("--editor-url", default=None)
args = ap.parse_args()
FILE = os.path.abspath(args.file)
HOST = args.host or tailscale_ip()
EDITOR_URL = args.editor_url or f"http://{HOST}:8090/"


def read_file():
    with open(FILE, "rb") as f:
        data = f.read()
    return data, hashlib.sha1(data).hexdigest()


class H(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json", extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            with open(os.path.join(ROOT, "index.html")) as f:
                page = (f.read()
                        .replace("{{EDITOR_URL}}", EDITOR_URL)
                        .replace("{{TITLE}}", os.path.basename(FILE)))
            self._send(200, page.encode(), "text/html; charset=utf-8")
        elif self.path == "/diagram":
            data, etag = read_file()
            self._send(200, data, "application/xml", {"X-Etag": etag})
        elif self.path == "/version":
            _, etag = read_file()
            self._send(200, json.dumps({"etag": etag, "file": FILE}).encode())
        else:
            self._send(404, b"not found", "text/plain")

    def do_POST(self):
        if self.path != "/diagram":
            return self._send(404, b"not found", "text/plain")
        n = int(self.headers.get("Content-Length", 0))
        data = self.rfile.read(n)
        if not data.lstrip().startswith(b"<"):
            return self._send(400, b"not xml", "text/plain")
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(FILE))
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, FILE)
        self._send(200, json.dumps({"etag": hashlib.sha1(data).hexdigest()}).encode())

    def log_message(self, *a):
        pass


print(f"drawio-live bridge: http://{HOST}:{args.port}/ -> {FILE} (editor: {EDITOR_URL})",
      file=sys.stderr)
HTTPServer((HOST, args.port), H).serve_forever()
