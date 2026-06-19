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

test("prepare creates a .docs symlink to the resolved dir", () => {
  const target = mkdtempSync(path.join(tmpdir(), "mdx-docs-"));
  const { docsDir, symlinkPath } = prepare(target);
  expect(docsDir).toBe(realpathSync(target));
  expect(lstatSync(symlinkPath).isSymbolicLink()).toBe(true);
});
