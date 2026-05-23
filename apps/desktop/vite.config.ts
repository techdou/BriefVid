import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

const root = __dirname;
const backendStaticRoot = path.resolve(root, "../web/static");
const accessToken = process.env.VIDEO_SUM_ACCESS_TOKEN || "";
const proxyHeaders = accessToken ? { Authorization: `Bearer ${accessToken}` } : undefined;

export default defineConfig(({ command }) => ({
  root,
  base: command === "build" ? "/static/" : "/",
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 3000,
    strictPort: true,
    fs: {
      allow: [root, path.resolve(root, "..")],
    },
    proxy: {
      "/api": {
        target: "http://127.0.0.1:3838",
        headers: proxyHeaders,
      },
      "/health": "http://127.0.0.1:3838",
      "/media": {
        target: "http://127.0.0.1:3838",
        headers: proxyHeaders,
      },
      "/static/assets/icons": "http://127.0.0.1:3838",
      "/static/favicon.ico": "http://127.0.0.1:3838",
      "/static/favicon.svg": "http://127.0.0.1:3838",
      "/static/favicon-32x32.png": "http://127.0.0.1:3838",
      "/static/apple-touch-icon.png": "http://127.0.0.1:3838",
    },
  },
  build: {
    outDir: backendStaticRoot,
    emptyOutDir: false,
    assetsDir: "assets",
  },
}));
