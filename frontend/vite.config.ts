import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
    plugins: [
        react(),
        tailwindcss(),
    ],
    server: {
        port: 3000,
        proxy: {
            '/api': {
                target: 'http://127.0.0.1:8000',
                changeOrigin: true,
            },
            '/docs': {
                target: 'http://127.0.0.1:8000',
                changeOrigin: true,
            },
            '/openapi.json': {
                target: 'http://127.0.0.1:8000',
                changeOrigin: true,
            },
        },
    },
})

