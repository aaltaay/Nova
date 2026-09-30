import path from 'node:path';
import { describe, expect, it, vi } from 'vitest';
import { createEngineSync, syncToRelease } from '../../electron/engineSync.mjs';

const ROOT = 'C:\\Users\\op\\github\\Nova';
const API = 'http://127.0.0.1:8000';
const SHA = 'abc123';

type Reply = { code: number; stdout?: string; stderr?: string };

/**
 * A clean master at v1025, with release v1029 (commit SHA) on origin/master: the first matching
 * rule in `extra` answers a command (by its joined args), then the defaults; a merge moves HEAD.
 */
function releaseGit(extra: Array<[RegExp, Reply]> = [], start = '1025') {
  let head = start;
  const calls: string[] = [];
  const rules: Array<[RegExp, Reply]> = [
    ...extra,
    [/^rev-parse --abbrev-ref HEAD$/, { code: 0, stdout: 'master\n' }],
    [/^status --porcelain/, { code: 0, stdout: '' }],
    [/^fetch --quiet origin master \+refs\/tags\/v1029:refs\/tags\/v1029$/, { code: 0 }],
    [/^rev-parse --verify --quiet v1029\^\{commit\}$/, { code: 0, stdout: `${SHA}\n` }],
    [new RegExp(`^merge-base --is-ancestor ${SHA} origin/master$`), { code: 0 }],
    [new RegExp(`^merge-base --is-ancestor ${SHA} HEAD$`), { code: 1 }],
    [new RegExp(`^merge-base --is-ancestor HEAD ${SHA}$`), { code: 0 }],
    [/^diff --name-only/, { code: 0, stdout: '' }],
  ];
  const git = vi.fn(async (_root: string, args: string[]) => {
    const line = args.join(' ');
    calls.push(line);
    if (line === 'rev-list --count HEAD') return { code: 0, stdout: `${head}\n`, stderr: '' };
    if (line === `merge --ff-only --quiet ${SHA}`) {
      head = '1029';
      return { code: 0, stdout: '', stderr: '' };
    }
    const hit = rules.find(([re]) => re.test(line));
    const reply = hit ? hit[1] : { code: 0, stdout: '' };
    return { code: reply.code, stdout: reply.stdout ?? '', stderr: reply.stderr ?? '' };
  });
  return { git, calls };
}

describe('syncToRelease (the backend follows the desk, one version)', () => {
  it("fast-forwards a clean master to the desk's release, never to master's newest commit", async () => {
    const { git, calls } = releaseGit();
    expect(await syncToRelease(ROOT, 'v1029', git)).toEqual({ ok: true, pulled: true, from: 'v1025', to: 'v1029', reason: null });
    expect(calls).toContain(`merge --ff-only --quiet ${SHA}`);
    expect(calls.some((c) => c.includes('merge --ff-only --quiet origin/master'))).toBe(false);
  });

  it('leaves a checkout already at the release, or past it, where it is (master never moves back)', async () => {
    const at = releaseGit([[new RegExp(`^merge-base --is-ancestor ${SHA} HEAD$`), { code: 0 }]], '1029');
    expect(await syncToRelease(ROOT, 'v1029', at.git)).toEqual({ ok: true, pulled: false, from: 'v1029', to: 'v1029', reason: null });
    const past = releaseGit([[new RegExp(`^merge-base --is-ancestor ${SHA} HEAD$`), { code: 0 }]], '1031');
    expect(await syncToRelease(ROOT, 'v1029', past.git)).toMatchObject({ ok: true, pulled: false, to: 'v1031' });
    expect(past.calls.some((c) => c.startsWith('merge --ff-only'))).toBe(false);
  });

  it('never touches a checkout that is not a clean master', async () => {
    const branch = releaseGit([[/^rev-parse --abbrev-ref HEAD$/, { code: 0, stdout: 'feature/x\n' }]]);
    expect((await syncToRelease(ROOT, 'v1029', branch.git)).reason).toBe('the checkout is on feature/x, not master');
    const dirty = releaseGit([[/^status --porcelain/, { code: 0, stdout: ' M frontend/electron/sidecar.mjs\n M backend/main.py\n' }]]);
    const out = await syncToRelease(ROOT, 'v1029', dirty.git);
    expect(out.reason).toBe('the checkout has 2 changed files nobody committed');
    expect(dirty.calls.some((c) => c.startsWith('fetch') || c.startsWith('merge'))).toBe(false);
  });

  it('refuses a diverged checkout, a missing tag and a tag that is not on master', async () => {
    const diverged = releaseGit([[new RegExp(`^merge-base --is-ancestor HEAD ${SHA}$`), { code: 1 }]]);
    expect((await syncToRelease(ROOT, 'v1029', diverged.git)).reason).toBe('the checkout has commits master does not have');
    const missing = releaseGit([[/^rev-parse --verify/, { code: 1 }]]);
    expect((await syncToRelease(ROOT, 'v1029', missing.git)).reason).toBe('GitHub has no v1029 tag');
    const stray = releaseGit([[new RegExp(`^merge-base --is-ancestor ${SHA} origin/master$`), { code: 1 }]]);
    expect((await syncToRelease(ROOT, 'v1029', stray.git)).reason).toBe('v1029 is not a commit on master');
    expect((await syncToRelease(ROOT, 'dev', releaseGit().git)).reason).toBe('the desk does not know its own version');
  });

  it('holds a release that changes the backend packages: a restart would fail without them', async () => {
    const { git } = releaseGit([[/^diff --name-only/, { code: 0, stdout: 'backend/requirements.txt\n' }]]);
    expect((await syncToRelease(ROOT, 'v1029', git)).reason)
      .toMatch(/^v1029 changes backend\/requirements.txt: install the new packages first/);
    const offline = releaseGit([[/^fetch/, { code: 128, stderr: 'fatal: unable to access github.com\n' }]]);
    expect((await syncToRelease(ROOT, 'v1029', offline.git)).reason).toBe('git fetch failed: fatal: unable to access github.com');
  });
});

