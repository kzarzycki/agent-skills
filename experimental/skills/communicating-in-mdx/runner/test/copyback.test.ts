import { serializeAnswers } from "../src/lib/copyback";

test("wraps JSON in ANSWERS token", () => {
  const t = serializeAnswers({ a: "1" });
  expect(t.startsWith("ANSWERS<<<")).toBe(true);
  expect(t.includes('"a": "1"')).toBe(true);
  expect(t.trim().endsWith(">>>ANSWERS")).toBe(true);
});
