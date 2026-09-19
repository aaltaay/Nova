import path from 'path'
import { fileURLToPath } from 'url'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { loadEnv } from 'vite'
import { defineConfig } from 'vitest/config'
import { injectNovaTitle } from './electron/appTitle.mjs'
import { resolveReleaseTag } from './electron/releaseTagSource.mjs'
import { readDevNovaApiKey } from './scripts/vite-nova-api-key'
import { novaLaunchGatewayPlugin } from './scripts/vite-nova-launch-gateway'
import { novaStartApiPlugin } from './scripts/vite-nova-start-api'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

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

// VERSION is a build artifact (CI writes it with bump_version.py --sync); a working
// clone derives the tag from git instead. package.json stays 0.0.0-dev. See #344.
const novaReleaseTag = resolveReleaseTag({
  versionFile: path.resolve(__dirname, '..', 'VERSION'),
  cwd: path.resolve(__dirname, '..'),
})

function applyLocalNovaApiKey(mode: string): void {
  const rootEnv = loadEnv(mode, path.resolve(__dirname, '..'), '')
  const frontendEnv = loadEnv(mode, __dirname, '')
  const key = readDevNovaApiKey({
    VITE_NOVA_API_KEY:
      process.env.VITE_NOVA_API_KEY ||
      frontendEnv.VITE_NOVA_API_KEY ||
      rootEnv.VITE_NOVA_API_KEY,
    NOVA_API_KEY:
      process.env.NOVA_API_KEY || frontendEnv.NOVA_API_KEY || rootEnv.NOVA_API_KEY,
  })
  if (key) process.env.VITE_NOVA_API_KEY = key
}

// https://vite.dev/config/
export default defineConfig(({ command, mode }) => {
  if (command === 'serve') applyLocalNovaApiKey(mode)
  return {
  // Relative asset URLs required for Electron file:// loads; web/Vercel keep absolute `/`.
  base: isElectronBuild ? './' : '/',
  define: {
    __NOVA_RELEASE_TAG__: JSON.stringify(novaReleaseTag),
  },
  plugins: [
    react(),
    tailwindcss(),
    novaStartApiPlugin(),
    novaLaunchGatewayPlugin(),
    {
      name: 'inject-nova-window-title',
      transformIndexHtml(html) {
        return injectNovaTitle(html, novaReleaseTag)
      },
    },
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
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
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
  // Playwright lives under e2e/; keep Vitest from loading those specs.
  test: {
    exclude: ['**/node_modules/**', '**/dist/**', '**/e2e/**'],
    setupFiles: ['./src/testSetup/reactActEnvironment.ts'],
  },
}
})

