/**
 * The desk must never install an update by itself (#347). These cover the glue
 * around updatePolicy.mjs: what electron-updater is configured to do, and what
 * happens on Restart, on Later, and when the local engine will not stop.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

type FakeUpdater = { autoInstallOnAppQuit: boolean; checkForUpdates: ReturnType<typeof vi.fn> };

const h = vi.hoisted(() => ({
  boxes: [] as { buttons?: string[]; message?: string }[],
  responses: [] as number[],
  installs: [] as unknown[][],
  updater: null as FakeUpdater | null,
}));

vi.mock('electron', () => ({
  app: { isPackaged: true, getVersion: () => '0.1.831' },
  dialog: {
    showMessageBox: vi.fn(async (...args: unknown[]) => {
      h.boxes.push(args[args.length - 1] as { buttons?: string[]; message?: string });
      return { response: h.responses.shift() ?? 1 };
    }),
  },
  Menu: { buildFromTemplate: (t: unknown) => t, setApplicationMenu: () => {} },
}));

vi.mock('electron-updater', async () => {
  const { EventEmitter } = await import('node:events');
  class NsisUpdater extends EventEmitter {
    logger: unknown;
    autoDownload = true;
    autoInstallOnAppQuit = true;
    checkForUpdates = vi.fn(async () => {
      this.emit('checking-for-update');
      this.emit('update-available', { version: '0.1.832' });
      this.emit('download-progress', { percent: 50 });
      this.emit('update-downloaded', { version: '0.1.832' });
      return { downloadPromise: Promise.resolve([]) };
    });
    quitAndInstall = vi.fn((...args: unknown[]) => h.installs.push(args));
    constructor() {
      super();
      h.updater = this;
    }
  }
  return { NsisUpdater };
});

const realPlatform = process.platform;
const win = { isDestroyed: () => false, setProgressBar: vi.fn(), flashFrame: vi.fn() };

async function startAndCheck(deps: Record<string, unknown> = {}) {
  const { startAutoUpdate } = await import('../../electron/autoUpdate.mjs');
  const stopEngine = vi.fn(async () => true);
  const restartEngine = vi.fn(async () => {});
  await startAutoUpdate({
    getWindow: () => win,
    envPath: () => '',
    stopEngine,
    restartEngine,
    ...deps,
  });
  // Nothing happens until the delayed startup check fires.
  expect(h.updater?.checkForUpdates).not.toHaveBeenCalled();
  await vi.runAllTimersAsync();
  return { stopEngine, restartEngine };
}

beforeEach(() => {
  vi.resetModules();
  vi.useFakeTimers();
  h.boxes.length = 0;
  h.responses.length = 0;
  h.installs.length = 0;
  Object.defineProperty(process, 'platform', { value: 'win32', configurable: true });
});

afterEach(() => {
  vi.useRealTimers();
  Object.defineProperty(process, 'platform', { value: realPlatform, configurable: true });
  delete process.env.NOVA_UPDATE_CHECK;
});

describe('startAutoUpdate', () => {
  it('downloads in the background and installs only when the operator picks Restart', async () => {
    h.responses.push(0); // "Restart to update"
    const { stopEngine } = await startAndCheck();
    expect(h.updater?.autoInstallOnAppQuit).toBe(false);
    expect(win.setProgressBar).toHaveBeenCalledWith(0.5);
    expect(h.boxes.at(-1)?.buttons).toEqual(['Restart to update', 'Later']);
    expect(stopEngine).toHaveBeenCalled();
    // Silent install into the existing location, then relaunch the new version.
    expect(h.installs).toEqual([[true, true]]);
  });

  it('installs nothing when the operator picks Later', async () => {
    h.responses.push(1);
    const { stopEngine } = await startAndCheck();
    expect(stopEngine).not.toHaveBeenCalled();
    expect(h.installs).toEqual([]);
  });

  it('refuses to install while the local engine is still running, and revives it', async () => {
    h.responses.push(0);
    const { restartEngine } = await startAndCheck({ stopEngine: vi.fn(async () => false) });
    expect(h.installs).toEqual([]);
    expect(restartEngine).toHaveBeenCalled();
    expect(h.boxes.at(-1)?.message).toContain('did not install');
  });

  it('never checks on its own when the setting is off', async () => {
    process.env.NOVA_UPDATE_CHECK = '0';
    const { startAutoUpdate } = await import('../../electron/autoUpdate.mjs');
    await startAutoUpdate({ getWindow: () => win, envPath: () => '', stopEngine: vi.fn(), restartEngine: vi.fn() });
    await vi.runAllTimersAsync();
    expect(h.updater?.checkForUpdates).not.toHaveBeenCalled();
  });

  it('stays out of a dev checkout entirely', async () => {
    h.updater = null;
    const electron = await import('electron');
    (electron.app as { isPackaged: boolean }).isPackaged = false;
    const { startAutoUpdate } = await import('../../electron/autoUpdate.mjs');
    await startAutoUpdate({ getWindow: () => win, envPath: () => '', stopEngine: vi.fn(), restartEngine: vi.fn() });
    await vi.runAllTimersAsync();
    expect(h.updater).toBeNull();
    (electron.app as { isPackaged: boolean }).isPackaged = true;
  });
});
