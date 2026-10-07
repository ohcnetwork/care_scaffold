import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import ExamplePage from "./pages/ExamplePage";

/**
 * Standalone harness — NOT the federation entrypoint.
 * The host only ever imports `./manifest`. This exists so `vite preview` serves something
 * and so the plugin can be developed in isolation.
 */
window.CARE_API_URL ??= "__PLUGIN_API_URL__";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ExamplePage />
  </StrictMode>,
);
