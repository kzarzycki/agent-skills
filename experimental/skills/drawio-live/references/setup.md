# drawio-live setup

Two processes: a drawio editor (docker) and the bridge server (python stdlib).
`<skill-dir>` below = the directory containing this file's parent `SKILL.md`.

## 1. Editor container

```bash
docker run -d --name drawio-editor --restart unless-stopped \
  -p <TAILSCALE_IP>:8090:8080 jgraph/drawio
curl -s -o /dev/null -w '%{http_code}' "http://<TAILSCALE_IP>:8090/?embed=1&proto=json"   # 200
```

Bind to the Tailscale IP (`hostname -I` → the 100.64–127.x address), not
`0.0.0.0` — the host may also have a public IP. Port 8090 is arbitrary; 8080 is
often taken.

**No docker?** Point the bridge at the public embed host instead:
`--editor-url https://embed.diagrams.net/`. The editor then loads from the
internet but diagram data still flows only browser ⇄ bridge (the iframe gets
content via postMessage, nothing is uploaded).

## 2. Bridge server

```bash
python3 <skill-dir>/scripts/server.py /path/to/diagram.drawio &
# options: --port 8765  --host <ip>  --editor-url http://<ip>:8090/
```

Autodetects the Tailscale IP. Serves `scripts/index.html` (host page) at `/`,
the file at `GET /diagram`, its hash at `GET /version`, and accepts editor
autosaves at `POST /diagram` (atomic tmp+rename write).

Run it as a harness background task (it dies with the session — restart with the
same command) or under tmux/systemd for persistence.

## 3. Verify

```bash
curl -s http://<ip>:8765/version                      # {"etag": "..."}
BRIDGE_URL=http://<ip>:8765 node <skill-dir>/scripts/e2e.cjs   # E2E PASS
```

e2e.cjs needs playwright. If `node` can't resolve it, find an install and use
`NODE_PATH`: `find ~/.npm/_npx -maxdepth 3 -name playwright -type d` →
`NODE_PATH=<that>/.. node e2e.cjs`. Chromium browsers may already be in
`~/.cache/ms-playwright`. Without playwright, skip — the curl check plus a
manual user test covers it.

## Embed protocol (for debugging the host page)

Reference: drawio GitHub discussion #5612. The flow used here:

| Direction | Message |
|---|---|
| editor → host | `{"event":"init"}` on iframe ready |
| host → editor | `{"action":"load","xml":...,"autosave":1,"modified":0}` |
| editor → host | `{"event":"autosave","xml":...}` on every change |
| editor → host | `{"event":"save","xml":...}` on Ctrl+S |
| host → editor | `{"action":"status","message":...,"modified":false}` ack |

Do not switch the external-edit path from `load` to `merge` — `merge` adds new
cells but silently skips value changes to existing ones (tested).

## Security notes

- Everything binds to the tailnet; nothing is exposed publicly and no diagram
  content leaves the machine (with a local editor container).
- The bridge has no auth — anyone on the tailnet can read/write the one file it
  serves. Acceptable for a personal tailnet; don't point it at sensitive files.
