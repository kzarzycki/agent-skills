import { render, screen, fireEvent } from "@testing-library/react";
import QuestionForm from "../src/components/QuestionForm";

test("collects answers into token textarea", () => {
  render(<QuestionForm questions={[{ id: "name", label: "Name" }]} />);
  fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Zarz" } });
  fireEvent.click(screen.getByRole("button", { name: /copy answers/i }));
  expect((screen.getByRole("textbox", { name: /answers token/i }) as HTMLTextAreaElement).value).toContain(
    '"name": "Zarz"',
  );
});
