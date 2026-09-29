import path from 'node:path';
import { describe, expect, it, vi } from 'vitest';
import { createEngineSync, pullMaster } from '../../electron/engineSync.mjs';

const ROOT = 'C:\\Users\\op\\github\\Nova';
const API = 'http://127.0.0.1:8000';

type Reply = { code: number; stdout?: string; stderr?: string };

/** A scripted git: the first matching rule answers each command (by its joined args). */
function gitFake(rules: Array<[RegExp, Reply]>) {
  const calls: string[] = [];
  const git = vi.fn(async (_root: string, args: string[]) => {
    const line = args.join(' ');
    calls.push(line);
    const hit = rules.find(([re]) => re.test(line));
    const reply = hit ? hit[1] : { code: 0, stdout: '' };
    return { code: reply.code, stdout: reply.stdout ?? '', stderr: reply.stderr ?? '' };
  });
  return { git, calls };
}

/** A clean master two commits behind origin/master, going v1025 -> v1027. */
function behindMaster(extra: Array<[RegExp, Reply]> = []) {
  let merged = false;
  const rules: Array<[RegExp, Reply]> = [
    ...extra,
    [/^rev-parse --abbrev-ref HEAD$/, { code: 0, stdout: 'master\n' }],
    [/^status --porcelain/, { code: 0, stdout: '' }],
    [/^fetch/, { code: 0 }],
    [/^rev-list --count HEAD\.\.origin\/master$/, { code: 0, stdout: '2\n' }],
    [/^merge-base --is-ancestor/, { code: 0 }],
    [/^diff --name-only/, { code: 0, stdout: '' }],
  ];
  const fake = gitFake(rules);
  const git = vi.fn(async (root: string, args: string[]) => {
    const line = args.join(' ');
    if (line === 'rev-list --count HEAD') return { code: 0, stdout: merged ? '1027\n' : '1025\n', stderr: '' };
    if (line.startsWith('merge --ff-only')) {
      merged = true;
      return { code: 0, stdout: '', stderr: '' };
    }
    return fake.git(root, args);
  });
  return { git, calls: fake.calls };
}

describe('pullMaster (Pull master and restart)', () => {
  it('fast-forwards a clean master and names both revisions', async () => {
    const { git } = behindMaster();
    expect(await pullMaster(ROOT, git)).toEqual({ ok: true, pulled: true, from: 'v1025', to: 'v1027', reason: null });
  });

  it('never touches a checkout that is not a clean master', async () => {
    const branch = gitFake([[/^rev-parse --abbrev-ref HEAD$/, { code: 0, stdout: 'feature/x\n' }]]);
    expect((await pullMaster(ROOT, branch.git)).reason).toBe('the checkout is on feature/x, not master');
    const dirty = gitFake([
      [/^rev-parse --abbrev-ref HEAD$/, { code: 0, stdout: 'master\n' }],
      [/^status --porcelain/, { code: 0, stdout: ' M frontend/electron/sidecar.mjs\n M backend/main.py\n' }],
    ]);
    const out = await pullMaster(ROOT, dirty.git);
    expect(out.ok).toBe(false);
    expect(out.reason).toBe('the checkout has 2 changed files nobody committed');
    expect(dirty.calls.some((c) => c.startsWith('fetch') || c.startsWith('merge'))).toBe(false);
  });

  it('refuses a checkout that has diverged from master', async () => {
    const { git, calls } = behindMaster([[/^merge-base --is-ancestor/, { code: 1 }]]);
    expect((await pullMaster(ROOT, git)).reason).toBe('the checkout has commits master does not have');
    expect(calls.some((c) => c.startsWith('merge --ff-only'))).toBe(false);
  });

  it('holds a pull that changes the backend packages: a restart would fail without them', async () => {
    const { git } = behindMaster([[/^diff --name-only/, { code: 0, stdout: 'backend/requirements.txt\n' }]]);
    const out = await pullMaster(ROOT, git);
    expect(out.ok).toBe(false);
    expect(out.reason).toMatch(/^master changes backend\/requirements.txt: install the new packages first/);
  });

  it('says so when master has nothing newer, and when fetch fails', async () => {
    const { git } = behindMaster([[/^rev-list --count HEAD\.\.origin\/master$/, { code: 0, stdout: '0\n' }]]);
    expect(await pullMaster(ROOT, git)).toEqual({ ok: true, pulled: false, from: 'v1025', to: 'v1025', reason: null });
    const offline = behindMaster([[/^fetch/, { code: 128, stderr: 'fatal: unable to access github.com\n' }]]);
    expect((await pullMaster(ROOT, offline.git)).reason).toBe('git fetch failed: fatal: unable to access github.com');
  });
});

