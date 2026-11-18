#!/usr/bin/env python3
"""Import a claude.ai chat or project into local files. Read-only: GET requests only.

    uv run --with playwright python claude_ai_import.py chat <url|id> <out-dir> [--port 9333]
    uv run --with playwright python claude_ai_import.py project <url|id> <out-dir> [--port 9333]
    python3 claude_ai_import.py self-test          # no network, no browser, no playwright

Output per chat: <out-dir>/transcript.md and <out-dir>/assets/. A project adds
instructions.md, knowledge/ and chats/<name>-<id8>/ (one chat folder each).

Extending later (a write path): everything goes through `Fetcher`; a writer would be a
second method there, and nothing in the importer below needs to change.
"""
import base64
import json
import os
import re
import sys
import tempfile
from pathlib import Path

API = "/api/organizations"


class Fetcher:
    """The only place that touches the network. Both methods are GET."""

    def get_json(self, path):
        raise NotImplementedError

    def get_bytes(self, path):
        raise NotImplementedError


class CdpFetcher(Fetcher):
    """Attach to an already logged-in browser and fetch from its own background tab.

    Never launches a browser, never types credentials, never opens a foreground tab.
    """

    def __init__(self, port):
        from playwright.sync_api import sync_playwright  # imported late: self-test needs none

        self._pw = sync_playwright().start()
        self._b = self._pw.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
        with self._b.contexts[0].expect_page() as p:
            self._b.new_browser_cdp_session().send(
                "Target.createTarget", {"url": "https://claude.ai/", "background": True})
        self._page = p.value
        self._page.wait_for_load_state("domcontentloaded")
        self._page.wait_for_timeout(3000)
        if "claude.ai" not in self._page.url or "/login" in self._page.url:
            self.close()
            sys.exit("claude.ai is not logged in in that browser: log in there, then rerun")

    def _fetch(self, path):
        r = self._page.evaluate(
            """async p => { const r = await fetch(p, {credentials: 'include', method: 'GET'});
              const b = new Uint8Array(await r.arrayBuffer()); let s = '';
              for (let i = 0; i < b.length; i += 32768) s += String.fromCharCode(...b.subarray(i, i + 32768));
              return {status: r.status, b64: btoa(s)}; }""", path)
        if r["status"] != 200:
            raise RuntimeError(f"GET {path.split('?')[0]} -> {r['status']}")
        return base64.b64decode(r["b64"])

    def get_json(self, path):
        return json.loads(self._fetch(path))

    def get_bytes(self, path):
        return self._fetch(path)

    def close(self):
        try:
            self._page.close()
        finally:
            self._pw.stop()


def slug(name, default="untitled"):
    s = re.sub(r"[^\w.\- ]+", "", name or "").strip().replace(" ", "-")
    return (s or default)[:60]


def sniff_ext(data):
    for magic, ext in ((b"\x89PNG", ".png"), (b"\xff\xd8\xff", ".jpg"), (b"GIF8", ".gif"),
                       (b"RIFF", ".webp"), (b"%PDF", ".pdf")):
        if data.startswith(magic):
            return ext
    return ""


class Assets:
    """Downloads a file id once into assets/ and returns the relative path (None if it fails)."""

    def __init__(self, fetcher, org, out):
        self.f, self.org, self.dir = fetcher, org, Path(out) / "assets"
        self.done, self.failed = {}, []

    def save(self, file_id, name=None):
        if file_id in self.done:
            return self.done[file_id]
        try:
            data = self.f.get_bytes(f"{API}/{self.org}/files/{file_id}/contents")
        except Exception as e:  # a missing file is reported, never fatal
            self.failed.append((file_id, name, str(e)))
            self.done[file_id] = None
            return None
        name = slug(name or file_id[:8])
        if "." not in name:
            name += sniff_ext(data)
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / f"{file_id[:8]}-{name}").write_bytes(data)
        self.done[file_id] = f"assets/{file_id[:8]}-{name}"
        return self.done[file_id]

    def save_text(self, key, name, text):
        self.dir.mkdir(parents=True, exist_ok=True)
        path = f"assets/{key[:8]}-{slug(name)}"
        (Path(self.dir.parent) / path).write_text(text)
        return path


