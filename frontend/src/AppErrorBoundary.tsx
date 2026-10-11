import { Component, type ReactNode } from "react";
import { reportBrowserError } from "./telemetry";

export class AppErrorBoundary extends Component<
  { children: ReactNode },
  { failed: boolean }
> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch() {
    reportBrowserError("UI_RENDER_FAILURE");
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <main className="page">
        <h1>This screen could not load.</h1>
        <p role="alert">
          Reload the page to try again. If you were checking out, review your
          existing order before starting another payment.
        </p>
        <button className="button" onClick={() => window.location.reload()}>
          Reload page
        </button>
      </main>
    );
  }
}
