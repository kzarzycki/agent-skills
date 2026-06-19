import { render, screen } from "@testing-library/react";
import { vi } from "vitest";

vi.mock("../src/docs", () => ({
  loadDocs: () => [
    { slug: "sample", title: "sample", load: async () => ({ default: () => <h1>Sample Doc</h1> }) },
  ],
}));

import App from "../src/App";

test("lists docs and renders the selected one via hash", async () => {
  window.location.hash = "#sample";
  render(<App />);
  expect(screen.getByRole("link", { name: /sample/i })).toBeInTheDocument();
  expect(await screen.findByRole("heading", { name: /sample doc/i })).toBeInTheDocument();
});
