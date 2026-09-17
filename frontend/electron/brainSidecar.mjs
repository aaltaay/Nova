/**
 * Spawn / stop the standing nova-brain client next to the API sidecar.
 * Localhost bot API only -- never a second order door.
 */
import { spawn, spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { app } from 'electron';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

let brainChild = null;

function repoRootFromElectron() {
  return path.resolve(__dirname, '..', '..');
}

function resolveBrainSpawn() {
  const backendDir = path.join(repoRootFromElectron(), 'backend');
  const pyCheck = spawnSync('py', ['-3', '-c', 'pass'], {
    stdio: 'ignore',
    windowsHide: true,
    shell: true,
  });
  if (pyCheck.status === 0) {
    return { command: 'py', args: ['-3', '-m', 'nova_brain'], cwd: backendDir };
  }
  return { command: 'python', args: ['-m', 'nova_brain'], cwd: backendDir };
}

export function startBrainSidecar(env) {
  if (brainChild) return;
  if (process.env.NOVA_BRAIN_DISABLED === '1') {
    console.log('[nova-brain] skipped -- NOVA_BRAIN_DISABLED=1');
    return;
  }
  const backendDir = path.join(repoRootFromElectron(), 'backend');
  if (!fs.existsSync(path.join(backendDir, 'nova_brain', '__main__.py'))) {
    console.warn('[nova-brain] package missing -- skip');
    return;
  }
  const { command, args, cwd } = resolveBrainSpawn();
  brainChild = spawn(command, args, {
    cwd,
    env: {
      ...env,
      NOVA_API_BASE: env.NOVA_API_BASE || 'http://127.0.0.1:8000',
      NOVA_BRAIN_SESSION_ID: env.NOVA_BRAIN_SESSION_ID || 'nova-brain',
    },
    stdio: ['ignore', 'pipe', 'pipe'],
    windowsHide: true,
  });
  brainChild.stdout?.on('data', (buf) => {
    console.log(`[nova-brain] ${buf.toString().trimEnd()}`);
  });
  brainChild.stderr?.on('data', (buf) => {
    console.error(`[nova-brain] ${buf.toString().trimEnd()}`);
  });
  brainChild.on('exit', (code, signal) => {
    console.log(`[nova-brain] exited code=${code} signal=${signal}`);
    brainChild = null;
  });
  brainChild.on('error', (err) => {
    console.error('[nova-brain] spawn error', err);
    brainChild = null;
  });
}

export function stopBrainSidecar() {
  if (!brainChild) return;
  const child = brainChild;
  brainChild = null;
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
    console.error('[nova-brain] stop failed', err);
  }
}

void app;
