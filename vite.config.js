import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Affär SPA — developer proxy to the FastAPI backend.
// In dev, /api is forwarded to the backend on the port set in ../BACKEND_PORT
// (default 8000). Production is served statically behind nginx which proxies /api
// to the same FastAPI service.
export default defineConfig({
  // MC 707.2 G2: the SPA is served by the FastAPI backend, which also
  // mounts under an optional AFFAR_ROOT_PATH prefix (e.g. /affar). Relative
  // asset URLs ("./assets/...") resolve under whatever prefix the page was
  // loaded from, so one build works at root AND under any prefix — no baked
  // "/assets" absolute URLs that would 404 outside the root.
  base: './',
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: process.env.AFFAR_API_URL || 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
