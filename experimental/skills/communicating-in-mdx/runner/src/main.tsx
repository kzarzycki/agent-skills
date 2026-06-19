import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { MDXProvider } from "@mdx-js/react";
import App from "./App";
import { components } from "./components";
import "./styles/design-system.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <MDXProvider components={components}>
      <App />
    </MDXProvider>
  </StrictMode>,
);
