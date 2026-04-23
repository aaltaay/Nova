/**
 * After `vite build`, write dist/config.json so production can load the API
 * base at runtime even when Vite did not inline VITE_API_BASE_URL (e.g. some
 * Railway/Nixpacks build env quirks). Reads the same env as the Vite build.
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const dist = path.resolve(__dirname, '..', 'dist');
const base =
  process.env.VITE_API_BASE_URL?.trim() || process.env.NOVA_API_BASE?.trim();

if (!fs.existsSync(dist)) {
  console.warn('[postbuild] dist/ missing — skip config.json');
  process.exit(0);
}

if (!base) {
  console.warn(
    '[postbuild] VITE_API_BASE_URL / NOVA_API_BASE unset — skip dist/config.json',
  );
  process.exit(0);
}

const normalized = base.replace(/\/$/, '');
if (!normalized.startsWith('http://') && !normalized.startsWith('https://')) {
  console.error(
    '[postbuild] API base must start with http:// or https://, got:',
    JSON.stringify(normalized.slice(0, 80)),
  );
  process.exit(1);
}

fs.writeFileSync(
  path.join(dist, 'config.json'),
  JSON.stringify({ apiBase: normalized }),
  'utf8',
);
console.log('[postbuild] wrote dist/config.json');
