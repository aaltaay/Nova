/**
 * Spawn / stop the local Nova FastAPI sidecar (uvicorn in dev, nova-api.exe in prod).
 */
import { spawn, spawnSync } from 'node:child_process';
import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { app, dialog, shell } from 'electron';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

/** Mirrors frontend/backend NOVA_DESKTOP_API_* constants. */
export const API_HOST = '127.0.0.1';
export const API_PORT = 8000;
export const API_BASE = `http://${API_HOST}:${API_PORT}`;

let apiChild = null;

function repoRootFromElectron() {
  // frontend/electron -> frontend -> Nova
  return path.resolve(__dirname, '..', '..');
}

function ensureUserEnv() {
  const userData = app.getPath('userData');
  const envPath = path.join(userData, '.env');
  const cacheDir = path.join(userData, 'cache');
  const logDir = path.join(userData, 'logs');
  fs.mkdirSync(cacheDir, { recursive: true });
  fs.mkdirSync(logDir, { recursive: true });

  if (!fs.existsSync(envPath)) {
    const repoEnv = path.join(repoRootFromElectron(), '.env');
    const example = path.join(repoRootFromElectron(), '.env.example');
    if (fs.existsSync(repoEnv)) {
      fs.copyFileSync(repoEnv, envPath);
    } else {
      const template = fs.existsSync(example)
        ? fs.readFileSync(example, 'utf8')
        : [
            'APCA_API_KEY_ID=',
            'APCA_API_SECRET_KEY=',
            'APCA_API_BASE_URL=https://api.alpaca.markets',
            'ALPACA_DATA_FEED=iex',
            '',
          ].join('\n');
      fs.writeFileSync(envPath, template, 'utf8');
    }
  }
  return { envPath, cacheDir, logDir, userData };
}

function sidecarEnv() {
  const { envPath, cacheDir, logDir } = ensureUserEnv();
  return {
    ...process.env,
    NOVA_ENV_PATH: envPath,
    NOVA_CACHE_DIR: cacheDir,
    NOVA_LOG_DIR: logDir,
    NOVA_API_HOST: API_HOST,
    NOVA_API_PORT: String(API_PORT),
    PYTHONUTF8: '1',
    PYTHONIOENCODING: 'utf-8',
  };
}

function packagedApiExe() {
  return path.join(process.resourcesPath, 'nova-api', 'nova-api.exe');
}

function resolveSpawn() {
  if (app.isPackaged) {
    const exe = packagedApiExe();
    if (!fs.existsSync(exe)) {
      throw new Error(`Packaged API missing: ${exe}`);
    }
    return { command: exe, args: [], cwd: path.dirname(exe) };
  }

  const backendDir = path.join(repoRootFromElectron(), 'backend');
  const runApi = path.join(backendDir, 'run_api.py');
  if (!fs.existsSync(runApi)) {
    throw new Error(`Dev API entry missing: ${runApi}`);
  }

  // Prefer Windows py launcher; fall back to python on PATH.
  const pyCheck = spawnSync('py', ['-3', '-c', 'pass'], {
    stdio: 'ignore',
    windowsHide: true,
    shell: true,
  });
  if (pyCheck.status === 0) {
    return { command: 'py', args: ['-3', runApi], cwd: backendDir };
  }
  return { command: 'python', args: [runApi], cwd: backendDir };
}

export function waitForHealth(timeoutMs = 90_000) {
  const started = Date.now();
  return new Promise((resolve, reject) => {
    const tick = () => {
      const req = http.get(`${API_BASE}/api/health`, (res) => {
        const chunks = [];
        res.on('data', (c) => chunks.push(c));
        res.on('end', () => {
          // Require an actual 200 with the expected JSON shape — a 3xx/4xx
          // (e.g. a stale/unrelated process on :8000) used to pass this
          // check as long as it was below 500 (see PROBLEM_LOG 2026-07-23).
          if (res.statusCode !== 200) {
            retry();
            return;
          }
          try {
            const body = JSON.parse(Buffer.concat(chunks).toString('utf8'));
            if (typeof body.status !== 'string') {
              retry();
              return;
            }
          } catch {
            retry();
            return;
          }
          resolve();
        });
      });
      req.on('error', retry);
      req.setTimeout(2000, () => {
        req.destroy();
        retry();
      });
    };
    const retry = () => {
      if (Date.now() - started > timeoutMs) {
        reject(new Error(`Nova API did not become healthy at ${API_BASE}/api/health`));
        return;
      }
      setTimeout(tick, 400);
    };
    tick();
  });
}

export async function startApiSidecar() {
  if (apiChild) return;

  // Reuse an already-running local API (e.g. Run Nova.bat) when healthy.
  try {
    await waitForHealth(2_500);
    console.log('[nova-api] reusing existing healthy API at', API_BASE);
    return;
  } catch {
    // nothing listening — start our own
  }

  const { command, args, cwd } = resolveSpawn();
  const env = sidecarEnv();

  apiChild = spawn(command, args, {
    cwd,
    env,
    stdio: ['ignore', 'pipe', 'pipe'],
    windowsHide: true,
  });

  apiChild.stdout?.on('data', (buf) => {
    console.log(`[nova-api] ${buf.toString().trimEnd()}`);
  });
  apiChild.stderr?.on('data', (buf) => {
    console.error(`[nova-api] ${buf.toString().trimEnd()}`);
  });
  apiChild.on('exit', (code, signal) => {
    console.log(`[nova-api] exited code=${code} signal=${signal}`);
    apiChild = null;
  });
  apiChild.on('error', (err) => {
    console.error('[nova-api] spawn error', err);
  });
}

export function stopApiSidecar() {
  if (!apiChild) return;
  const child = apiChild;
  apiChild = null;
  try {
    if (process.platform === 'win32') {
      spawn('taskkill', ['/pid', String(child.pid), '/T', '/F'], {
        stdio: 'ignore',
        windowsHide: true,
      });
    } else {
      child.kill('SIGTERM');
    }
  } catch (err) {
    console.error('[nova-api] stop failed', err);
  }
}

/** Stop our sidecar (if any), free port 8000, start fresh, wait for /api/health. */
export async function restartApiSidecar() {
  stopApiSidecar();
  apiChild = null;
  // Also kill a wedged external API (e.g. Run Nova.bat) that we did not spawn.
  if (process.platform === 'win32') {
    const stopScript = path.join(repoRootFromElectron(), 'scripts', 'Stop-NovaPorts.ps1');
    if (fs.existsSync(stopScript)) {
      spawnSync(
        'powershell',
        ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', stopScript, '-Ports', String(API_PORT)],
        { stdio: 'ignore', windowsHide: true },
      );
    }
  }
  await new Promise((r) => setTimeout(r, 500));
  await startApiSidecar();
  await waitForHealth();
}

export async function openEnvFileIfNeeded() {
  const { envPath } = ensureUserEnv();
  const raw = fs.readFileSync(envPath, 'utf8');
  const hasKey = /APCA_API_KEY_ID\s*=\s*\S+/.test(raw);
  if (hasKey) return;
  const result = await dialog.showMessageBox({
    type: 'warning',
    title: 'Nova — Alpaca keys needed',
    message:
      'No Alpaca API key found. Add APCA_API_KEY_ID and APCA_API_SECRET_KEY to your Nova .env, then restart.',
    detail: envPath,
    buttons: ['Open .env folder', 'Continue anyway'],
    defaultId: 0,
    cancelId: 1,
  });
  if (result.response === 0) {
    await shell.showItemInFolder(envPath);
  }
}
