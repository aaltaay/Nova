/**
 * A release still being built: what Help > Check for Updates names beside
 * "Nova vNNN is the latest release." (operator report, 2026-10-13).
 *
 * `Desktop pack` (.github/workflows/desktop-pack.yml) publishes a merged
 * commit's Release about seven minutes after it lands. On 2026-10-13 the
 * operator asked at 22:29 and 22:30 UTC while v1276 (merged 22:25:08) was still
 * packing -- it published 22:31:20 -- and read the true "v1275 is the latest
 * release" as a broken update pipeline. So a Help-menu check that finds nothing
 * newer asks GitHub Actions, unauthenticated, for a master run still in
 * progress (then still queued) whose installer can still be published, and works out its
 * vNNN: Nova's version is the master commit count (`git rev-list --count`), and
 * GitHub's commit list at one commit a page ends on that count (`rel="last"`).
 *
 * Only that check asks (autoUpdate.mjs); every request shares one deadline.
 * Anything else -- offline, rate-limited, an answer of another shape -- is null
 * and one line in update.log, and the dialog says what it said before.
 * Schema: architecture/schema/desk-ops.md, "A release still being built".
 */
import { RELEASES_REPO, tagNumber } from './releaseNotes.mjs';
import { formatReleaseTag } from './releaseTag.mjs';
import { errorText } from './updatePolicy.mjs';

export const RELEASE_BUILD_WORKFLOW = 'desktop-pack.yml';
/** The whole look-up, every request together: the dialog waits on it. */
export const RELEASE_BUILD_TIMEOUT_MS = 4_000;
/** Runs read per status; a burst of merges rarely has more than two building. */
export const RELEASE_BUILD_RUNS_PER_PAGE = 5;
/** desktop-pack.yml's packing job, and the runner it packs on (docs-only runs use ubuntu-latest). */
export const RELEASE_BUILD_PACK_JOB = 'Desktop pack';
export const RELEASE_BUILD_PACK_RUNNER = 'windows-latest';
/**
 * What a Release waits on besides the pack (tools/release_gate.py REQUIRED_CHECKS,
 * kept equal by releaseBuild.test.ts): CI's jobs, listed under the calling job's
 * name ("Release checks / Backend tests") or its id ("verify / ...").
 */
export const RELEASE_BUILD_REQUIRED_CHECKS = Object.freeze(['Backend tests', 'Frontend build', 'Frontend E2E', 'Agent contract']);
const CHECK_CALLERS = ['Release checks', 'verify'];

