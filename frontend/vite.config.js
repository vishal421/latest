import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
// Mirrors frontend/nginx.conf's reverse-proxy rules so `npm run dev`
// behaves exactly like the production nginx container: the app always
// calls relative paths (see src/api.js), and this proxy forwards them
// to the local backend during development.
const API_PROXY_PREFIXES = [
  "devices", "health", "logs", "diagnostics", "topology", "cli",
  "identities", "alarms", "licenses", "sessions", "traffic-analytics",
  "config-backups", "automations", "reports", "settings",
];

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3120,
    proxy: Object.fromEntries(
      API_PROXY_PREFIXES.map((prefix) => [
        `/${prefix}`,
        { target: "http://localhost:3100", changeOrigin: true, ws: true },
      ])
    ),
  },
})
