/// <reference types="vitest" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import { VitePWA } from "vite-plugin-pwa";

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: "autoUpdate",
      manifest: {
        name: "HELL UPLOADS",
        short_name: "HELL UPLOADS",
        description: "Private AI tutorial research and video production",
        theme_color: "#0f0e13",
        background_color: "#0f0e13",
        display: "standalone",
        icons: [{ src: "/icon.svg", sizes: "any", type: "image/svg+xml", purpose: "any maskable" }],
      },
      workbox: { navigateFallbackDenylist: [/^\/api/, /^\/health/] },
    }),
  ],
  test: { environment: "jsdom", globals: true, setupFiles: ["./src/test/setup.ts"] },
});
