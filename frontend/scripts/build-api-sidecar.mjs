/**
 * Build the Windows FastAPI sidecar with PyInstaller (onedir → backend/dist/nova-api).
 */
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const backendDir = path.resolve(__dirname, '..', '..', 'backend');
const spec = path.join(backendDir, 'nova_api.spec');
const outDir = path.join(backendDir, 'dist', 'nova-api');
const exe = path.join(outDir, 'nova-api.exe');

function run(cmd, args, cwd) {
  console.log(`[build-api] ${cmd} ${args.join(' ')}`);
  const r = spawnSync(cmd, args, { cwd, stdio: 'inherit', shell: true });
  if (r.status !== 0) {
    process.exit(r.status ?? 1);
  }
}

if (!fs.existsSync(spec)) {
  console.error('[build-api] missing', spec);
  process.exit(1);
}

run('py', ['-3', '-m', 'pip', 'install', '-q', 'pyinstaller'], backendDir);
run('py', ['-3', '-m', 'PyInstaller', 'nova_api.spec', '--noconfirm'], backendDir);

if (!fs.existsSync(exe)) {
  console.error('[build-api] expected output missing:', exe);
  process.exit(1);
}
console.log('[build-api] OK', exe);
