import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// Where the development server forwards /api, /docs and /openapi.json. The default is the API run
// locally with `uvicorn app.main:app --port 8000`. To develop against the Docker stack instead,
// point it at the stack's nginx origin (no port needs publishing on the API container):
//   PowerShell:  $env:VITE_DEV_API_TARGET = "http://localhost"; npm run dev
//   or put VITE_DEV_API_TARGET=http://localhost in frontend/.env.local (git-ignored)
// Only used by `npm run dev`; production builds ignore it and call the same origin.
const DEFAULT_DEV_API_TARGET = 'http://127.0.0.1:8000'

export function resolveDevApiTarget(raw: string | undefined): string {
    const value = (raw ?? '').trim()
    if (!value) return DEFAULT_DEV_API_TARGET
    let url: URL
    try {
        url = new URL(value)
    } catch {
        throw new Error(`VITE_DEV_API_TARGET must be an http(s) origin such as http://localhost, got "${value}"`)
    }
    if (url.protocol !== 'http:' && url.protocol !== 'https:') {
        throw new Error(`VITE_DEV_API_TARGET must start with http:// or https://, got "${value}"`)
    }
    return url.origin
}

export default defineConfig(({ command, mode }) => {
    const env = loadEnv(mode, process.cwd(), 'VITE_')
    const apiTarget = resolveDevApiTarget(env.VITE_DEV_API_TARGET)
    const proxied = { target: apiTarget, changeOrigin: true }

    return {
        plugins: [
            react(),
            tailwindcss(),
        ],
        // Shown only in the development 502 message (see services/api.ts). Empty for production
        // builds, so no development address can end up in a shipped bundle.
        define: {
            __DEV_API_PROXY_TARGET__: JSON.stringify(command === 'serve' ? apiTarget : ''),
        },
        server: {
            port: 3000,
            proxy: {
                '/api': proxied,
                '/docs': proxied,
                '/openapi.json': proxied,
            },
        },
    }
})
