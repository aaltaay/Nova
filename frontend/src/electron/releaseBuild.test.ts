/**
 * Help > Check for Updates names a release still being built (operator report,
 * 2026-10-13: v1276 merged 22:25:08 UTC, the operator asked at 22:29 and 22:30,
 * it published 22:31:20, and "Nova v1275 is the latest release." read as a
 * broken pipeline). Only a run that will pack an installer counts, its vNNN is
 * its head's commit count, and any failure says exactly what the dialog said
 * before, with one line in update.log.
 */
import fs from 'node:fs';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  RELEASE_BUILD_PACK_JOB,
  RELEASE_BUILD_PACK_RUNNER,
  RELEASE_BUILD_REQUIRED_CHECKS,
  RELEASE_BUILD_TIMEOUT_MS,
  commitCount,
  createReleaseBuild,
  jobsUrl,
  masterRuns,
  runWillPublish,
  runsUrl,
} from '../../electron/releaseBuild.mjs';
import { buildingDetail, manualCheckResult } from '../../electron/updateCopy.mjs';
import { INITIAL_UPDATE_STATE, reduceUpdateState } from '../../electron/updatePolicy.mjs';

const SHA = 'c7dc401d'.padEnd(40, '0');
const OLD_SHA = 'b'.repeat(40);
const API = 'https://api.github.com/repos/aaltaay/Nova';
const MERGED_AT = Date.parse('2026-10-13T22:25:10Z');

const run = (over: Record<string, unknown> = {}) => ({
  id: 38477662219,
  status: 'in_progress',
  event: 'workflow_dispatch',
  head_branch: 'master',
  head_sha: SHA,
  created_at: '2026-10-13T22:25:10Z',
  run_started_at: '2026-10-13T22:25:10Z',
  ...over,
});
// GitHub's own Link header for a one-commit-a-page list (probed 2026-10-13: page 1278 on master's tip).
const linkTo = (count: number) =>
  `<https://api.github.com/repositories/1210849735/commits?sha=${SHA}&per_page=1&page=2>; rel="next", `
  + `<https://api.github.com/repositories/1210849735/commits?sha=${SHA}&per_page=1&page=${count}>; rel="last"`;
const job = (name: string, labels: string[], over: Record<string, unknown> = {}) => ({
  id: 1,
  run_attempt: 1,
  name,
  status: 'in_progress',
  conclusion: null,
  labels,
  ...over,
});
const red = { status: 'completed', conclusion: 'failure' };
const green = { status: 'completed', conclusion: 'success' };
// PR delivery's run while it packs: the pack on Windows, Release checks still running.
const packing = { jobs: [job('Desktop pack', ['windows-latest']), job('Release checks / Backend tests', ['ubuntu-latest'])] };

type Answer = { status?: number; body?: unknown; link?: string | null };
type Route = Answer | ((init?: { signal?: AbortSignal }) => Promise<unknown>);

/** A GitHub that answers each URL by the first route whose key it contains; anything else is a 404. */
function github(routes: Record<string, Route>) {
  const calls: string[] = [];
  const fetch = vi.fn(async (url: string, init?: { signal?: AbortSignal }) => {
    calls.push(url);
    const key = Object.keys(routes).find((k) => url.includes(k));
    const route = key ? routes[key] : { status: 404, body: { message: 'Not Found' } };
    if (typeof route === 'function') return route(init);
    const status = route.status ?? 200;
    return {
      ok: status < 400,
      status,
      json: async () => route.body,
      headers: { get: (name: string) => (name.toLowerCase() === 'link' ? route.link ?? null : null) },
    };
  });
  return { fetch, calls };
}

const logger = { info: vi.fn(), warn: vi.fn() };
const watch = (fetch: ReturnType<typeof vi.fn>) => createReleaseBuild({ fetch, logger });

beforeEach(() => {
  logger.info.mockClear();
  logger.warn.mockClear();
});

afterEach(() => {
  vi.useRealTimers();
});

