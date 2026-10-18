/** Isolated chart renderer: no trading app, launch plugins, .env or API-key injection. */
import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
export default defineConfig(({ mode }) => ({
  envDir: false,
  envPrefix: [],
  plugins: [react(), {
    name: 'nova-chart-instance',
    configureServer(server) {
      server.middlewares.use((_request, response, next) => {
        response.setHeader('X-Nova-Chart-Instance', mode);
        next();
      });
    },
    configurePreviewServer(server) {
      server.middlewares.use((_request, response, next) => {
        response.setHeader('X-Nova-Chart-Instance', mode);
        next();
      });
    },
  }],
  cacheDir: '.vite-chart-gateway-cache',
  resolve: { dedupe: ['react', 'react-dom'] },
  server: { host: '127.0.0.1', port: 5179, strictPort: true },
  build: { rollupOptions: { input: 'chart-gateway.html' }, outDir: 'dist-chart-gateway' },
  test: { exclude: ['**/node_modules/**', '**/e2e/**'] },
}));
