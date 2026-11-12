import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import basicSsl from '@vitejs/plugin-basic-ssl'
import { defineConfig } from 'vite'

// A API é a plataforma em Python (app/). Rode antes: uvicorn app.main:app --port 8000
const API = process.env.CONCILIA_API || 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [react(), tailwindcss(), basicSsl()],
  server: {
    host: true, // expõe no 0.0.0.0 (rede local Wi-Fi)
    port: 5173,
    proxy: {
      '/api': {
        target: API,
        changeOrigin: true,
        secure: false,
      },
    },
  },
})
