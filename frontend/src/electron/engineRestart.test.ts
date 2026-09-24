import path from 'node:path';
import { describe, expect, it, vi } from 'vitest';
import {
  engineCheckout,
  engineIdentity,
  engineScripts,
  engineStartCommandLine,
  isNewEngine,
  restartCheckoutEngine,
  watchdogRunning,
} from '../../electron/engineRestart.mjs';

const API = 'http://127.0.0.1:8000';
const ROOT = 'C:\\Users\\op\\github\\Nova';
const STOP = path.win32.join(ROOT, 'scripts', 'Stop-NovaPorts.ps1');
const START = path.win32.join(ROOT, 'scripts', 'Start-NovaApi.ps1');
const OLD = { instance_id: 'old', pid: 100, release_tag: 'v991' };

/** A fake /api/health + /api/diagnostics: health answers the queued engines in turn. */
function engineFake(health: Array<object | null>, diagnostics: object | null = { process: { repo_root: ROOT, release_tag: 'v991' } }) {
  const queue = [...health];
  return vi.fn(async (url: string) => {
    if (url.endsWith('/api/diagnostics')) return diagnostics;
    return queue.length > 1 ? queue.shift() : queue[0];
  });
}

/** spawnSync fake: the watchdog query answers `watchdogCount`, the stop script `stopOut`. */
function runFake(watchdogCount: number, stopOut = 'Nova: taskkill PID 100 succeeded (exit 0)') {
  return vi.fn((_exe: string, args: string[]) =>
    args.includes('-EncodedCommand') ? { stdout: `${watchdogCount}\r\n` } : { stdout: stopOut });
}

function deps(over: Record<string, unknown>) {
  let t = 0;
  return {
    apiBase: API,
    port: 8000,
    platform: 'win32',
    exists: (p: string) => p === STOP || p === START,
    env: { SystemRoot: 'C:\\Windows' },
    waitForPortFree: async () => true,
    spawnFn: vi.fn(() => ({ on: vi.fn(), unref: vi.fn() })),
    sleep: async () => { t += 1_000; },
    now: () => t,
    timeoutMs: 10_000,
    ...over,
  };
}

