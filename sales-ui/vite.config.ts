import path from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

export default defineConfig({
  plugins: [
    react(),
    // Long batch jobs keep one EventSource open for a long time; Node's default
    // requestTimeout (~5m) can cut SSE mid-batch when proxied through this dev server.
    {
      name: "disable-http-server-request-timeout",
      configureServer(server) {
        const httpServer = server.httpServer;
        if (!httpServer) return;
        httpServer.requestTimeout = 0;
        httpServer.headersTimeout = 0;
      },
    },
  ],
  optimizeDeps: {
    include: ["@react-pdf/renderer"],
  },
  server: {
    port: 5173,
    fs: {
      allow: [repoRoot],
    },
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8765",
        changeOrigin: true,
      },
    },
  },
});
