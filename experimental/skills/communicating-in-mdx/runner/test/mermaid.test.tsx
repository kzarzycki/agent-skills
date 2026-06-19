import { render, screen } from "@testing-library/react";
import { vi } from "vitest";

vi.mock("mermaid", () => ({
  default: {
    initialize: vi.fn(),
    render: vi.fn(async () => ({ svg: "<svg data-testid='m'></svg>" })),
  },
}));

import Mermaid from "../src/components/Mermaid";

test("renders mermaid svg", async () => {
  render(<Mermaid chart="graph TD; A-->B" />);
  expect(await screen.findByTestId("m")).toBeInTheDocument();
});
