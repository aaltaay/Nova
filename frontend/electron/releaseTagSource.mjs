/**
 * Resolve the Nova revision (vNNN) without reading a tracked file.
 *
 * VERSION is a build artifact, not repo content (see D-080 / #344): CI writes it
 * with `tools/bump_version.py --sync` before packing, and a working clone simply
 * derives it from git. Order: generated VERSION file -> git commit count -> ''.
 *
 * Owner: this module. Invalidation: none -- every call re-reads the source.
 */
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';

import { formatReleaseTag, releaseTagFromText } from './releaseTag.mjs';

export function readVersionFileText(versionFile) {
  try {
    return fs.readFileSync(versionFile, 'utf8');
  } catch {
    return '';
  }
}

/** Commit count of HEAD as vNNN, or '' when git is unavailable (packaged app). */
export function releaseTagFromGit(cwd) {
  try {
    const out = execFileSync('git', ['rev-list', '--count', 'HEAD'], {
      cwd,
      encoding: 'utf8',
      stdio: ['ignore', 'pipe', 'ignore'],
    });
    return formatReleaseTag(Number(String(out).trim()));
  } catch {
    return '';
  }
}

export function resolveReleaseTag({ versionFile = '', cwd = process.cwd() } = {}) {
  return (
    releaseTagFromText(readVersionFileText(versionFile)) || releaseTagFromGit(cwd) || ''
  );
}
