import { render, screen } from "@testing-library/react";
import App from "../src/App";

test("renders empty state when no docs", () => {
  render(<App />);
  expect(screen.getByText(/no .mdx documents found/i)).toBeInTheDocument();
});
