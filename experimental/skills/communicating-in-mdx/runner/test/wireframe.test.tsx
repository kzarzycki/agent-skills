import { render, screen } from "@testing-library/react";
import { Canvas, Screen } from "../src/components/wireframe/Canvas";
import { WButton } from "../src/components/wireframe/primitives";

test("Screen shows its name and renders primitives", () => {
  render(
    <Canvas>
      <Screen name="Login">
        <WButton>Sign in</WButton>
      </Screen>
    </Canvas>,
  );
  expect(screen.getByText("Login")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Sign in" })).toBeInTheDocument();
});