def fence(text, lang=""):
    ticks = "```"
    while ticks in text:
        ticks += "`"
    return f"{ticks}{lang}\n{text}\n{ticks}"


def details(summary, body):
    return f"<details><summary>{summary}</summary>\n\n{body}\n\n</details>"


def render_tool_result(block, assets):
    out = []
    for item in block.get("content") or []:
        if item.get("type") == "text":
            out.append(fence(item.get("text", "")))
        elif item.get("file_uuid"):
            p = assets.save(item["file_uuid"], f"{item.get('type', 'file')}-{item['file_uuid'][:8]}")
            out.append(f"![{item.get('type', 'file')}]({p})" if p else f"(file {item['file_uuid']}: not downloadable)")
        else:
            out.append(fence(json.dumps(item, ensure_ascii=False, indent=1), "json"))
    for d in block.get("file_deliveries") or []:
        name = os.path.basename(d.get("path", ""))
        p = assets.save(d["file_uuid"], name)
        out.append(f"Delivered file `{name}` (id `{d['file_uuid']}`): " + (f"[{p}]({p})" if p else "not downloadable"))
    return "\n\n".join(out)


def render_block(block, assets):
    t = block.get("type")
    if t == "text":
        return block.get("text", "")
    if t == "thinking":
        sums = [s.get("summary", "") for s in block.get("summaries") or []]
        text = block.get("thinking") or ""
        body = text or ("_claude.ai does not return this thinking text; step summaries:_\n\n"
                        + "\n".join(f"- {s}" for s in sums) if sums else "")
        return details("Thinking", body) if body else ""
    if t == "tool_use":
        inp = block.get("input") or {}
        extra = ""
        if block.get("name") == "artifacts" and isinstance(inp.get("content"), str):
            p = assets.save_text(inp.get("id") or block.get("id", "artifact"),
                                 inp.get("title") or inp.get("id") or "artifact", inp["content"])
            extra = f"\n\nArtifact content: [{p}]({p})"
        return details(f"Tool call — {block.get('name')}",
                       fence(json.dumps(inp, ensure_ascii=False, indent=1), "json") + extra)
    if t == "tool_result":
        return details(f"Tool result — {block.get('name')}", render_tool_result(block, assets))
    return details(f"Block of type {t}", fence(json.dumps(block, ensure_ascii=False, indent=1), "json"))


def thread(chat):
    """The messages of the current branch, oldest first; others are counted, not rendered."""
    msgs = {m["uuid"]: m for m in chat["chat_messages"]}
    leaf = chat.get("current_leaf_message_uuid")
    if leaf not in msgs:
        return sorted(msgs.values(), key=lambda m: m["index"]), 0
    chain, cur = [], msgs.get(leaf)
    while cur:
        chain.append(cur)
        cur = msgs.get(cur.get("parent_message_uuid"))
    return chain[::-1], len(msgs) - len(chain)


def render_message(m, assets, n):
    who = "User" if m["sender"] == "human" else "Assistant"
    parts = [f"## {n}. {who} — {m['created_at']}"]
    blocks = m.get("content") or ([{"type": "text", "text": m.get("text", "")}])
    parts += [s for s in (render_block(b, assets) for b in blocks) if s]
    for a in m.get("attachments") or []:
        body = a.get("extracted_content")
        parts.append(details(f"Attachment — {a.get('file_name')}",
                             fence(body) if body is not None else "(no extracted text)"))
    for f in m.get("files") or []:
        p = assets.save(f["file_uuid"], f.get("file_name"))
        parts.append(f"File `{f.get('file_name')}` (id `{f['file_uuid']}`): "
                     + (f"[{p}]({p})" if p else "not downloadable"))
    return "\n\n".join(parts)


