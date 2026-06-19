import { render, screen, fireEvent } from "@testing-library/react";
import { Diagram } from "../src/components/Diagram";

test("hovering a node highlights it and shows its tooltip", () => {
  render(
    <Diagram
      nodes={[{ id: "a", x: 10, y: 10, label: "Author", tip: "Writes the .mdx" }]}
    />,
  );
  const node = screen.getByText("Author");
  expect(screen.queryByRole("tooltip")).toBeNull();
  fireEvent.mouseEnter(node);
  expect(node.closest(".diagram__node")).toHaveClass("active");
  expect(screen.getByRole("tooltip")).toHaveTextContent("Writes the .mdx");
  fireEvent.mouseLeave(node);
  expect(screen.queryByRole("tooltip")).toBeNull();
});
