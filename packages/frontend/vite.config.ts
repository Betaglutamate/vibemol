import { defineConfig } from "vite";

// The production build is emitted directly into the backend package's `static/`
// dir, so `vibemol serve` serves the SPA with no extra copy step. During dev,
// `npm run dev` runs Vite and proxies the API + WebSocket to the backend.
export default defineConfig({
  build: {
    outDir: "../backend/vibemol/static",
    emptyOutDir: true,
  },
  server: {
    proxy: {
      "/api": "http://localhost:8000",
      "/ws": { target: "ws://localhost:8000", ws: true },
    },
  },
  test: {
    globals: true,
    environment: "node",
  },
});
