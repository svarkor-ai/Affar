import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Affär SPA — developer proxy to the FastAPI backend.
// In dev, /api is forwarded to the backend on the port set in ../BACKEND_PORT
// (default 8000). Production is served statically behind nginx which proxies /api
// to the same FastAPI service.
export default defineConfig({
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
