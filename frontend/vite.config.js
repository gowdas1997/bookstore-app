import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    proxy: {
      "/api/users": "http://localhost:8001",
      "/api/books": "http://localhost:8002",
      "/api/orders": "http://localhost:8003",
    },
  },
});