describe('createEngineSync', () => {
  const onDisk = new Set([
    path.win32.join(ROOT, '.env'),
    path.win32.join(ROOT, 'scripts', 'Start-NovaApi.ps1'),
  ]);
  const fsDeps = { exists: (p: string) => onDisk.has(p), isDir: (p: string) => p === path.win32.join(ROOT, '.git') };
  const health = (tag: string) => ({ status: 'ok', frozen: false, repo_root: ROOT, release_tag: tag, checkout_tag: tag });
  const nothingOpen = { schema_version: 1, safe: true, open: [], unknown: [] };

  function answers(tag: string, check: unknown = nothingOpen) {
    return async (url: string) => (url.endsWith('/api/health') ? health(tag) : url.endsWith('/restart-check') ? check : null);
  }

  function sync(over: Record<string, unknown> = {}) {
    const views: Array<Record<string, unknown>> = [];
    const written: string[] = [];
    const follows: unknown[] = [];
    const s = createEngineSync({
      apiBase: API,
      userData: 'C:\\ud',
      deskTag: () => 'v1029',
      reloadEngine: vi.fn(async () => ({ from: 'v1025', to: 'v1029' })),
      publish: (v: Record<string, unknown>) => views.push(v),
      logger: { info: vi.fn(), warn: vi.fn() },
      fetchJson: answers('v1025'),
      fsDeps,
      now: () => 1_000,
      // Never the real disk: the owner file and the promise live in memory here.
      readOwner: () => null,
      writeOwner: (_userData: string, root: string) => {
        written.push(root);
        return true;
      },
      writeFollow: (_userData: string, body: unknown) => {
        follows.push(body);
        return true;
      },
      takeFollow: () => null,
      ...over,
    });
    const lastView = () => views[views.length - 1] as { running: unknown; last: { outcome: string; text: string } };
    return { s, views, written, follows, lastView };
  }

  it("brings the checkout to the desk's release, then restarts the backend onto it", async () => {
    const reloadEngine = vi.fn(async () => ({ from: 'v1025', to: 'v1029' }));
    const { git } = releaseGit();
    const { s, views, written, lastView } = sync({ git, reloadEngine });
    await s.syncNow();
    expect(reloadEngine).toHaveBeenCalledTimes(1);
    expect(lastView().running).toBeNull();
    expect(lastView().last).toMatchObject({ outcome: 'restarted', text: 'Restarted the backend: v1025 -> v1029' });
    expect(views.some((v) => (v.last as { outcome?: string } | null)?.outcome === 'pulled')).toBe(true);
    expect(written).toEqual([ROOT]);
  });

  it('restarts without pulling when the checkout already holds the release (no restart-then-pull)', async () => {
    const reloadEngine = vi.fn(async () => ({ from: 'v1025', to: 'v1029' }));
    const { git, calls } = releaseGit([[new RegExp(`^merge-base --is-ancestor ${SHA} HEAD$`), { code: 0 }]], '1029');
    const { s, lastView } = sync({ git, reloadEngine });
    await s.syncNow();
    expect(calls.some((c) => c.startsWith('merge --ff-only'))).toBe(false);
    expect(reloadEngine).toHaveBeenCalledTimes(1);
    expect(lastView().last.outcome).toBe('restarted');
  });

  it('does not restart a backend that already runs what its checkout holds', async () => {
    const reloadEngine = vi.fn();
    const { git } = releaseGit([[new RegExp(`^merge-base --is-ancestor ${SHA} HEAD$`), { code: 0 }]], '1029');
    const { s, lastView } = sync({ git, reloadEngine, fetchJson: answers('v1029') });
    await s.syncNow();
    expect(reloadEngine).not.toHaveBeenCalled();
    expect(lastView().last).toMatchObject({ outcome: 'current', text: 'The backend already runs v1029' });
  });

  it('never touches a backend that is not running from the checkout', async () => {
    const reloadEngine = vi.fn();
    const packaged = { status: 'ok', frozen: true, release_tag: 'v1025' };
    const { git, calls } = releaseGit();
    const { s, lastView } = sync({ git, reloadEngine, fetchJson: async () => packaged });
    await s.syncNow();
    expect(calls).toEqual([]);
    expect(reloadEngine).not.toHaveBeenCalled();
    expect(lastView().last.outcome).toBe('failed');
  });

  it('says why a refused update was refused', async () => {
    const { git } = releaseGit([[/^status --porcelain/, { code: 0, stdout: ' M x\n' }]]);
    const { s, lastView } = sync({ git });
    await s.syncNow();
    expect(lastView().last).toMatchObject({ outcome: 'failed', text: 'Not updated: the checkout has 1 changed file nobody committed' });
  });

  describe('Restart to update carries the backend (one update for both)', () => {
    it('with nothing open: brings the checkout along and leaves the new desk its promise, asking nothing', async () => {
      const box = vi.fn();
      const { git, calls } = releaseGit();
      const { s, follows } = sync({ git });
      expect(await s.prepareForDesk('v1029', { box })).toBe(true);
      expect(box).not.toHaveBeenCalled();
      expect(calls).toContain(`merge --ff-only --quiet ${SHA}`);
      expect(follows).toEqual([{ tag: 'v1029', repoRoot: ROOT, now: 1_000 }]);
    });

    it('lists what is open first, and installs nothing when the operator waits', async () => {
      const box = vi.fn(async () => ({ response: 1 }));
      const check = { schema_version: 1, safe: false, unknown: [], open: [{ kind: 'recording', text: 'Recording MSGY' }] };
      const { git, calls } = releaseGit();
      const { s, follows } = sync({ git, fetchJson: answers('v1025', check) });
      expect(await s.prepareForDesk('v1029', { box })).toBe(false);
      const asked = (box.mock.calls[0] as unknown as [{ message: string; detail: string }])[0];
      expect(asked.message).toBe('Updating to v1029 restarts the backend too.');
      expect(asked.detail).toContain('- Recording MSGY');
      expect(calls.some((c) => c.startsWith('fetch'))).toBe(false);
      expect(follows).toEqual([]);
    });

    it('asks before updating the desk alone when the backend cannot come along', async () => {
      const { git } = releaseGit([[/^status --porcelain/, { code: 0, stdout: ' M x\n' }]]);
      const wait = sync({ git });
      expect(await wait.s.prepareForDesk('v1029', { box: vi.fn(async () => ({ response: 0 })) })).toBe(false);
      const alone = sync({ git });
      const box = vi.fn(async () => ({ response: 1 }));
      expect(await alone.s.prepareForDesk('v1029', { box })).toBe(true);
      expect((box.mock.calls[0] as unknown as [{ message: string }])[0].message).toBe('The backend cannot be updated to v1029.');
      expect(alone.follows).toEqual([]);
    });

    it('leaves a bundled backend to the installer', async () => {
      const packaged = { status: 'ok', frozen: true, release_tag: 'v1025' };
      const { git, calls } = releaseGit();
      const { s } = sync({ git, fetchJson: async () => packaged });
      expect(await s.prepareForDesk('v1029', { box: vi.fn() })).toBe(true);
      expect(calls).toEqual([]);
    });

    it('the new desk keeps the promise: it restarts the backend onto its release without asking', async () => {
      const reloadEngine = vi.fn(async () => ({ from: 'v1025', to: 'v1029' }));
      const { git } = releaseGit([[new RegExp(`^merge-base --is-ancestor ${SHA} HEAD$`), { code: 0 }]], '1029');
      const { s, lastView } = sync({
        git,
        reloadEngine,
        takeFollow: () => ({ tag: 'v1029', repo_root: ROOT, asked_at: 900 }),
      });
      await s.followIfAsked();
      expect(reloadEngine).toHaveBeenCalledTimes(1);
      expect(lastView().last.outcome).toBe('restarted');
    });

    it('a promise for another release, or none, restarts nothing', async () => {
      const reloadEngine = vi.fn();
      const other = sync({ reloadEngine, takeFollow: () => ({ tag: 'v1028', repo_root: ROOT, asked_at: 900 }) });
      await other.s.followIfAsked();
      const none = sync({ reloadEngine });
      await none.s.followIfAsked();
      expect(reloadEngine).not.toHaveBeenCalled();
    });
  });
});
