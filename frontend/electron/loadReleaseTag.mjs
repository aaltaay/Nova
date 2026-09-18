/**
 * Read the repo VERSION file (unpackaged) or map app.getVersion() (packaged).
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { loadNovaReleaseTag } from './releaseTag.mjs';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const VERSION_FILE = path.resolve(__dirname, '..', '..', 'VERSION');

function readVersionFileText() {
  try {
    return fs.readFileSync(VERSION_FILE, 'utf8');
  } catch {
    return '';
  }
}

export function novaDesktopReleaseTag(app) {
  return loadNovaReleaseTag({
    appVersion: app.getVersion(),
    isPackaged: app.isPackaged,
    versionFileText: app.isPackaged ? '' : readVersionFileText(),
  });
}
