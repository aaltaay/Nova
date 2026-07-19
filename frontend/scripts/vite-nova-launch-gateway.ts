/**
 * Vite dev middleware: POST /__nova/launch-gateway
 * Spawns/focuses IB Gateway when the FastAPI process is stale or missing the route.
 */
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import type { IncomingMessage, ServerResponse } from 'node:http';
import type { Plugin } from 'vite';

const START_PATH = '/__nova/launch-gateway';
const GATEWAY_ROOT = 'C:\\Jts\\ibgateway';
const GATEWAY_DEFAULT = 'C:\\Jts\\ibgateway\\1045\\ibgateway.exe';

let launching = false;

function sendJson(res: ServerResponse, status: number, body: Record<string, unknown>): void {
  res.statusCode = status;
  res.setHeader('Content-Type', 'application/json');
  res.end(JSON.stringify(body));
}

function resolveGatewayExe(): string | null {
  const override = (process.env.IBKR_GATEWAY_EXE || '').trim();
  if (override && fs.existsSync(override)) return override;
  if (fs.existsSync(GATEWAY_DEFAULT)) return GATEWAY_DEFAULT;
  if (!fs.existsSync(GATEWAY_ROOT)) return null;
  const versions = fs
    .readdirSync(GATEWAY_ROOT, { withFileTypes: true })
    .filter((d) => d.isDirectory())
    .map((d) => path.join(GATEWAY_ROOT, d.name, 'ibgateway.exe'))
    .filter((p) => fs.existsSync(p));
  return versions.sort().at(-1) ?? null;
}

function ibcLauncher(): string | null {
  const candidate = path.join(os.homedir(), '.nova', 'ibc', 'start_gateway.ps1');
  return fs.existsSync(candidate) ? candidate : null;
}

function focusOrLaunch(): { ok: boolean; action: string; message: string; path?: string } {
  const ibc = ibcLauncher();
  if (ibc) {
    spawn('powershell', ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', ibc], {
      detached: true,
      stdio: 'ignore',
      windowsHide: true,
    }).unref();
    return {
      ok: true,
      action: 'launched_ibc',
      path: ibc,
      message:
        'Started IB Gateway via IBC (Vite). Complete IBKR Mobile 2FA if prompted.',
    };
  }

  const exe = resolveGatewayExe();
  if (!exe) {
    return {
      ok: false,
      action: 'not_found',
      message: `IB Gateway not found under ${GATEWAY_ROOT}. Install it or set IBKR_GATEWAY_EXE.`,
    };
  }

  spawn(exe, [], {
    cwd: path.dirname(exe),
    detached: true,
    stdio: 'ignore',
    windowsHide: false,
  }).unref();

  // Best-effort focus (may race with window creation).
  spawn(
    'powershell',
    [
      '-NoProfile',
      '-Command',
      "Get-Process ibgateway,tws -ErrorAction SilentlyContinue | ForEach-Object { $_.MainWindowHandle }",
    ],
    { detached: true, stdio: 'ignore', windowsHide: true },
  ).unref();

  return {
    ok: true,
    action: 'launched',
    path: exe,
    message:
      'Started IB Gateway (Vite). Look for its login window and complete 2FA if prompted.',
  };
}

export function novaLaunchGatewayPlugin(): Plugin {
  return {
    name: 'nova-launch-gateway',
    configureServer(server) {
      server.middlewares.use((req: IncomingMessage, res: ServerResponse, next: () => void) => {
        void (async () => {
          const url = req.url?.split('?')[0] || '';
          if (url !== START_PATH) {
            next();
            return;
          }
          if (req.method !== 'POST') {
            sendJson(res, 405, { ok: false, message: 'POST required' });
            return;
          }
          if (launching) {
            sendJson(res, 409, {
              ok: false,
              action: 'busy',
              message: 'Gateway launch already in progress',
            });
            return;
          }
          launching = true;
          try {
            const result = focusOrLaunch();
            sendJson(res, result.ok ? 200 : 404, result);
          } catch (err) {
            const message = err instanceof Error ? err.message : String(err);
            console.error('[nova-launch-gateway]', message);
            sendJson(res, 500, { ok: false, action: 'error', message });
          } finally {
            launching = false;
          }
        })();
      });
    },
  };
}
