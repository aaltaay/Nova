/**
 * Resolve the desk revision: generated VERSION file or git (unpackaged), or map
 * app.getVersion() (packaged, where electron-builder stamped 0.1.N). See #344.
 */
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { loadNovaReleaseTag } from './releaseTag.mjs';
import { resolveReleaseTag } from './releaseTagSource.mjs';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, '..', '..');
const VERSION_FILE = path.join(REPO_ROOT, 'VERSION');

export function novaDesktopReleaseTag(app) {
  // Packaged apps ship no git dir and no VERSION file -- go straight to app.getVersion().
  const fromSource = app.isPackaged
    ? ''
    : resolveReleaseTag({ versionFile: VERSION_FILE, cwd: REPO_ROOT });
  return loadNovaReleaseTag({
    appVersion: app.getVersion(),
    isPackaged: app.isPackaged,
    versionFileText: fromSource,
  });
}
