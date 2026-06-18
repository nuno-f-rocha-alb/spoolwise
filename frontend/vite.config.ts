import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'node:path'

// During dev the SPA runs on Vite (:5173) and talks to the existing Flask
// backend (:5000) same-origin via this proxy, so Flask-Login session cookies
// are sent without any CORS dance. In production the built SPA is served by
// Flask itself, so these proxies are a dev-only concern.
// Use 127.0.0.1 (not "localhost"): on Windows, Node may resolve "localhost" to
// IPv6 ::1 first and fail the proxy if the target only answers on IPv4.
const FLASK = 'http://127.0.0.1:5000'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    proxy: {
      '/api': { target: FLASK, changeOrigin: true },
      '/files': { target: FLASK, changeOrigin: true },
      '/static': { target: FLASK, changeOrigin: true },
    },
  },
})
