import { test, expect } from "vitest";
import { mkdtempSync, realpathSync, lstatSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { parseArgs, prepare } from "../bin/mdx-runner.mjs";

test("parseArgs reads dir, open, port, check", () => {
  const a = parseArgs(["--dir", "/x/y", "--open", "--port", "6000", "--check"]);
  expect(a).toEqual({ dir: "/x/y", open: true, port: "6000", check: true });
});

test("parseArgs defaults dir to null", () => {
  expect(parseArgs([]).dir).toBe(null);
});

test("prepare links the given symlink path to the resolved dir", () => {
  // Pass an isolated symlink path so the test never clobbers the runner's
  // shared `.docs` — doing so would break a live runner serving real docs.
  const target = mkdtempSync(path.join(tmpdir(), "mdx-docs-"));
  const link = path.join(mkdtempSync(path.join(tmpdir(), "mdx-link-")), ".docs");
  const { docsDir, symlinkPath } = prepare(target, link);
  expect(docsDir).toBe(realpathSync(target));
  expect(symlinkPath).toBe(link);
  expect(lstatSync(symlinkPath).isSymbolicLink()).toBe(true);
});
