#!/usr/bin/env node
import { existsSync, lstatSync, rmSync, symlinkSync, realpathSync, statSync } from "node:fs";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import path from "node:path";

const runnerRoot = path.dirname(path.dirname(fileURLToPath(import.meta.url)));

export function parseArgs(argv) {
  const a = { dir: null, open: false, port: null, check: false };
  for (let i = 0; i < argv.length; i++) {
    const v = argv[i];
    if (v === "--dir") a.dir = argv[++i];
    else if (v === "--open") a.open = true;
    else if (v === "--port") a.port = argv[++i];
    else if (v === "--check") a.check = true;
  }
  return a;
}

// Resolve the docs dir: explicit --dir, else .work/ if present, else docs/, relative to cwd.
export function resolveDir(dir) {
  if (dir) return path.resolve(dir);
  const cwd = process.cwd();
  for (const cand of [".work", "docs"]) {
    const p = path.join(cwd, cand);
    if (existsSync(p) && statSync(p).isDirectory()) return p;
  }
  return cwd;
}

function symlinkExists(p) {
  try {
    lstatSync(p);
    return true;
  } catch {
    return false;
  }
}

export function prepare(dir) {
  const docsDir = realpathSync(resolveDir(dir));
  const symlinkPath = path.join(runnerRoot, ".docs");
  if (symlinkExists(symlinkPath)) rmSync(symlinkPath, { force: true });
  symlinkSync(docsDir, symlinkPath, "dir");
  return { docsDir, symlinkPath };
}

export function run(argv) {
  const args = parseArgs(argv);
  const { docsDir } = prepare(args.dir);
  console.log(`[mdx-runner] serving ${docsDir}`);
  if (args.check) return 0;
  const viteArgs = [];
  if (args.open) viteArgs.push("--open");
  const child = spawn("npx", ["vite", ...viteArgs], {
    cwd: runnerRoot,
    stdio: "inherit",
    env: { ...process.env, MDX_DOCS_DIR: docsDir, MDX_RUNNER_PORT: args.port || "" },
  });
  child.on("exit", (code) => process.exit(code ?? 0));
}

if (import.meta.url === `file://${process.argv[1]}`) run(process.argv.slice(2));
