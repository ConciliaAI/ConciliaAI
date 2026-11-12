import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// A API é a plataforma em Python (app/). Rode antes: uvicorn app.main:app --port 8000
const API = process.env.CONCILIA_API || 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: { '/api': { target: API, changeOrigin: true } },
  },
})
