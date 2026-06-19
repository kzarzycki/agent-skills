import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import Tabs from "../src/components/Tabs";

test("Tabs switches panels", async () => {
  render(
    <Tabs labels={["One", "Two"]}>
      <p>first</p>
      <p>second</p>
    </Tabs>,
  );
  expect(screen.getByText("first")).toBeVisible();
  await userEvent.click(screen.getByRole("tab", { name: "Two" }));
  expect(screen.getByText("second")).toBeVisible();
});