describe('which run is a release being built', () => {
  it('reads only master runs, newest first, never a pull request', () => {
    const runs = masterRuns({
      workflow_runs: [
        run({ id: 1, created_at: '2026-10-13T22:20:00Z' }),
        run({ id: 2, event: 'pull_request', head_branch: 'feature/x' }),
        run({ id: 3, head_branch: 'v1276' }),
        run({ id: 4, created_at: '2026-10-13T22:25:10Z' }),
        run({ id: 5, head_sha: 'not-a-sha' }),
      ],
    });
    expect(runs.map((r) => r.id)).toEqual([4, 1]);
    expect(() => masterRuns({ message: 'API rate limit exceeded' })).toThrow('list of workflow runs');
  });

  it('counts a dispatch run while its Release can still be published', () => {
    const dispatch = run();
    expect(runWillPublish(dispatch, packing)).toBe(true);
    // Queued: no job has started yet.
    expect(runWillPublish(dispatch, { jobs: [] })).toBe(true);
    expect(runWillPublish(dispatch, { jobs: [job('Desktop pack', ['windows-latest'], green)] })).toBe(true);
  });

  it('drops a run whose pack or a required check finished red, though the run is still in progress (Codex review)', () => {
    const dispatch = run();
    expect(runWillPublish(dispatch, { jobs: [job('Desktop pack', ['windows-latest'], red)] })).toBe(false);
    for (const check of RELEASE_BUILD_REQUIRED_CHECKS) {
      for (const caller of ['Release checks', 'verify']) {
        const jobs = [job('Desktop pack', ['windows-latest']), job(`${caller} / ${check}`, ['ubuntu-latest'], red)];
        expect(runWillPublish(dispatch, { jobs }), `${caller} / ${check}`).toBe(false);
      }
    }
    for (const conclusion of ['cancelled', 'timed_out', 'skipped']) {
      const jobs = [job('Desktop pack', ['windows-latest'], { status: 'completed', conclusion })];
      expect(runWillPublish(dispatch, { jobs }), conclusion).toBe(false);
    }
    // A check outside the gate's list (a security scan is warning-only) holds nothing.
    const scan = job('Release checks / CodeQL', ['ubuntu-latest'], red);
    expect(runWillPublish(dispatch, { jobs: [...packing.jobs, scan] })).toBe(true);
  });

  it("reads each job's newest attempt, so a re-run of a red pack counts again", () => {
    const jobs = [
      job('Desktop pack', ['windows-latest'], { id: 10, run_attempt: 1, ...red }),
      job('Desktop pack', ['windows-latest'], { id: 20, run_attempt: 2 }),
    ];
    expect(runWillPublish(run(), { jobs })).toBe(true);
    expect(runWillPublish(run(), { jobs: [...jobs].reverse() })).toBe(true);
  });

  it('knows a push run packs only once its Desktop pack job runs on Windows', () => {
    const push = run({ event: 'push' });
    const changes = job('changes / Select affected checks', ['ubuntu-latest'], green);
    expect(runWillPublish(push, { jobs: [changes, job('Desktop pack', ['windows-latest'])] })).toBe(true);
    // A docs-only push packs nothing: the job runs on Linux and the commit gets a tag, no Release.
    expect(runWillPublish(push, { jobs: [job('Desktop pack', ['ubuntu-latest'], green)] })).toBe(false);
    // Before `changes` answers, the job is not listed with a runner: not counted.
    expect(runWillPublish(push, { jobs: [changes] })).toBeNull();
    expect(runWillPublish(push, { jobs: [job('Desktop pack', [])] })).toBeNull();
    expect(runWillPublish(run({ event: 'schedule' }), packing)).toBe(false);
    expect(() => runWillPublish(push, {})).toThrow('list of jobs');
  });

  it('names the same jobs as the release gate and the workflow', () => {
    const gate = fs.readFileSync(new URL('../../../tools/release_gate.py', import.meta.url), 'utf8');
    const tuple = /REQUIRED_CHECKS: tuple\[str, \.\.\.\] = \(([^)]*)\)/.exec(gate)?.[1] ?? '';
    expect([...tuple.matchAll(/"([^"]+)"/g)].map((m) => m[1])).toEqual([...RELEASE_BUILD_REQUIRED_CHECKS]);
    expect(gate).toContain('CHECKS_PREFIX = "Release checks"');
    expect(gate).toContain(`PACK_CHECK = "${RELEASE_BUILD_PACK_JOB}"`);
    const workflow = fs.readFileSync(new URL('../../../.github/workflows/desktop-pack.yml', import.meta.url), 'utf8');
    expect(workflow).toMatch(new RegExp(`name: ${RELEASE_BUILD_PACK_JOB}\\r?\\n`));
    expect(workflow).toMatch(/name: Release checks\r?\n/);
    expect(workflow).toContain(`'${RELEASE_BUILD_PACK_RUNNER}'`);
  });

  it("reads a commit's vNNN from the last page of a one-commit-a-page list", () => {
    expect(commitCount(linkTo(1276))).toBe(1276);
    expect(commitCount(null)).toBeNull();
    expect(commitCount('<https://api.github.com/x?page=2>; rel="next"')).toBeNull();
  });
});

