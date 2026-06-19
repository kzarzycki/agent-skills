import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { vi, afterEach } from "vitest";
import { OptionGallery, Option } from "../src/components/OptionGallery";

afterEach(() => vi.restoreAllMocks());

test("selecting does not submit; the Submit button posts the chosen option", async () => {
  const fetchMock = vi.fn(async (_u: string, _i: RequestInit) => ({ ok: true, status: 200 }) as Response);
  vi.stubGlobal("fetch", fetchMock);

  render(
    <OptionGallery id="look">
      <Option name="a" label="Minimal">
        <p>mock A</p>
      </Option>
      <Option name="b" label="Bold">
        <p>mock B</p>
      </Option>
    </OptionGallery>,
  );

  // Submit is disabled until something is selected.
  const submitBtn = screen.getByRole("button", { name: /submit choice/i });
  expect(submitBtn).toBeDisabled();

  // Selecting highlights but does NOT post.
  fireEvent.click(screen.getAllByRole("button", { name: /^select$/i })[1]);
  expect(fetchMock).not.toHaveBeenCalled();
  expect(submitBtn).toBeEnabled();
  expect(screen.getByText(/Selected: Bold/)).toBeInTheDocument();

  // Submit posts the selection.
  fireEvent.click(submitBtn);
  await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent(/Bold/));
  const body = JSON.parse(fetchMock.mock.calls[0][1].body as string);
  expect(body).toEqual({ form: "look", choice: "b", label: "Bold" });
});
