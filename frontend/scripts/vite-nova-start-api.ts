/**
 * Vite dev middleware: POST /__nova/start-api
 * Kills whatever is holding the local API port, then starts Run Nova's API script
 * in a new console window. Browser UIs cannot spawn processes themselves.
 *
 * Restart attempts are coalesced across processes (not just this Vite dev
 * server) via a lock file on disk — a second POST while a restart is already
 * in flight (e.g. a manual button click racing browser auto-heal, or two
 * Vite dev servers) gets 409 instead of racing Stop-NovaPorts/Start-NovaApi
 * and hitting WinError 10048 (see PROBLEM_LOG 2026-07-23).
 */
import { spawn } from 'node:child_process';
import fs from 'node:fs';
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
export const LOCK_PATH = path.join(repoRoot, 'backend', '.cache', 'start-api.lock');
// A start attempt that has not released its lock within this long is treated
// as abandoned (crashed Vite process, killed terminal) rather than active.
const LOCK_STALE_MS = 60_000;

export interface HealthProbe {
  ok: boolean;
  instanceId?: string;
}

/** Pure so it is unit-testable without touching the filesystem clock. */
export function isLockStale(raw: string, nowMs: number, staleMs = LOCK_STALE_MS): boolean {
  try {
    const parsed = JSON.parse(raw) as { ts?: unknown };
    if (typeof parsed.ts !== 'number' || !Number.isFinite(parsed.ts)) return true;
    return nowMs - parsed.ts > staleMs;
  } catch {
    return true;
  }
}

export function acquireLock(): boolean {
  fs.mkdirSync(path.dirname(LOCK_PATH), { recursive: true });
  try {
    fs.writeFileSync(LOCK_PATH, JSON.stringify({ pid: process.pid, ts: Date.now() }), { flag: 'wx' });
    return true;
  } catch (err) {
    if ((err as NodeJS.ErrnoException).code !== 'EEXIST') throw err;
  }
  let stale = true;
  try {
    stale = isLockStale(fs.readFileSync(LOCK_PATH, 'utf8'), Date.now());
  } catch {
    stale = true; // unreadable lock — treat as abandoned
  }
  if (!stale) return false;
  try {
    fs.rmSync(LOCK_PATH, { force: true });
    fs.writeFileSync(LOCK_PATH, JSON.stringify({ pid: process.pid, ts: Date.now() }), { flag: 'wx' });
    return true;
  } catch {
    return false;
  }
}

export function releaseLock(): void {
  try {
    fs.rmSync(LOCK_PATH, { force: true });
  } catch {
    // best-effort — a leftover lock just self-heals via the staleness check
  }
}

function probeHealth(timeoutMs = 2000): Promise<HealthProbe> {
  return new Promise((resolve) => {
    const req = http.get(HEALTH_URL, (res) => {
      const chunks: Buffer[] = [];
      res.on('data', (c: Buffer) => chunks.push(c));
      res.on('end', () => {
        if (res.statusCode !== 200) {
          resolve({ ok: false });
          return;
        }
        try {
          const body = JSON.parse(Buffer.concat(chunks).toString('utf8')) as Record<string, unknown>;
          resolve({
            ok: true,
            instanceId: typeof body.instance_id === 'string' ? body.instance_id : undefined,
          });
        } catch {
          resolve({ ok: false });
        }
      });
    });
    req.on('error', () => resolve({ ok: false }));
    req.setTimeout(timeoutMs, () => {
      req.destroy();
      resolve({ ok: false });
    });
  });
}

/**
 * Poll until a NEW instance answers 200 with the expected schema. If a
 * previous instance id is known, a healthy response from that *same* id
 * means the old process never actually died — fail loud instead of
 * declaring victory (see acceptance criteria: restart success requires a
 * new instance id, not merely any sub-500 response).
 */
function waitForHealth(previousInstanceId: string | undefined, timeoutMs = 45_000): Promise<void> {
  const started = Date.now();
  return new Promise((resolve, reject) => {
    const tick = () => {
      void probeHealth().then((probe) => {
        if (probe.ok && (!previousInstanceId || probe.instanceId !== previousInstanceId)) {
          resolve();
          return;
        }
        if (Date.now() - started > timeoutMs) {
          reject(
            new Error(
              probe.ok
                ? `API did not restart — the same instance (${previousInstanceId}) is still answering at ${HEALTH_URL}`
                : `API did not become healthy at ${HEALTH_URL}`,
            ),
          );
          return;
        }
        setTimeout(tick, 400);
      });
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
  const before = await probeHealth(1500);

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

  await waitForHealth(before.instanceId);
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
          if (!acquireLock()) {
            sendJson(res, 409, { ok: false, error: 'API start already in progress' });
            return;
          }
          try {
            await startApiProcess();
            sendJson(res, 200, { ok: true, apiBase: `http://${API_HOST}:${API_PORT}` });
          } catch (err) {
            const message = err instanceof Error ? err.message : String(err);
            console.error('[nova-start-api]', message);
            sendJson(res, 500, { ok: false, error: message });
          } finally {
            releaseLock();
          }
        })();
      });
    },
  };
}