describe('createReleaseBuild', () => {
  it('names the release PR delivery is packing, and when it started', async () => {
    const gh = github({
      'status=in_progress': { body: { total_count: 1, workflow_runs: [run()] } },
      '/runs/38477662219/jobs': { body: packing },
      [`/commits?sha=${SHA}&per_page=1`]: { link: linkTo(1276) },
    });
    expect(await watch(gh.fetch).find('v1275')).toEqual({ tag: 'v1276', status: 'in_progress', startedAt: MERGED_AT });
    expect(gh.calls).toEqual([
      runsUrl('in_progress'),
      `${API}/actions/runs/38477662219/jobs?filter=latest&per_page=100`,
      `${API}/commits?sha=${SHA}&per_page=1`,
    ]);
    expect(jobsUrl(38477662219)).toBe(gh.calls[1]);
    expect(gh.calls[0]).toBe(
      `${API}/actions/workflows/desktop-pack.yml/runs?branch=master&status=in_progress&exclude_pull_requests=true&per_page=5`,
    );
    const init = gh.fetch.mock.calls[0][1] as { headers: Record<string, string>; signal: AbortSignal };
    expect(init.headers).not.toHaveProperty('Authorization');
    expect(init.signal).toBeInstanceOf(AbortSignal);
    expect(logger.warn).not.toHaveBeenCalled();
  });

  it('skips a docs-only push and names the packing run behind it', async () => {
    const docs = run({ id: 2, event: 'push', head_sha: 'd'.repeat(40), created_at: '2026-10-13T22:27:00Z' });
    const gh = github({
      'status=in_progress': { body: { workflow_runs: [docs, run()] } },
      '/runs/2/jobs': { body: { jobs: [job('Desktop pack', ['ubuntu-latest'])] } },
      '/jobs': { body: packing },
      [`/commits?sha=${SHA}`]: { link: linkTo(1276) },
    });
    expect((await watch(gh.fetch).find('v1275'))?.tag).toBe('v1276');
  });

  it('skips a run whose pack already failed, and says nothing when no other is building', async () => {
    const gh = github({
      'status=in_progress': { body: { workflow_runs: [run()] } },
      '/jobs': { body: { jobs: [job('Desktop pack', ['windows-latest'], red), job('Release checks / Frontend E2E', [])] } },
      'status=queued': { body: { workflow_runs: [] } },
    });
    expect(await watch(gh.fetch).find('v1275')).toBeNull();
    expect(gh.calls.some((url) => url.includes('/commits?'))).toBe(false);
    expect(logger.warn).not.toHaveBeenCalled();
  });

  it('names a human push that packs', async () => {
    const gh = github({
      'status=in_progress': { body: { workflow_runs: [run({ event: 'push' })] } },
      [`/runs/38477662219/jobs`]: { body: { jobs: [job('Desktop pack', ['windows-latest'])] } },
      [`/commits?sha=${SHA}`]: { link: linkTo(1276) },
    });
    expect((await watch(gh.fetch).find('v1275'))?.tag).toBe('v1276');
  });

  it('falls back to a queued run when none is in progress', async () => {
    const gh = github({
      'status=in_progress': { body: { workflow_runs: [] } },
      'status=queued': { body: { workflow_runs: [run({ status: 'queued', run_started_at: undefined })] } },
      '/jobs': { body: { jobs: [] } },
      [`/commits?sha=${SHA}`]: { link: linkTo(1276) },
    });
    expect(await watch(gh.fetch).find('v1275')).toEqual({ tag: 'v1276', status: 'queued', startedAt: MERGED_AT });
  });

  it('says nothing when no run is building, without counting a commit', async () => {
    const gh = github({
      'status=in_progress': { body: { workflow_runs: [] } },
      'status=queued': { body: { workflow_runs: [] } },
    });
    expect(await watch(gh.fetch).find('v1275')).toBeNull();
    expect(gh.calls).toEqual([runsUrl('in_progress'), runsUrl('queued')]);
    expect(logger.warn).not.toHaveBeenCalled();
  });

  it('says nothing for a run of the installed release or an older one', async () => {
    const gh = github({
      'status=in_progress': { body: { workflow_runs: [run({ head_sha: OLD_SHA })] } },
      '/jobs': { body: packing },
      [`/commits?sha=${OLD_SHA}`]: { link: linkTo(1275) },
    });
    expect(await watch(gh.fetch).find('v1275')).toBeNull();
  });

  it.each([
    ['a rate limit', { 'status=in_progress': { status: 403, body: { message: 'API rate limit exceeded' } } }, 'HTTP 403'],
    ['an answer of another shape', { 'status=in_progress': { body: [] } }, 'list of workflow runs'],
    [
      'no commit count',
      { 'status=in_progress': { body: { workflow_runs: [run()] } }, '/jobs': { body: packing }, '/commits?': { link: null } },
      'no commit count for c7dc401d',
    ],
  ])('falls back on %s, with one line in update.log', async (_name, routes, reason) => {
    expect(await watch(github(routes as Record<string, Route>).fetch).find('v1275')).toBeNull();
    expect(logger.warn).toHaveBeenCalledTimes(1);
    expect(logger.warn.mock.calls[0][0]).toContain('could not ask GitHub for a release still being built');
    expect(logger.warn.mock.calls[0][0]).toContain(reason);
  });

  it('falls back when offline', async () => {
    const fetch = vi.fn(async () => {
      throw new Error('net::ERR_INTERNET_DISCONNECTED');
    });
    expect(await watch(fetch).find('v1275')).toBeNull();
    expect(logger.warn.mock.calls[0][0]).toContain('net::ERR_INTERNET_DISCONNECTED');
  });

  it('never waits past its deadline, even on a request that ignores the abort', async () => {
    vi.useFakeTimers();
    const hangs = github({ 'status=in_progress': () => new Promise(() => {}) });
    const found = watch(hangs.fetch).find('v1275');
    await vi.advanceTimersByTimeAsync(RELEASE_BUILD_TIMEOUT_MS);
    expect(await found).toBeNull();
    expect(logger.warn.mock.calls[0][0]).toContain(`no answer within ${RELEASE_BUILD_TIMEOUT_MS} ms`);
    // The requests in flight are aborted at the deadline.
    const init = hangs.fetch.mock.calls[0][1] as { signal: AbortSignal };
    expect(init.signal.aborted).toBe(true);
  });

  it('needs a vNNN installed version', async () => {
    const gh = github({});
    expect(await watch(gh.fetch).find('')).toBeNull();
    expect(gh.calls).toEqual([]);
    expect(logger.warn).toHaveBeenCalledTimes(1);
  });
});

