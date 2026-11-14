import os from 'node:os';
import path from 'node:path';
import { describe, expect, it, vi } from 'vitest';
import {
  PHONE_PAGE_RETRY_MS,
  PHONE_PAGE_START_GRACE_MS,
  createPhonePageKeeper,
  phonePageKeeperOn,
  runTool,
  startPageServer,
} from '../../electron/phonePageKeeper.mjs';

const ROOT = 'C:\\Users\\op\\github\\Nova';
const PY = 'C:\\Python313\\python.exe';

type Reply = { code: number; stdout?: string; stderr?: string };

/** A keeper on fakes: `check` answers phone_page.py check, `update` its update; the clock is `t.now`. */
function keeper({ check = { code: 0 } as Reply, update = { code: 0 } as Reply, served = true, root = ROOT as string | null,
  busy = false, python = PY as string | null, rev = 'v1538' } = {}) {
  const t = { now: 1_000_000, check, update, served, busy, rev };
  const run = vi.fn(async (_py: string, _root: string, args: string[], _opts: { low?: boolean }) => {
    held.push(`${args[1]}:${holding ? 'held' : 'free'}`);
    const reply = args[1] === 'check' ? t.check : t.update;
    return { code: reply.code, stdout: reply.stdout ?? '', stderr: reply.stderr ?? '' };
  });
  const start = vi.fn();
  const publish = vi.fn();
  const logger = { info: vi.fn(), warn: vi.fn() };
  const held: string[] = [];
  let holding = false;
  const k = createPhonePageKeeper({
    root: () => root,
    busy: () => t.busy,
    lock: async (fn: () => Promise<void>) => {
      holding = true;
      try {
        await fn();
      } finally {
        holding = false;
      }
    },
    revision: async () => t.rev,
    publish,
    logger,
    python: () => python,
    run,
    probe: async () => t.served,
    start,
    exists: () => true,
    now: () => t.now,
  });
  const actions = () => run.mock.calls.map((c) => c[2][1]);
  return { k, t, run, start, publish, logger, actions, held };
}

describe('the desk keeps the phone page built', () => {
  it('leaves a current, served page alone', async () => {
    const { k, start, actions } = keeper();
    await k.tick();
    expect(actions()).toEqual(['check']);
    expect(start).not.toHaveBeenCalled();
    expect(k.view()).toMatchObject({ root: ROOT, build: 'current', served: true, last: null });
  });

  it('rebuilds a page that is behind its checkout, below normal priority, and says so', async () => {
    const { k, run, logger, actions } = keeper({ check: { code: 1 } });
    await k.tick();
    expect(actions()).toEqual(['check', 'update']);
    expect(run.mock.calls[1][3]).toMatchObject({ low: true });
    expect(run.mock.calls[1][2]).toEqual([path.join(ROOT, 'tools', 'phone_page.py'), 'update', '--frontend', path.join(ROOT, 'frontend')]);
    expect(k.view()).toMatchObject({ build: 'current', last: { outcome: 'built' } });
    expect(k.view()?.last?.text).toContain('v1538');
    expect(logger.info).toHaveBeenCalledWith(expect.stringContaining('phone page: Rebuilt'));
  });

  it('keeps the old page after a failed build, and tries again after 30 minutes or when the checkout moves', async () => {
    const { k, t, actions } = keeper({ check: { code: 1 }, update: { code: 1, stderr: 'npm install failed' } });
    await k.tick();
    expect(k.view()).toMatchObject({ build: 'failed', last: { outcome: 'failed' } });
    expect(k.view()?.last?.text).toContain('npm install failed');
    await k.tick();
    expect(actions().filter((a) => a === 'update')).toHaveLength(1);
    t.now += PHONE_PAGE_RETRY_MS;
    await k.tick();
    expect(actions().filter((a) => a === 'update')).toHaveLength(2);
    t.rev = 'v1539';
    await k.tick();
    expect(actions().filter((a) => a === 'update')).toHaveLength(3);
  });

  it("checks and builds holding the backend's checkout lock, so no pull starts under a build", async () => {
    const { k, held } = keeper({ check: { code: 1 } });
    await k.tick();
    expect(held).toEqual(['check:held', 'update:held']);
  });

  it('never builds while the desk pulls or restarts the backend, but still keeps the server', async () => {
    const { k, start, actions } = keeper({ check: { code: 1 }, busy: true, served: false });
    await k.tick();
    expect(actions()).toEqual([]);
    expect(start).toHaveBeenCalledTimes(1);
  });

  it('says it cannot tell, rather than building, when the check itself breaks', async () => {
    const { k, actions } = keeper({ check: { code: 2, stderr: 'Traceback' } });
    await k.tick();
    expect(actions()).toEqual(['check']);
    expect(k.view()).toMatchObject({ build: null, last: { outcome: 'failed' } });
  });
});

