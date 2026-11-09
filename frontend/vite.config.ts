import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Only the framework shared by every route gets a named vendor chunk. The analytics
// grid, AG Studio and Sentry are reached through dynamic imports, so leaving them to
// automatic splitting keeps them out of the landing page's modulepreload list.
const VENDOR_REACT = [
  "/node_modules/react/",
  "/node_modules/react-dom/",
  "/node_modules/react-router",
  "/node_modules/scheduler/",
];

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: { "/api": "http://127.0.0.1:8000" },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          const path = id.replaceAll("\\", "/");
          if (VENDOR_REACT.some((segment) => path.includes(segment))) {
            return "vendor-react";
          }
          return undefined;
        },
      },
    },
  },
});
