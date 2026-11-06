import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev: the browser uses :5173 and Vite forwards API + generated pages to FastAPI.
const api = { target: "http://127.0.0.1:8000", changeOrigin: true };
export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { "/api": api, "/blog": api, "/health": api } },
});
