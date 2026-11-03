import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes("node_modules/@icon-park")) {
            return "icons";
          }
          if (id.includes("node_modules/react") || id.includes("node_modules/react-dom")) {
            return "react";
          }
        },
      },
    },
  },
  resolve: {
    alias: {
      "@": "/src",
    },
  },
  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
    watch: {
      ignored: ["**/coverage/**", "**/dist/**"],
    },
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: false,
        ws: true,
        configure(proxy) {
          // Vite's http-proxy can mis-forward binary responses when Content-Length is
          // recomputed incorrectly, surfacing as a 500 with an empty body and no backend log.
          proxy.on("proxyRes", (proxyRes) => {
            const contentType = String(proxyRes.headers["content-type"] ?? "").toLowerCase();
            if (
              contentType.startsWith("image/") ||
              contentType.startsWith("audio/") ||
              contentType.startsWith("video/") ||
              contentType.includes("octet-stream") ||
              contentType.includes("application/pdf") ||
              contentType.includes("application/vnd.openxmlformats-officedocument")
            ) {
              delete proxyRes.headers["content-length"];
            }
          });
        },
      },
    },
  },
});
