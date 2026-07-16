/**
 * Vite dev middleware: POST /__nova/start-api
 * Kills whatever is holding the local API port, then starts Run Nova's API script
 * in a new console window. Browser UIs cannot spawn processes themselves.
 */
import { spawn } from 'node:child_process';
import http from 'node:http';
import type { IncomingMessage, ServerResponse } from 'node:http';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import type { Plugin } from 'vite';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(__dirname, '..', '..');
const API_HOST = '127.0.0.1';
const API_PORT = 8000;
const HEALTH_URL = `http://${API_HOST}:${API_PORT}/api/health`;
const START_PATH = '/__nova/start-api';

let starting = false;

function waitForHealth(timeoutMs = 45_000): Promise<void> {
  const started = Date.now();
  return new Promise((resolve, reject) => {
    const tick = () => {
      const req = http.get(HEALTH_URL, (res) => {
        res.resume();
        if (res.statusCode && res.statusCode >= 200 && res.statusCode < 500) {
          resolve();
          return;
        }
        retry();
      });
      req.on('error', retry);
      req.setTimeout(2000, () => {
        req.destroy();
        retry();
      });
    };
    const retry = () => {
      if (Date.now() - started > timeoutMs) {
        reject(new Error(`API did not become healthy at ${HEALTH_URL}`));
        return;
      }
      setTimeout(tick, 400);
    };
    tick();
  });
}

function runPs1(scriptRel: string, args: string[] = []): Promise<void> {
  const script = path.join(repoRoot, scriptRel);
  return new Promise((resolve, reject) => {
    const child = spawn(
      'powershell',
      ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', script, ...args],
      {
        cwd: repoRoot,
        windowsHide: true,
        stdio: 'ignore',
      },
    );
    child.on('error', reject);
    child.on('exit', (code) => {
      if (code === 0 || code === null) resolve();
      else reject(new Error(`${scriptRel} exited ${code}`));
    });
  });
}

async function startApiProcess(): Promise<void> {
  await runPs1('scripts/Stop-NovaPorts.ps1', ['-Ports', String(API_PORT)]);

  const startScript = path.join(repoRoot, 'scripts', 'Start-NovaApi.ps1');
  const backendDir = path.join(repoRoot, 'backend');
  spawn(
    'cmd.exe',
    [
      '/c',
      'start',
      'Nova — API',
      '/D',
      backendDir,
      'powershell',
      '-NoProfile',
      '-ExecutionPolicy',
      'Bypass',
      '-File',
      startScript,
    ],
    {
      cwd: repoRoot,
      windowsHide: true,
      detached: true,
      stdio: 'ignore',
    },
  ).unref();

  await waitForHealth();
}

function sendJson(res: ServerResponse, status: number, body: Record<string, unknown>): void {
  res.statusCode = status;
  res.setHeader('Content-Type', 'application/json');
  res.end(JSON.stringify(body));
}

export function novaStartApiPlugin(): Plugin {
  return {
    name: 'nova-start-api',
    configureServer(server) {
      server.middlewares.use((req: IncomingMessage, res: ServerResponse, next: () => void) => {
        void (async () => {
          const url = req.url?.split('?')[0] || '';
          if (url !== START_PATH) {
            next();
            return;
          }
          if (req.method !== 'POST') {
            sendJson(res, 405, { ok: false, error: 'POST required' });
            return;
          }
          if (starting) {
            sendJson(res, 409, { ok: false, error: 'API start already in progress' });
            return;
          }
          starting = true;
          try {
            await startApiProcess();
            sendJson(res, 200, { ok: true, apiBase: `http://${API_HOST}:${API_PORT}` });
          } catch (err) {
            const message = err instanceof Error ? err.message : String(err);
            console.error('[nova-start-api]', message);
            sendJson(res, 500, { ok: false, error: message });
          } finally {
            starting = false;
          }
        })();
      });
    },
  };
}