describe('createEngineSync', () => {
  const onDisk = new Set([
    path.win32.join(ROOT, '.env'),
    path.win32.join(ROOT, 'scripts', 'Start-NovaApi.ps1'),
  ]);
  const fsDeps = { exists: (p: string) => onDisk.has(p), isDir: (p: string) => p === path.win32.join(ROOT, '.git') };
  const health = (tag: string) => ({ status: 'ok', frozen: false, repo_root: ROOT, release_tag: tag, checkout_tag: tag });

  function sync(over: Record<string, unknown> = {}) {
    const views: Array<Record<string, unknown>> = [];
    const written: string[] = [];
    const s = createEngineSync({
      apiBase: API,
      userData: 'C:\\ud',
      reloadEngine: vi.fn(async () => ({ from: 'v1025', to: 'v1027' })),
      publish: (v: Record<string, unknown>) => views.push(v),
      logger: { info: vi.fn(), warn: vi.fn() },
      fetchJson: async (url: string) => (url.endsWith('/api/health') ? health('v1025') : null),
      fsDeps,
      now: () => 1_000,
      // Never the real disk: the owner file lives in memory here.
      readOwner: () => null,
      writeOwner: (_userData: string, root: string) => {
        written.push(root);
        return true;
      },
      ...over,
    });
    return { s, views, written };
  }

  it('pulls, then restarts the backend onto the new code', async () => {
    const reloadEngine = vi.fn(async () => ({ from: 'v1025', to: 'v1027' }));
    const { git } = behindMaster();
    const { s, views, written } = sync({ git, reloadEngine });
    await s.syncNow();
    expect(reloadEngine).toHaveBeenCalledTimes(1);
    const last = views[views.length - 1];
    expect(last.running).toBeNull();
    expect(last.last).toMatchObject({ outcome: 'restarted', text: 'Restarted the backend: v1025 -> v1027' });
    expect(last.owner).toBe(ROOT);
    expect(last.attached_to_owner).toBe(true);
    expect(written).toEqual([ROOT]);
  });

  it('does not restart when the pull brought nothing newer', async () => {
    const reloadEngine = vi.fn();
    const { git } = behindMaster([[/^rev-list --count HEAD\.\.origin\/master$/, { code: 0, stdout: '0\n' }]]);
    const { s, views } = sync({ git, reloadEngine });
    await s.syncNow();
    expect(reloadEngine).not.toHaveBeenCalled();
    expect((views[views.length - 1].last as { outcome: string }).outcome).toBe('current');
  });

  it('never pulls for a backend that is not running from the checkout', async () => {
    const reloadEngine = vi.fn();
    const packaged = { status: 'ok', frozen: true, release_tag: 'v1025' };
    const { git, calls } = behindMaster();
    const { s, views } = sync({ git, reloadEngine, fetchJson: async () => packaged });
    await s.syncNow();
    expect(calls).toEqual([]);
    expect(reloadEngine).not.toHaveBeenCalled();
    expect((views[views.length - 1].last as { outcome: string }).outcome).toBe('failed');
  });

  it('says why a refused pull was refused', async () => {
    const dirty = gitFake([
      [/^rev-parse --abbrev-ref HEAD$/, { code: 0, stdout: 'master\n' }],
      [/^status --porcelain/, { code: 0, stdout: ' M x\n' }],
    ]);
    const { s, views } = sync({ git: dirty.git });
    await s.syncNow();
    expect(views[views.length - 1].last).toMatchObject({
      outcome: 'failed',
      text: 'Not pulled: the checkout has 1 changed file nobody committed',
    });
  });
});