def import_chat(fetcher, org, chat_id, out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    chat = fetcher.get_json(f"{API}/{org}/chat_conversations/{chat_id}"
                            "?tree=True&rendering_mode=messages&render_all_tools=true")
    assets = Assets(fetcher, org, out)
    msgs, off_branch = thread(chat)
    head = [f"# {chat.get('name') or 'Untitled chat'}", "",
            f"- Chat: https://claude.ai/chat/{chat['uuid']}",
            f"- Model: {chat.get('model')}",
            f"- Created: {chat.get('created_at')}; updated: {chat.get('updated_at')}",
            f"- Messages: {len(msgs)} on the current branch"
            + (f"; {off_branch} more on other branches, not rendered" if off_branch else ""),
            "- claude.ai returns no thinking text, only step summaries; those are kept in `<details>`.",
            "", "---", ""]
    body = [render_message(m, assets, i) for i, m in enumerate(msgs)]
    if assets.failed:
        body.append("## Files that could not be downloaded\n\n"
                    + "\n".join(f"- `{n or i}` (id `{i}`): {e}" for i, n, e in assets.failed))
    (out / "transcript.md").write_text("\n".join(head) + "\n\n---\n\n".join(body) + "\n")
    return {"messages": len(msgs), "assets": len(list((out / "assets").glob("*"))) if (out / "assets").exists() else 0,
            "failed": len(assets.failed)}


def import_project(fetcher, org, project_id, out):
    out = Path(out)
    base = f"{API}/{org}/projects/{project_id}"
    proj = fetcher.get_json(base)
    out.mkdir(parents=True, exist_ok=True)
    (out / "instructions.md").write_text(
        f"# {proj.get('name')}\n\n{proj.get('description') or ''}\n\n## Instructions\n\n"
        f"{proj.get('prompt_template') or '(none)'}\n")
    # docs and files answered [] on the account these were probed on: item fields are
    # the usual claude.ai ones (file_name, content / file_uuid) and unverified.
    kdir, n_know, failed = out / "knowledge", 0, 0
    for d in fetcher.get_json(base + "/docs"):
        kdir.mkdir(exist_ok=True)
        (kdir / f"{(d.get('uuid') or '')[:8]}-{slug(d.get('file_name'), 'doc')}").write_text(d.get("content") or "")
        n_know += 1
    kassets = Assets(fetcher, org, out)
    kassets.dir = kdir
    for f in fetcher.get_json(base + "/files"):
        n_know += 1
        failed += kassets.save(f.get("file_uuid") or f.get("uuid"), f.get("file_name")) is None
    stats = []
    for c in fetcher.get_json(base + "/conversations"):
        sub = out / "chats" / f"{slug(c.get('name'))}-{c['uuid'][:8]}"
        stats.append(import_chat(fetcher, org, c["uuid"], sub))
    return {"knowledge_items": n_know, "knowledge_failed": failed, "chats": len(stats),
            "messages": sum(s["messages"] for s in stats), "assets": sum(s["assets"] for s in stats),
            "failed": sum(s["failed"] for s in stats)}


def parse_id(arg):
    m = re.search(r"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})", arg)
    return m.group(1) if m else arg


def org_id(fetcher):
    orgs = fetcher.get_json(API)
    chat = [o for o in orgs if "chat" in (o.get("capabilities") or [])]
    return (chat or orgs)[0]["uuid"]


# ---------- self-test: a made-up chat, no network ----------

FIXTURE = {
    "uuid": "11111111-1111-4111-8111-111111111111", "name": "Fixture chat", "model": "m",
    "created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-01T00:05:00Z",
    "current_leaf_message_uuid": "m2",
    "chat_messages": [
        {"uuid": "m0", "index": 0, "sender": "human", "created_at": "t0", "parent_message_uuid": "root",
         "content": [{"type": "text", "text": "Hello"}], "files": [],
         "attachments": [{"file_name": "notes.txt", "extracted_content": "attached text"}]},
        {"uuid": "m1", "index": 1, "sender": "assistant", "created_at": "t1", "parent_message_uuid": "m0",
         "attachments": [], "files": [{"file_uuid": "aaaaaaaa-0000", "file_name": "build.py"}],
         "content": [
             {"type": "thinking", "thinking": "", "summaries": [{"summary": "Weighing options"}]},
             {"type": "text", "text": "Here is a table:\n\n| a | b |\n|---|---|\n| 1 | 2 |"},
             {"type": "tool_use", "name": "artifacts", "id": "toolu_1",
              "input": {"id": "art1", "title": "page.html", "content": "<p>hi</p>"}},
             {"type": "tool_result", "name": "Read", "content": [
                 {"type": "image", "file_uuid": "bbbbbbbb-0000"}, {"type": "text", "text": "a ``` fence"}]},
             {"type": "tool_result", "name": "SendUserFile", "content": [{"type": "text", "text": "1 file"}],
              "file_deliveries": [{"file_uuid": "cccccccc-0000", "path": "/home/claude/part.stl"},
                                  {"file_uuid": "dddddddd-0000", "path": "/home/claude/gone.stl"}]}]},
        {"uuid": "m2", "index": 2, "sender": "human", "created_at": "t2", "parent_message_uuid": "m1",
         "content": [{"type": "text", "text": "Thanks"}], "files": [], "attachments": []},
        {"uuid": "mx", "index": 3, "sender": "human", "created_at": "t3", "parent_message_uuid": "m0",
         "content": [{"type": "text", "text": "edited branch"}], "files": [], "attachments": []},
    ],
}
FILES = {"aaaaaaaa-0000": b"print(1)", "bbbbbbbb-0000": b"\x89PNG....", "cccccccc-0000": b"solid"}


class FakeFetcher(Fetcher):
    def __init__(self):
        self.calls = []

    def get_json(self, path):
        self.calls.append(path)
        if path == API:
            return [{"uuid": "org1", "capabilities": ["chat"]}]
        if "/chat_conversations/" in path:
            return FIXTURE
        if path.endswith("/docs"):
            return [{"uuid": "d1d1d1d1-x", "file_name": "spec.md", "content": "doc text"}]
        if path.endswith("/files"):
            return [{"file_uuid": "aaaaaaaa-0000", "file_name": "k.py"}]
        if path.endswith("/conversations"):
            return [{"uuid": FIXTURE["uuid"], "name": "Fixture chat"}]
        return {"uuid": "p1", "name": "Proj", "description": "d", "prompt_template": "be brief"}

    def get_bytes(self, path):
        self.calls.append(path)
        fid = path.split("/files/")[1].split("/")[0]
        if fid not in FILES:
            raise RuntimeError("GET -> 404")
        return FILES[fid]


def self_test():
    with tempfile.TemporaryDirectory() as tmp:
        f = FakeFetcher()
        org = org_id(f)
        s = import_chat(f, org, FIXTURE["uuid"], Path(tmp) / "chat")
        t = (Path(tmp) / "chat/transcript.md").read_text()
        assert s == {"messages": 3, "assets": 4, "failed": 1}, s
        assert "edited branch" not in t and "1 more on other branches" in t
        for needle in ("## 0. User", "## 2. User", "| a | b |", "attached text", "Weighing options",
                       "part.stl", "gone.stl", "not downloadable", "````"):
            assert needle in t, needle
        names = sorted(p.name for p in (Path(tmp) / "chat/assets").iterdir())
        assert any(n.endswith("build.py") for n in names) and any(n.endswith(".png") for n in names), names
        assert (Path(tmp) / "chat/assets/art1-page.html").read_text() == "<p>hi</p>"
        assert all(c.startswith("/api/") and "POST" not in c for c in f.calls)
        p = import_project(f, org, "p1", Path(tmp) / "proj")
        assert p["chats"] == 1 and p["knowledge_items"] == 2 and p["messages"] == 3, p
        assert "be brief" in (Path(tmp) / "proj/instructions.md").read_text()
        assert (Path(tmp) / "proj/chats/Fixture-chat-11111111/transcript.md").exists()
    print("self-test ok")


def main(argv):
    if argv[:1] == ["self-test"]:
        return self_test()
    args = [a for a in argv if not a.startswith("--port")]
    port = int(os.environ.get("CLAUDE_CDP_PORT", 9333))
    for a in argv:
        if a.startswith("--port="):
            port = int(a.split("=", 1)[1])
    if len(args) != 3 or args[0] not in ("chat", "project"):
        sys.exit(__doc__)
    kind, target, out = args
    f = CdpFetcher(port)
    try:
        org = org_id(f)
        run = import_chat if kind == "chat" else import_project
        print(json.dumps(run(f, org, parse_id(target), out)))
    finally:
        f.close()


if __name__ == "__main__":
    main(sys.argv[1:])
