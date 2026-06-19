import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { vi, afterEach } from "vitest";
import QuestionForm from "../src/components/QuestionForm";

afterEach(() => {
  vi.restoreAllMocks();
});

test("POSTs answers to the runner endpoint and confirms", async () => {
  const fetchMock = vi.fn(
    async (_url: string, _init: RequestInit) => ({ ok: true, status: 200 }) as Response,
  );
  vi.stubGlobal("fetch", fetchMock);

  render(<QuestionForm id="demo" questions={[{ id: "name", label: "Name" }]} />);
  fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Zarz" } });
  fireEvent.click(screen.getByRole("button", { name: /submit answers/i }));

  await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent(/submitted/i));
  expect(fetchMock).toHaveBeenCalledWith(
    "/__mdx/answers",
    expect.objectContaining({ method: "POST" }),
  );
  const body = JSON.parse(fetchMock.mock.calls[0][1].body as string);
  expect(body).toEqual({ form: "demo", answers: { name: "Zarz" } });
});

test("falls back to a copy-paste token when there is no runner", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => {
      throw new Error("no server");
    }),
  );

  render(<QuestionForm id="demo" questions={[{ id: "name", label: "Name" }]} />);
  fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Zarz" } });
  fireEvent.click(screen.getByRole("button", { name: /submit answers/i }));

  const token = await screen.findByRole("textbox", { name: /answers token/i });
  expect((token as HTMLTextAreaElement).value).toContain('"name": "Zarz"');
});
