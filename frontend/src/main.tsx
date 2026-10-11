import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { AppErrorBoundary } from "./AppErrorBoundary";
import { reportBrowserError, setupBrowserMonitoring } from "./telemetry";

void setupBrowserMonitoring();

createRoot(document.getElementById("root")!, {
  // React's default error logging may include customer text or component details.
  onCaughtError: () => reportBrowserError("UI_RENDER_FAILURE"),
  onUncaughtError: () => reportBrowserError("UI_RENDER_FAILURE"),
  onRecoverableError: () => reportBrowserError("UI_RENDER_FAILURE"),
}).render(
  <StrictMode>
    <AppErrorBoundary>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </AppErrorBoundary>
  </StrictMode>,
);
