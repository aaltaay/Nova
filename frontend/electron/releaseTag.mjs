/**
 * Public Nova revision is VERSION (vNNN). electron-builder still stamps
 * package.json as 0.1.N, so app.getVersion() maps to the same tag.
 */
const TAG_RE = /^v\d+$/;
const SEMVER_RE = /^(\d+)\.(\d+)\.(\d+)$/;
const TAG_MIN_WIDTH = 3;

export function formatReleaseTag(count) {
  const n = Number(count);
  if (!Number.isInteger(n) || n < 1) return '';
  return `v${String(n).padStart(TAG_MIN_WIDTH, '0')}`;
}

export function releaseTagFromText(text) {
  const raw = String(text ?? '').trim();
  if (TAG_RE.test(raw)) return raw;
  const match = SEMVER_RE.exec(raw);
  if (match) return formatReleaseTag(Number(match[3]));
  return '';
}

/**
 * Unpackaged desk: prefer the repo VERSION file.
 * Packaged builds: map electron-builder semver (same N).
 */
export function loadNovaReleaseTag({
  appVersion = '',
  isPackaged = false,
  versionFileText = '',
} = {}) {
  if (!isPackaged) {
    const fromFile = releaseTagFromText(versionFileText);
    if (fromFile) return fromFile;
  }
  const fromApp = releaseTagFromText(appVersion);
  if (fromApp) return fromApp;
  return String(appVersion || '').trim();
}
