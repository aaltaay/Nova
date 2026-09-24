/**
 * The desk must never install an update by itself (#347). These cover the glue
 * around updatePolicy.mjs: what electron-updater is configured to do, and what
 * happens on Restart, on Later, and when the local engine will not stop.
 * Since 2026-09-23 the installer is fetched by updateDownload.mjs in resumable
 * chunks and handed back to electron-updater; its own download is the fallback.
 * The open desk re-checks every two hours, never in weekday trading hours.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  UPDATE_FIRST_CHECK_DELAY_MS,
  UPDATE_RECHECK_INTERVAL_MS,
  UPDATE_RECHECK_TICK_MS,
} from '../../electron/updatePolicy.mjs';

type FakeUpdater = {
  autoDownload: boolean;
  autoInstallOnAppQuit: boolean;
  checkForUpdates: ReturnType<typeof vi.fn>;
  downloadUpdate: ReturnType<typeof vi.fn>;
  quitAndInstall: ReturnType<typeof vi.fn>;
};
type MenuRow = { label?: string; role?: string; submenu?: { label: string }[] };
type DownloadOpts = { cacheDir: string; target: { url: string }; onProgress: (p: number) => void };

const h = vi.hoisted(() => ({
  boxes: [] as { buttons?: string[]; message?: string }[],
  responses: [] as number[],
  installs: [] as unknown[][],
  updater: null as FakeUpdater | null,
  menu: [] as MenuRow[],
  // When true the fake updater exposes what a resumable download needs.
  resumable: false,
  download: null as null | ((opts: DownloadOpts) => Promise<string>),
  // One answer per check, in order: false = up to date. Empty: an update is available.
  available: [] as boolean[],
  // "Updating Nova" windows shown, and how many engine stops had run when each was.
  splashes: [] as { version: string; processName: string; closed: boolean; atStop: number }[],
  stopCalls: 0,
}));

vi.mock('electron', () => ({
  app: { isPackaged: true, getVersion: () => '0.1.831', getPath: () => '' },
  dialog: {
    showMessageBox: vi.fn(async (...args: unknown[]) => {
      h.boxes.push(args[args.length - 1] as { buttons?: string[]; message?: string });
      return { response: h.responses.shift() ?? 1 };
    }),
  },
  Menu: {
    buildFromTemplate: (t: unknown) => t,
    setApplicationMenu: (m: MenuRow[]) => {
      h.menu = m;
    },
  },
  net: { fetch: vi.fn() },
}));

vi.mock('../../electron/updateDownload.mjs', async (importOriginal) => {
  const real = await importOriginal<typeof import('../../electron/updateDownload.mjs')>();
  return {
    ...real,
    downloadInstaller: vi.fn(async (opts: DownloadOpts) => {
      if (!h.download) throw new Error('downloadInstaller called without a test double');
      return h.download(opts);
    }),
  };
});

vi.mock('../../electron/updateSplash.mjs', () => ({
  showUpdateSplash: vi.fn((opts: { version: string; processName: string }) => {
    h.splashes.push({ version: opts.version, processName: opts.processName, closed: false, atStop: h.stopCalls });
    const entry = h.splashes[h.splashes.length - 1];
    return { close: () => { entry.closed = true; } };
  }),
}));

vi.mock('electron-updater', async () => {
  const { EventEmitter } = await import('node:events');
  class NsisUpdater extends EventEmitter {
    logger: unknown;
    autoDownload = true;
    autoInstallOnAppQuit = true;
    updateInfoAndProvider: unknown = null;
    checkForUpdates = vi.fn(async () => {
      const updateInfo = { version: '0.1.832' };
      this.emit('checking-for-update');
      if (!(h.available.shift() ?? true)) {
        this.emit('update-not-available', { version: '0.1.831' });
        return { isUpdateAvailable: false, updateInfo: { version: '0.1.831' } };
      }
      if (h.resumable) {
        this.updateInfoAndProvider = {
          provider: {
            resolveFiles: () => [
              {
                url: new URL('https://github.com/aaltaay/Nova/releases/download/v832/Nova-Setup-v832.exe'),
                info: { sha512: 'abc', size: 100 },
              },
            ],
          },
        };
      }
      this.emit('update-available', updateInfo);
      return { isUpdateAvailable: true, updateInfo };
    });
    getOrCreateDownloadHelper = vi.fn(async () => ({ cacheDir: 'C:/cache/nova-updater' }));
    // electron-updater's own download, or its hand-off of a file already in the cache.
    downloadUpdate = vi.fn(async () => {
      this.emit('download-progress', { percent: 50 });
      this.emit('update-downloaded', { version: '0.1.832' });
      return [];
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
  const stopEngine = vi.fn(async () => {
    h.stopCalls += 1;
    return true;
  });
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
  // Not runAllTimers: the re-check clock repeats for as long as the desk runs.
  await vi.advanceTimersByTimeAsync(UPDATE_FIRST_CHECK_DELAY_MS);
  return { stopEngine, restartEngine };
}

function helpLabels() {
  return (h.menu.find((row) => row.role === 'help')?.submenu ?? []).map((row) => row.label);
}

beforeEach(() => {
  vi.resetModules();
  vi.useFakeTimers();
  h.boxes.length = 0;
  h.responses.length = 0;
  h.installs.length = 0;
  h.menu = [];
  h.resumable = false;
  h.download = null;
  h.available.length = 0;
  h.splashes.length = 0;
  h.stopCalls = 0;
  win.setProgressBar.mockClear();
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

  it('puts the "Updating Nova" window up at the click, before anything closes, and leaves it up', async () => {
    h.responses.push(0);
    await startAndCheck();
    // Shown before the engine stop began; it closes itself once the new window is up.
    expect(h.splashes).toEqual([
      { version: 'v832', processName: expect.any(String), closed: false, atStop: 0 },
    ]);
    expect(h.installs).toEqual([[true, true]]);
  });

  it('installs nothing when the operator picks Later', async () => {
    h.responses.push(1);
    const { stopEngine } = await startAndCheck();
    expect(stopEngine).not.toHaveBeenCalled();
    expect(h.installs).toEqual([]);
    expect(h.splashes).toEqual([]);
  });

  it('refuses to install while the local engine is still running, and revives it', async () => {
    h.responses.push(0);
    const { restartEngine } = await startAndCheck({ stopEngine: vi.fn(async () => false) });
    expect(h.installs).toEqual([]);
    expect(restartEngine).toHaveBeenCalled();
    expect(h.boxes.at(-1)?.message).toContain('did not install');
    // Nova stays open, so the "Updating Nova" window must not.
    expect(h.splashes.map((s) => s.closed)).toEqual([true]);
  });

  it('closes the "Updating Nova" window when the installer cannot be started', async () => {
    h.responses.push(0);
    const { restartEngine } = await startAndCheck({
      stopEngine: vi.fn(async () => {
        h.updater!.quitAndInstall.mockImplementation(() => {
          throw new Error('No update filepath provided');
        });
        return true;
      }),
    });
    expect(restartEngine).toHaveBeenCalled();
    expect(h.splashes.map((s) => s.closed)).toEqual([true]);
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

describe('re-checks while the desk stays open', () => {
  const MINUTE = 60_000;

  it('asks GitHub again every two hours outside trading hours, quietly', async () => {
    vi.setSystemTime(new Date('2026-09-26T14:00:00Z')); // Saturday 10:00 ET
    h.available.push(false, false);
    await startAndCheck();
    expect(h.updater?.checkForUpdates).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(UPDATE_RECHECK_INTERVAL_MS - UPDATE_RECHECK_TICK_MS);
    expect(h.updater?.checkForUpdates).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(2 * UPDATE_RECHECK_TICK_MS);
    expect(h.updater?.checkForUpdates).toHaveBeenCalledTimes(2);
    expect(h.boxes).toEqual([]); // "up to date" is never announced by an automatic check
  });

  it('holds re-checks through weekday trading hours, then catches up after the close', async () => {
    vi.setSystemTime(new Date('2026-09-23T13:00:00Z')); // Wednesday 09:00 ET
    h.available.push(false, false);
    await startAndCheck(); // the launch check itself is never held
    expect(h.updater?.checkForUpdates).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(6 * 60 * MINUTE + 50 * MINUTE); // 15:50 ET
    expect(h.updater?.checkForUpdates).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(20 * MINUTE); // 16:10 ET
    expect(h.updater?.checkForUpdates).toHaveBeenCalledTimes(2);
  });

  it("holds a re-check's prompt through trading hours and offers it after the close", async () => {
    vi.setSystemTime(new Date('2026-09-23T08:30:00Z')); // Wednesday 04:30 ET
    h.available.push(false); // the launch check finds nothing; the 06:40 re-check finds v832
    h.resumable = true;
    h.download = async (opts) => {
      // Lands at 07:10 ET, inside trading hours.
      await new Promise((resolve) => setTimeout(resolve, 30 * MINUTE));
      return `${opts.cacheDir}/pending/Nova-Setup-v832.exe`;
    };
    await startAndCheck();
    await vi.advanceTimersByTimeAsync(3 * 60 * MINUTE); // 07:30 ET
    expect(h.updater?.checkForUpdates).toHaveBeenCalledTimes(2);
    expect(helpLabels()[0]).toBe('Restart to Update (v832)');
    expect(h.boxes).toEqual([]);
    await vi.advanceTimersByTimeAsync(8 * 60 * MINUTE + 20 * MINUTE); // 15:50 ET
    expect(h.boxes).toEqual([]);
    h.responses.push(1); // Later
    await vi.advanceTimersByTimeAsync(20 * MINUTE); // 16:10 ET
    expect(h.boxes).toHaveLength(1);
    expect(h.boxes[0]?.buttons).toEqual(['Restart to update', 'Later']);
    expect(h.installs).toEqual([]);
    // Later is not re-asked this session.
    await vi.advanceTimersByTimeAsync(4 * 60 * MINUTE);
    expect(h.boxes).toHaveLength(1);
  });
});

describe('resumable installer download', () => {
  it("fetches the installer itself into electron-updater's cache, then lets electron-updater verify it", async () => {
    h.resumable = true;
    const seen: DownloadOpts[] = [];
    h.download = async (opts) => {
      seen.push(opts);
      opts.onProgress(40);
      // electron-updater has not been asked to download anything yet.
      expect(h.updater?.downloadUpdate).not.toHaveBeenCalled();
      return `${opts.cacheDir}/pending/Nova-Setup-v832.exe`;
    };
    h.responses.push(1); // Later
    await startAndCheck();
    expect(h.updater?.autoDownload).toBe(false);
    expect(seen).toHaveLength(1);
    expect(seen[0].cacheDir).toBe('C:/cache/nova-updater');
    expect(seen[0].target.url).toBe('https://github.com/aaltaay/Nova/releases/download/v832/Nova-Setup-v832.exe');
    expect(win.setProgressBar).toHaveBeenCalledWith(0.4);
    expect(h.updater?.downloadUpdate).toHaveBeenCalledTimes(1);
    expect(h.boxes.at(-1)?.buttons).toEqual(['Restart to update', 'Later']);
  });

  it('says the download stopped, keeps its percent, and offers Resume instead of a failed check', async () => {
    h.resumable = true;
    h.download = async (opts) => {
      opts.onProgress(45);
      throw new Error('net::ERR_SSL_PROTOCOL_ERROR (gave up on bytes 0-9; 0 kept)');
    };
    await startAndCheck();
    expect(h.updater?.downloadUpdate).not.toHaveBeenCalled();
    expect(h.boxes).toEqual([]); // an automatic check fails quietly
    expect(helpLabels()[0]).toBe('Download of v832 stopped at 45% — Resume');
    expect(helpLabels()[1]).toContain('ERR_SSL_PROTOCOL_ERROR');
  });

  it("falls back to electron-updater's own download when it cannot plan a resumable one", async () => {
    h.resumable = false; // no provider to resolve the installer URL
    h.responses.push(1);
    await startAndCheck();
    expect(h.updater?.downloadUpdate).toHaveBeenCalledTimes(1);
    expect(h.boxes.at(-1)?.buttons).toEqual(['Restart to update', 'Later']);
  });
});
