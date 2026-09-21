/**
 * Stamp NOVA_RELEASE_TAG (vNNN) from the generated VERSION file or git, then run
 * electron-builder.
 * Usage: node scripts/run-electron-pack.mjs [nsis|dir]
 * Default (no arg): the NSIS installer -- the only Windows target Nova ships
 * (#347: a portable EXE can never update itself).
 *
 * Packing never publishes. electron-builder publishes implicitly on a CI tag
 * build unless told otherwise, and Nova's Release is cut by desktop-pack.yml
 * from the verified artifact, so `--publish never` stays on every pack. The
 * GitHub publish config still makes it write latest.yml + .blockmap next to the
 * installer -- the feed electron-updater reads.
 */
import { spawnSync } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { resolveReleaseTag } from '../electron/releaseTagSource.mjs';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const frontendDir = path.resolve(__dirname, '..');
const repoRoot = path.resolve(frontendDir, '..');
const versionFile = path.join(repoRoot, 'VERSION');
const arg = process.argv[2];
const targets = arg === 'dir' ? ['dir'] : ['nsis'];

// VERSION is a build artifact, so a clean clone has none -- fall back to git. See #344.
const tag = resolveReleaseTag({ versionFile, cwd: repoRoot });
if (!tag) {
  throw new Error(
    `cannot resolve a release tag: no ${versionFile} and no git history. ` +
      'Run: py -3 tools/bump_version.py --sync',
  );
}
const env = {
  ...process.env,
  NOVA_RELEASE_TAG: tag,
  CSC_IDENTITY_AUTO_DISCOVERY: 'false',
};

console.log(`[electron-pack] NOVA_RELEASE_TAG=${tag} targets=${targets.join(',')}`);
const r = spawnSync(
  'npx',
  ['electron-builder', '--win', ...targets, '--x64', '--publish', 'never'],
  { cwd: frontendDir, env, stdio: 'inherit', shell: true },
);
process.exit(r.status ?? 1);
