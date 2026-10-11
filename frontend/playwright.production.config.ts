import { defineConfig } from "@playwright/test";
import base from "./playwright.config";

export default defineConfig(base, {
  projects: [{ name: "production-without-license" }],
  use: { baseURL: "http://127.0.0.1:5174" },
  // The filter-unit check imports source through Vite; all user flows run on dist.
  grepInvert:
    /browser privacy filter drops arbitrary events and removes attachments/,
  webServer: {
    command: "npm run preview -- --port 5174 --strictPort",
    url: "http://127.0.0.1:5174",
    reuseExistingServer: false,
  },
});
