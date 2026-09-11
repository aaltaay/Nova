/**
 * Stamp NOVA_RELEASE_TAG from repo VERSION (vNNN) and run electron-builder.
 * Usage: node scripts/run-electron-pack.mjs [nsis|portable|dir]
 * Default (no arg): nsis + portable.
 */
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const frontendDir = path.resolve(__dirname, '..');
const repoRoot = path.resolve(frontendDir, '..');
const versionFile = path.join(repoRoot, 'VERSION');
const arg = process.argv[2];
const targets =
  arg === 'dir' ? ['dir'] : arg === 'nsis' ? ['nsis'] : arg === 'portable' ? ['portable'] : ['nsis', 'portable'];

function releaseTagFromVersionFile() {
  if (!fs.existsSync(versionFile)) {
    throw new Error(`missing ${versionFile}`);
  }
  const raw = fs.readFileSync(versionFile, 'utf8').trim();
  if (/^v\d{3,}$/.test(raw)) {
    return raw;
  }
  const legacy = raw.match(/^0\.1\.(\d+)$/);
  if (legacy) {
    return `v${legacy[1].padStart(3, '0')}`;
  }
  throw new Error(`unrecognized VERSION: ${raw}`);
}

const tag = releaseTagFromVersionFile();
const env = {
  ...process.env,
  NOVA_RELEASE_TAG: tag,
  CSC_IDENTITY_AUTO_DISCOVERY: 'false',
};

console.log(`[electron-pack] NOVA_RELEASE_TAG=${tag} targets=${targets.join(',')}`);
const r = spawnSync(
  'npx',
  ['electron-builder', '--win', ...targets, '--x64'],
  { cwd: frontendDir, env, stdio: 'inherit', shell: true },
);
process.exit(r.status ?? 1);