describe("the dialog's words", () => {
  const current = reduceUpdateState(reduceUpdateState(INITIAL_UPDATE_STATE, { type: 'checking' }), { type: 'not-available' });
  const MIN = 60_000;
  const building = (over: Record<string, unknown> = {}) => ({ tag: 'v1276', status: 'in_progress', startedAt: MERGED_AT, ...over });

  it("says today's words exactly when nothing is being built", () => {
    expect(manualCheckResult(current, 'v1275')).toEqual({ type: 'info', message: 'Nova v1275 is the latest release.' });
    expect(manualCheckResult(current, 'v1275', { building: null, now: MERGED_AT })).toEqual({
      type: 'info',
      message: 'Nova v1275 is the latest release.',
    });
  });

  it('names the release being built under the same message (the 22:29 click on 2026-10-13)', () => {
    expect(manualCheckResult(current, 'v1275', { building: building(), now: MERGED_AT + 4 * MIN + 20_000 })).toEqual({
      type: 'info',
      message: 'Nova v1275 is the latest release.',
      detail:
        'v1276 is being built now (started 4 min ago). A build usually takes about 7 minutes; '
        + 'check again in about 3 minutes. It is published only if its checks pass.',
    });
  });

  it('counts the minutes left, and says so when a build runs long', () => {
    expect(buildingDetail(building(), MERGED_AT + 20_000)).toContain('(started less than a minute ago)');
    expect(buildingDetail(building(), MERGED_AT + 20_000)).toContain('check again in about 7 minutes.');
    expect(buildingDetail(building(), MERGED_AT + 6 * MIN)).toContain('check again in about 1 minute.');
    expect(buildingDetail(building(), MERGED_AT + 9 * MIN)).toContain(
      '(started 9 min ago). A build usually takes about 7 minutes; this one is taking longer; check again in a few minutes.',
    );
    // A clock behind GitHub's never reads a negative minute.
    expect(buildingDetail(building(), MERGED_AT - MIN)).toContain('(started less than a minute ago)');
  });

  it('says a queued build has not started', () => {
    expect(buildingDetail(building({ status: 'queued' }), MERGED_AT + MIN)).toBe(
      'v1276 is queued to be built (queued 1 min ago). A build usually takes about 7 minutes once it starts; '
      + 'check again in about 7 minutes. It is published only if its checks pass.',
    );
  });

  it('leaves out a start time GitHub did not give', () => {
    expect(buildingDetail(building({ startedAt: null }), MERGED_AT)).toBe(
      'v1276 is being built now. A build usually takes about 7 minutes; check again in about 7 minutes. '
      + 'It is published only if its checks pass.',
    );
    expect(buildingDetail(null, MERGED_AT)).toBe('');
  });
});