const API = `https://api.github.com/repos/${RELEASES_REPO}`;
const HEADERS = Object.freeze({ Accept: 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28' });
const SHA_RE = /^[0-9a-f]{40}$/;
const LAST_PAGE_RE = /<[^>]*[?&]page=(\d+)[^>]*>\s*;\s*rel="last"/;

/** @param {'in_progress' | 'queued'} status */
export function runsUrl(status) {
  return `${API}/actions/workflows/${RELEASE_BUILD_WORKFLOW}/runs?branch=master&status=${status}`
    + `&exclude_pull_requests=true&per_page=${RELEASE_BUILD_RUNS_PER_PAGE}`;
}

export function jobsUrl(runId) {
  return `${API}/actions/runs/${runId}/jobs?filter=latest&per_page=100`;
}

export function commitCountUrl(sha) {
  return `${API}/commits?sha=${sha}&per_page=1`;
}

/** A runs answer's master runs, newest first; a pull request's run is never one. */
export function masterRuns(body) {
  const runs = body?.workflow_runs;
  if (!Array.isArray(runs)) throw new Error('GitHub did not answer with a list of workflow runs');
  return runs
    .filter((run) => run?.head_branch === 'master' && run.event !== 'pull_request' && SHA_RE.test(run.head_sha ?? ''))
    .sort((a, b) => (Date.parse(b.created_at) || 0) - (Date.parse(a.created_at) || 0));
}

/** The newest attempt of the job under any of `names`, as release_gate.py reads it. */
function latestJob(jobs, names) {
  const newer = (a, b) => (Number(b.run_attempt) || 0) - (Number(a.run_attempt) || 0) || (Number(b.id) || 0) - (Number(a.id) || 0);
  return jobs.filter((job) => names.includes(job?.name)).sort(newer)[0] ?? null;
}

const finishedRed = (job) => job?.status === 'completed' && job.conclusion !== 'success';

/**
 * Whether a run's Release can still be published, from its jobs. False once the
 * pack or a required check finished other than green: the run stays in progress
 * while the other side runs, but release_gate.py will hold its Release. Then
 * whether it packs: PR delivery's dispatch always does; a push only on the
 * packing runner (false on another: docs only), null while its job has no runner yet.
 */
export function runWillPublish(run, jobsBody) {
  const jobs = jobsBody?.jobs;
  if (!Array.isArray(jobs)) throw new Error('GitHub did not answer with a list of jobs');
  const pack = latestJob(jobs, [RELEASE_BUILD_PACK_JOB]);
  const checks = RELEASE_BUILD_REQUIRED_CHECKS.map(
    (check) => latestJob(jobs, CHECK_CALLERS.map((caller) => `${caller} / ${check}`)),
  );
  if ([pack, ...checks].some(finishedRed)) return false;
  if (run?.event === 'workflow_dispatch') return true;
  if (run?.event !== 'push') return false;
  const labels = pack?.labels;
  if (!Array.isArray(labels) || labels.length === 0) return null;
  return labels.includes(RELEASE_BUILD_PACK_RUNNER);
}

/** The commit count a one-commit-a-page list's `Link` header ends on, or null. */
export function commitCount(link) {
  const match = LAST_PAGE_RE.exec(String(link ?? ''));
  return match ? Number(match[1]) : null;
}

/**
 * @param {{ fetch: (url: string, init?: object) => Promise<Response>,
 *   logger: { info: Function, warn: Function }, timeoutMs?: number }} deps
 */
export function createReleaseBuild({ fetch, logger, timeoutMs = RELEASE_BUILD_TIMEOUT_MS }) {
  async function get(url, signal) {
    const res = await fetch(url, { headers: HEADERS, signal });
    if (!res.ok) throw new Error(`GitHub answered HTTP ${res.status} for ${new URL(url).pathname}`);
    return res;
  }

  async function getJson(url, signal) {
    return (await get(url, signal)).json();
  }

  async function willPublish(run, signal) {
    if (run.event !== 'workflow_dispatch' && run.event !== 'push') return false;
    return runWillPublish(run, await getJson(jobsUrl(run.id), signal)) === true;
  }

  async function packingRun(signal) {
    for (const status of ['in_progress', 'queued']) {
      const runs = masterRuns(await getJson(runsUrl(status), signal));
      for (const run of runs) {
        if (await willPublish(run, signal)) return run;
      }
    }
    return null;
  }

  async function lookUp(installedTag, signal) {
    const installed = tagNumber(installedTag);
    if (installed == null) throw new Error(`the installed version ${installedTag || '(none)'} is not a vNNN tag`);
    const run = await packingRun(signal);
    if (!run) return null;
    const count = commitCount((await get(commitCountUrl(run.head_sha), signal)).headers.get('link'));
    if (count == null) throw new Error(`GitHub gave no commit count for ${run.head_sha.slice(0, 8)}`);
    if (count <= installed) return null;
    const startedAt = Date.parse(run.run_started_at ?? run.created_at);
    return {
      tag: formatReleaseTag(count),
      status: run.status === 'queued' ? 'queued' : 'in_progress',
      startedAt: Number.isFinite(startedAt) ? startedAt : null,
    };
  }

  /**
   * The release being built past `installedTag`: `{tag, status, startedAt}`, or
   * null when none is (or GitHub could not say). Never throws, never waits past the deadline.
   * @param {string} installedTag e.g. `v1275`
   */
  async function find(installedTag) {
    const controller = new AbortController();
    let timer = null;
    const deadline = new Promise((_, reject) => {
      timer = setTimeout(() => {
        const err = new Error(`no answer within ${timeoutMs} ms`);
        controller.abort(err);
        reject(err);
      }, timeoutMs);
    });
    try {
      const found = await Promise.race([lookUp(installedTag, controller.signal), deadline]);
      if (found) logger.info(`${found.tag} is being built (${found.status}); Help > Check for Updates says so`);
      return found;
    } catch (err) {
      logger.warn(`could not ask GitHub for a release still being built: ${errorText(err)}`);
      return null;
    } finally {
      clearTimeout(timer);
    }
  }

  return { find };
}
