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
})
