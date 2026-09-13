/**
 * Vite dev middleware: POST /__nova/launch-gateway
 * Spawns/focuses IB Gateway when the FastAPI process is stale or missing the route.
 */
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import net from 'node:net';
import os from 'node:os';
import path from 'node:path';
import type { IncomingMessage, ServerResponse } from 'node:http';
import type { Plugin } from 'vite';
import { alignIbcConfigIni, ibcConfigHasCredentials } from './alignIbcConfig';

const START_PATH = '/__nova/launch-gateway';

let launching = false;

function sendJson(res: ServerResponse, status: number, body: Record<string, unknown>): void {
  res.statusCode = status;
  res.setHeader('Content-Type', 'application/json');
  res.end(JSON.stringify(body));
}

function ibcDir(): string {
  return path.join(os.homedir(), '.nova', 'ibc');
}

function ibcLauncher(): string | null {
  const candidate = path.join(ibcDir(), 'start_gateway.ps1');
  return fs.existsSync(candidate) ? candidate : null;
}

function ibcConfigFile(): string {
  return path.join(ibcDir(), 'config.ini');
}

function alignLocalIbc(mode: 'paper' | 'live'): { ok: boolean; action?: string; message?: string } {
  const iniPath = ibcConfigFile();
  if (!fs.existsSync(iniPath)) {
    return {
      ok: false,
      action: 'missing_credentials',
      message:
        'Open live/paper cannot prefill Gateway login -- %USERPROFILE%\\.nova\\ibc\\config.ini is missing. See docs/ibc-gateway-setup.md.',
    };
  }
  const next = alignIbcConfigIni(fs.readFileSync(iniPath, 'utf8'), mode);
  fs.writeFileSync(iniPath, next, 'utf8');
  if (!ibcConfigHasCredentials(next)) {
    return {
      ok: false,
      action: 'missing_credentials',
      message:
        'Open live/paper cannot prefill Gateway login -- IBC config.ini is missing IbLoginId/IbPassword. See docs/ibc-gateway-setup.md.',
    };
  }
  return { ok: true };
}

function probePort(port: number, timeoutMs = 400): Promise<boolean> {
  return new Promise((resolve) => {
    const socket = net.connect({ host: '127.0.0.1', port });
    const finish = (ok: boolean) => {
      socket.removeAllListeners();
      socket.destroy();
      resolve(ok);
    };
    socket.setTimeout(timeoutMs);
    socket.once('connect', () => finish(true));
    socket.once('timeout', () => finish(false));
    socket.once('error', () => finish(false));
  });
}

async function focusOrLaunch(
  mode?: 'paper' | 'live',
): Promise<{ ok: boolean; action: string; message: string; path?: string }> {
  if (process.platform !== 'win32') {
    return {
      ok: false,
      action: 'unsupported',
      message: 'Gateway launch is only supported on Windows.',
    };
  }
  if (mode) {
    const want = mode === 'live' ? 4001 : 4002;
    if (await probePort(want)) {
      return {
        ok: true,
        action: 'already_listening',
        message:
          `${mode.toUpperCase()} Gateway is already listening on port ${want}. ` +
          'Did not start another Gateway.',
      };
    }
    const aligned = alignLocalIbc(mode);
    if (!aligned.ok) {
      return {
        ok: false,
        action: aligned.action || 'missing_credentials',
        message: aligned.message || 'IBC credentials missing.',
      };
    }
  }
  const ibc = ibcLauncher();
  if (!ibc) {
    return {
      ok: false,
      action: 'missing_ibc',
      message:
        'Open live/paper cannot prefill Gateway login -- IBC launcher missing at %USERPROFILE%\\.nova\\ibc\\start_gateway.ps1. Raw ibgateway.exe leaves username/password empty.',
    };
  }
  const extra = mode ? ['-TradingMode', mode] : [];
  spawn('powershell', ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', ibc, ...extra], {
    detached: true,
    stdio: 'ignore',
    windowsHide: true,
  }).unref();
  return {
    ok: true,
    action: 'launched_ibc',
    path: ibc,
    message:
      'Started IB Gateway via IBC (Vite). IBC fills username/password. Complete IBKR Mobile 2FA if prompted.',
  };
}

export function novaLaunchGatewayPlugin(): Plugin {
  return {
    name: 'nova-launch-gateway',
    configureServer(server) {
      server.middlewares.use((req: IncomingMessage, res: ServerResponse, next: () => void) => {
        void (async () => {
          const rawUrl = req.url || '';
          const url = rawUrl.split('?')[0] || '';
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
            const q = new URL(rawUrl, 'http://vite.local').searchParams.get('mode');
            const mode = q === 'paper' || q === 'live' ? q : undefined;
            const result = await focusOrLaunch(mode);
            sendJson(res, result.ok ? 200 : 409, result);
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
