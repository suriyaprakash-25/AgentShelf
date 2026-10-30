import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

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
        manualChunks: {
          "vendor-react": ["react", "react-dom", "react-router-dom"],
          "vendor-ag-grid": ["ag-grid-community", "ag-grid-react"],
          "vendor-ag-studio": ["ag-studio", "ag-studio-react"],
          "vendor-sentry": ["@sentry/browser"],
        },
      },
    },
  },
});