describe('engineRestart', () => {
  it('reads who answers, and says nothing it was not told', async () => {
    const full = await engineIdentity(API, async () => ({ status: 'ok', instance_id: 'abc', pid: 7, release_tag: 'v1007' }));
    expect(full).toEqual({ instance_id: 'abc', pid: 7, release_tag: 'v1007' });
    const older = await engineIdentity(API, async () => ({ status: 'ok' }));
    expect(older).toEqual({ instance_id: null, pid: null, release_tag: null });
    expect(await engineIdentity(API, async () => null)).toBeNull();
    expect(await engineIdentity(API, async () => ({ detail: 'Not Found' }))).toBeNull();
  });

  it('takes the checkout from the engine, never from a packaged one', async () => {
    expect(await engineCheckout(API, async () => ({ process: { repo_root: ROOT, release_tag: 'v991' } })))
      .toEqual({ root: ROOT, release_tag: 'v991' });
    expect(await engineCheckout(API, async () => ({ process: { repo_root: 'C:\\x\\_MEI', frozen: true } })))
      .toEqual({ root: null, release_tag: null });
    expect(await engineCheckout(API, async () => null)).toBeNull();
  });

  it('counts a reload only when a different process answers', () => {
    expect(isNewEngine(OLD, { instance_id: 'new', pid: 100, release_tag: 'v1007' })).toBe(true);
    expect(isNewEngine(OLD, { ...OLD })).toBe(false);
    expect(isNewEngine({ instance_id: null, pid: 100, release_tag: null }, { instance_id: null, pid: 200, release_tag: null })).toBe(true);
    expect(isNewEngine(OLD, null)).toBe(false);
  });

  it("finds the engine's own checkout first, then this app's", () => {
    const own = 'C:\\Program Files\\Nova\\resources';
    expect(engineScripts([ROOT, own], p => p === STOP || p === START))
      .toEqual({ root: ROOT, stop: STOP, start: START, backendDir: path.win32.join(ROOT, 'backend') });
    const ownStop = path.win32.join(own, 'scripts', 'Stop-NovaPorts.ps1');
    expect(engineScripts([null, own], p => p === ownStop)?.start).toBeNull();
    expect(engineScripts([ROOT, own], () => false)).toBeNull();
  });

  it('starts the engine the way Run Nova.bat does, and refuses a path cmd would rewrite', () => {
    const line = engineStartCommandLine('C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe', `${ROOT}\\backend`, START);
    expect(line).toBe(
      `/d /s /c "start "Nova API" /min /D ${ROOT}\\backend C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe `
      + `-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File ${START}"`,
    );
    expect(engineStartCommandLine('powershell.exe', 'C:\\My Nova\\backend', 'C:\\My Nova\\scripts\\Start-NovaApi.ps1'))
      .toContain('/D "C:\\My Nova\\backend"');
    expect(engineStartCommandLine('powershell.exe', 'C:\\100%\\backend', START)).toBeNull();
  });

  it('asks Windows whether the watchdog runs, and reads a failed question as no', () => {
    expect(watchdogRunning({ run: runFake(1) as never, env: {} })).toBe(true);
    expect(watchdogRunning({ run: runFake(0) as never, env: {} })).toBe(false);
    expect(watchdogRunning({ run: (() => { throw new Error('no powershell'); }) as never, env: {} })).toBe(false);
  });

  it('with the watchdog running: stops the engine, starts nothing, and waits for the new one', async () => {
    const run = runFake(1);
    const d = deps({ run, fetchJson: engineFake([OLD, null, { status: 'ok', instance_id: 'new', pid: 300, release_tag: 'v1007' }]) });
    await expect(restartCheckoutEngine(OLD, d)).resolves.toEqual({ from: 'v991', to: 'v1007' });
    const stopCall = run.mock.calls.find(([, args]) => args.includes('-File'));
    expect(stopCall?.[1]).toEqual(['-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', STOP, '-Ports', '8000']);
    expect(d.spawnFn).not.toHaveBeenCalled();
  });

  it('with no watchdog: starts the checkout engine itself, outside this app', async () => {
    const d = deps({ run: runFake(0), fetchJson: engineFake([{ status: 'ok', instance_id: 'new', pid: 300, release_tag: 'v1007' }]) });
    await expect(restartCheckoutEngine(OLD, d)).resolves.toEqual({ from: 'v991', to: 'v1007' });
    expect(d.spawnFn).toHaveBeenCalledTimes(1);
    const [exe, [line], opts] = (d.spawnFn as ReturnType<typeof vi.fn>).mock.calls[0] as [string, string[], Record<string, unknown>];
    expect(exe).toBe('C:\\Windows\\System32\\cmd.exe');
    expect(line).toContain(`-File ${START}`);
    expect(opts).toMatchObject({ detached: true, windowsVerbatimArguments: true, cwd: path.win32.join(ROOT, 'backend') });
  });

  it('never claims a reload it did not make', async () => {
    // No stop script anywhere: nothing is stopped.
    const noScript = deps({ run: runFake(1), exists: () => false, fetchJson: engineFake([OLD]) });
    await expect(restartCheckoutEngine(OLD, noScript)).rejects.toThrow(/^Not restarted: backend v991 was started outside Nova/);
    // The stop script left it running: say what it said.
    const held = deps({
      run: runFake(1, 'Nova: port 8000 is held by PID 5 (python), which does not look like a Nova process -- leaving it alone.'),
      waitForPortFree: async () => false,
      fetchJson: engineFake([OLD]),
    });
    await expect(restartCheckoutEngine(OLD, held)).rejects.toThrow(/^Not restarted: backend v991 is still running -- Nova: port 8000 is held/);
    // Stopped, but nothing new answered in time.
    const gone = deps({ run: runFake(1), fetchJson: engineFake([null]) });
    await expect(restartCheckoutEngine(OLD, gone)).rejects.toThrow(/^Stopped backend v991; no backend answered within 10 s/);
    // The same process still answering is not a reload.
    const same = deps({ run: runFake(1), fetchJson: engineFake([OLD]) });
    await expect(restartCheckoutEngine(OLD, same)).rejects.toThrow(/no backend answered/);
  });

  it('off Windows it says so instead of guessing', async () => {
    await expect(restartCheckoutEngine(OLD, deps({ platform: 'linux', fetchJson: engineFake([OLD]) })))
      .rejects.toThrow(/^Not restarted: backend v991 was started outside Nova; restart it where it runs/);
  });
});
