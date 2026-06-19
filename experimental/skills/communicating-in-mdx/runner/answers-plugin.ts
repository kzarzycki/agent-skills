import { appendFileSync, mkdirSync } from "node:fs";
import path from "node:path";
import type { IncomingMessage, ServerResponse } from "node:http";
import type { Plugin } from "vite";

// Vite dev middleware: sinks QuestionForm submissions to a JSONL file the agent
// reads. Same-origin localhost POST — nothing leaves the machine. Dev-only
// (configureServer never runs during `vite build`).
export function answersPlugin(answersFile: string): Plugin {
  return {
    name: "mdx-answers",
    configureServer(server) {
      server.middlewares.use(
        "/__mdx/answers",
        (req: IncomingMessage, res: ServerResponse, next: () => void) => {
          if (req.method !== "POST") return next();
          let body = "";
          req.on("data", (c) => (body += c));
          req.on("end", () => {
            try {
              const data = JSON.parse(body || "{}");
              const line = JSON.stringify({ ts: new Date().toISOString(), ...data });
              mkdirSync(path.dirname(answersFile), { recursive: true });
              appendFileSync(answersFile, line + "\n");
              res.statusCode = 200;
              res.setHeader("content-type", "application/json");
              res.end(JSON.stringify({ ok: true }));
            } catch (err) {
              res.statusCode = 400;
              res.setHeader("content-type", "application/json");
              res.end(JSON.stringify({ ok: false, error: String(err) }));
            }
          });
        },
      );
    },
  };
}
