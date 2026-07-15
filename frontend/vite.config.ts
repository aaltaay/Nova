import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

/** Railway / CI inject these at build time; same values as postbuild → dist/config.json */
function buildTimeApiBase(): string {
  const raw =
    process.env.VITE_API_BASE_URL?.trim() || process.env.NOVA_API_BASE?.trim() || ''
  return raw.replace(/\/$/, '')
}

function escapeMetaAttr(value: string): string {
  return value.replace(/&/g, '&amp;').replace(/"/g, '&quot;')
}

const isElectronBuild = process.env.NOVA_ELECTRON_BUILD === '1'

// https://vite.dev/config/
export default defineConfig({
  // Relative asset URLs required for Electron file:// loads; web/Vercel keep absolute `/`.
  base: isElectronBuild ? './' : '/',
  plugins: [
    react(),
    {
      name: 'inject-nova-api-base-meta',
      transformIndexHtml(html) {
        if (isElectronBuild) {
          // Desktop always uses the local sidecar; do not bake Railway URLs into the shell.
          return html
        }
        const base = buildTimeApiBase()
        if (!base || !base.startsWith('http')) return html
        const tag = `    <meta name="nova-api-base" content="${escapeMetaAttr(base)}" />\n`
        return html.replace('<head>', `<head>\n${tag}`)
      },
    },
  ],
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
  },
  build: {
    rollupOptions: {
      output: {
        // Split vendor deps into their own cacheable chunks so an app-code
        // change doesn't force re-downloading React/charting libs, and the
        // app chunk stays under Vite's 500 kB warning threshold.
        manualChunks(id) {
          if (id.includes('node_modules')) {
            if (/lightweight-charts/.test(id)) return 'vendor-charts'
            if (/[\\/]react(-dom)?[\\/]|\/react\/jsx-runtime/.test(id)) return 'vendor-react'
          }
        },
      },
    },
  },
})