describe('the desk keeps the phone page served', () => {
  it('starts the server when nothing answers, once per minute, and says when a start did not come up', async () => {
    const { k, t, start } = keeper({ served: false });
    await k.tick();
    expect(start).toHaveBeenCalledWith(PY, ROOT);
    expect(k.view()).toMatchObject({ served: false, last: { outcome: 'started' } });
    t.now += PHONE_PAGE_START_GRACE_MS / 2;
    await k.tick();
    expect(start).toHaveBeenCalledTimes(1);
    t.now += PHONE_PAGE_START_GRACE_MS;
    await k.tick();
    expect(start).toHaveBeenCalledTimes(2);
    expect(k.view()).toMatchObject({ served: false, last: { outcome: 'failed' } });
    t.served = true;
    await k.tick();
    expect(k.view()).toMatchObject({ served: true });
  });

  it('does nothing without a checkout, and says so without Python', async () => {
    const none = keeper({ root: null, served: false });
    await none.k.tick();
    expect(none.run).not.toHaveBeenCalled();
    expect(none.start).not.toHaveBeenCalled();
    expect(none.k.view()).toMatchObject({ root: null, build: null, served: null });

    const noPy = keeper({ python: null, served: false });
    await noPy.k.tick();
    expect(noPy.start).not.toHaveBeenCalled();
    expect(noPy.k.view()).toMatchObject({ served: false, last: { outcome: 'failed' } });
    expect(noPy.k.view()?.last?.text).toContain('Python');
  });
});

describe('how the keeper runs things', () => {
  it('starts the server with no window, in a process of its own', () => {
    const child = { on: vi.fn(), unref: vi.fn() };
    const spawnFn = vi.fn(() => child);
    startPageServer(PY, ROOT, { spawnFn });
    const [exe, args, opts] = spawnFn.mock.calls[0] as unknown as [string, string[], Record<string, unknown>];
    expect(exe).toBe(PY);
    expect(args[0]).toMatch(/serve_phone_page\.py$/);
    expect(opts).toMatchObject({ cwd: ROOT, detached: true, stdio: 'ignore', windowsHide: true });
    expect(child.unref).toHaveBeenCalled();
  });

  it('runs a build below normal priority, hidden', async () => {
    const setPriority = vi.fn();
    const execFileFn = vi.fn((_f: string, _a: string[], opts: Record<string, unknown>, cb: (e: null, o: string, s: string) => void) => {
      expect(opts).toMatchObject({ cwd: ROOT, windowsHide: true });
      setTimeout(() => cb(null, 'built', ''), 0);
      return { pid: 4242 };
    });
    const out = await runTool(PY, ROOT, ['x'], { timeoutMs: 1000, low: true, execFileFn, setPriority });
    expect(out).toEqual({ code: 0, stdout: 'built', stderr: '' });
    expect(setPriority).toHaveBeenCalledWith(4242, os.constants.priority.PRIORITY_BELOW_NORMAL);
  });

  it('is on unless NOVA_PHONE_PAGE is 0', () => {
    expect(phonePageKeeperOn({})).toBe(true);
    expect(phonePageKeeperOn({ NOVA_PHONE_PAGE: '1' })).toBe(true);
    expect(phonePageKeeperOn({ NOVA_PHONE_PAGE: '0' })).toBe(false);
  });
});
