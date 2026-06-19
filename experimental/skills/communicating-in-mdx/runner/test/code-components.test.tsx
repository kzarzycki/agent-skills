import { render, screen } from "@testing-library/react";
import Diff from "../src/components/Diff";

test("Diff tints added and removed lines", () => {
  render(<Diff code={"+added\n-removed\n unchanged"} />);
  expect(screen.getByText("added").closest(".diff__line")).toHaveClass("diff__line--add");
  expect(screen.getByText("removed").closest(".diff__line")).toHaveClass("diff__line--del");
});
