import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./index.css";
import { restoreSyntaxScheme } from "./lib/syntax";
import { restoreAppearance } from "./lib/theme";

restoreAppearance();
restoreSyntaxScheme();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
