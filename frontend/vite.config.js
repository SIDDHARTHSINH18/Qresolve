import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Dedicated QResolve ports (see backend/ports.py): backend 8321, dev
// frontend 5321. Port 8000 belongs to the foreign ENMA backend and is
// never used here. strictPort keeps the dev port from drifting silently.
const BACKEND = process.env.QRESOLVE_BACKEND_URL || 'http://127.0.0.1:8321'

export default defineConfig({
  plugins: [react()],
  // Relative base so the production bundle can be served from any path
  // (static host, Electron file://, or mounted under the backend).
  base: './',
  server: {
    port: 5321,
    strictPort: true,
    proxy: {
      // Same-origin in dev: the browser calls /api and Vite forwards it to
      // the FastAPI backend, so no CORS is required during development.
      '/api': { target: BACKEND, changeOrigin: true },
      '/health': { target: BACKEND, changeOrigin: true },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/test/setup.js',
    css: false,
  },
})
