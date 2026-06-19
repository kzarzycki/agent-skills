import { render, screen } from "@testing-library/react";
import Callout from "../src/components/Callout";
import MetricCard from "../src/components/MetricCard";
import Checklist from "../src/components/Checklist";
import { components } from "../src/components";

test("Callout shows tone class and children", () => {
  render(
    <Callout tone="decision" title="Pick one">
      body
    </Callout>,
  );
  expect(screen.getByText("Pick one")).toBeInTheDocument();
  expect(screen.getByText("body").closest(".callout")).toHaveClass("callout--decision");
});

test("MetricCard renders label and value", () => {
  render(<MetricCard label="Tokens" value="1.2k" delta="-30%" />);
  expect(screen.getByText("Tokens")).toBeInTheDocument();
  expect(screen.getByText("1.2k")).toBeInTheDocument();
});

test("Checklist renders items", () => {
  render(<Checklist items={["a", "b"]} />);
  expect(screen.getAllByRole("listitem")).toHaveLength(2);
});

test("registry exposes all six tags", () => {
  ["Callout", "Columns", "Checklist", "FileTree", "MetricCard", "Steps", "Timeline"].forEach((t) =>
    expect(components[t]).toBeTruthy(),
  );
});
