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

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    {
      name: 'inject-nova-api-base-meta',
      transformIndexHtml(html) {
        const base = buildTimeApiBase()
        if (!base || !base.startsWith('http')) return html
        const tag = `    <meta name="nova-api-base" content="${escapeMetaAttr(base)}" />\n`
        return html.replace('<head>', `<head>\n${tag}`)
      },
    },
  ],
})
